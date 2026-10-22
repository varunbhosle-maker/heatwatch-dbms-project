"""Reads daily weather from PostgreSQL, trains a RandomForest, writes tomorrow's heatwave risk back
into `predictions`. The DB trigger then creates alerts automatically."""
import os, sys, datetime
import pandas as pd, psycopg2, joblib
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split

DB = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/heatwatch")
THRESH = 40.0  # a heatwave day: max temperature >= 40 C
FEATS = ["avg_temp", "max_temp", "max_heat_index", "prev_max", "mean3"]

conn = psycopg2.connect(DB); cur = conn.cursor()
cur.execute("SELECT city_id, day, avg_temp, max_temp, max_heat_index FROM mv_city_daily_temp ORDER BY city_id, day")
df = pd.DataFrame(cur.fetchall(), columns=[d[0] for d in cur.description])
for c in ["avg_temp", "max_temp", "max_heat_index"]:
    df[c] = df[c].astype(float)

g = df.groupby("city_id")["max_temp"]
df["prev_max"] = g.shift(1)
df["mean3"] = g.transform(lambda s: s.rolling(3).mean())
nxt = g.shift(-1)

train = df[nxt.notna()].dropna(subset=FEATS).copy()
train["target"] = (nxt[train.index] >= THRESH).astype(int)
if train["target"].nunique() < 2:
    sys.exit("Not enough heatwave days in the data to train. Run load_history.py first.")

X_tr, X_te, y_tr, y_te = train_test_split(train[FEATS], train["target"], test_size=0.25, random_state=42, stratify=train["target"])
model = RandomForestClassifier(n_estimators=200, random_state=42, class_weight="balanced").fit(X_tr, y_tr)
acc = model.score(X_te, y_te)
print(f"Model accuracy on held-out data: {acc:.3f}")
joblib.dump(model, os.path.join(os.path.dirname(os.path.abspath(__file__)), "model.joblib"))  # used by app.py for live re-scoring

latest = df.sort_values("day").groupby("city_id").tail(1).dropna(subset=FEATS)
risk = model.predict_proba(latest[FEATS])[:, 1]

cur.execute("INSERT INTO ml_models(name, version, accuracy) VALUES ('RandomForest','1.0',%s) RETURNING model_id", (round(acc, 3),))
model_id = cur.fetchone()[0]
for (_, r), p in zip(latest.iterrows(), risk):
    cur.execute("INSERT INTO predictions(city_id, model_id, pred_date, risk) VALUES (%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                (int(r.city_id), model_id, r.day + datetime.timedelta(days=1), round(float(p), 3)))
    print(f"city {int(r.city_id)}: risk {p:.2f}")
conn.commit(); conn.close()
print("Done. Check the alerts table: triggers created the alerts.")
