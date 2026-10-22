import os, time, threading, datetime
import psycopg2, psycopg2.extras
from psycopg2.extras import execute_values
import weather_api
import joblib, pandas as pd
from flask import Flask, jsonify, render_template, request

DB = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/heatwatch")
app = Flask(__name__)

def query(sql, args=None, commit=False):
    conn = psycopg2.connect(DB)
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, args)
            rows = cur.fetchall() if cur.description else []
            if commit:
                conn.commit()
            return rows
    finally:
        conn.close()

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/api/cities")
def cities():
    return jsonify(query("""
        SELECT c.name AS city, r.name AS region, c.population, c.vulnerability::float8 AS vulnerability, c.latitude::float8 AS lat, c.longitude::float8 AS lon,
               COALESCE(v.risk, 0)::float8 AS risk, COALESCE(v.level, 'NORMAL') AS level,
               (SELECT m.max_temp::float8 FROM mv_city_daily_temp m WHERE m.city_id = c.city_id ORDER BY m.day DESC LIMIT 1) AS latest_max,
               g.total_capacity::int AS total_capacity, g.people_per_seat::int AS people_per_seat
        FROM cities c JOIN regions r ON r.region_id = c.region_id
        LEFT JOIN v_latest_risk v ON v.city_id = c.city_id
        LEFT JOIN v_capacity_gap g ON g.city = c.name
        ORDER BY risk DESC, c.name"""))

@app.route("/api/trend/<city>")
def trend(city):
    return jsonify(query("""SELECT * FROM (SELECT day::text AS day, max_temp::float8 AS max_temp, avg_temp::float8 AS avg_temp
        FROM mv_city_daily_temp WHERE city = %s ORDER BY day DESC LIMIT 45) t ORDER BY day""", (city,)))

@app.route("/api/alerts")
def alerts():
    return jsonify(query("""SELECT a.alert_id, c.name AS city, a.level, a.message, a.status,
        to_char(a.created_at, 'DD Mon HH24:MI') AS created
        FROM alerts a JOIN predictions p USING (prediction_id) JOIN cities c USING (city_id)
        ORDER BY a.created_at DESC, a.alert_id DESC LIMIT 50"""))

@app.post("/api/alerts/<int:alert_id>/close")
def close_alert(alert_id):
    query("CALL close_alert(%s)", (alert_id,), commit=True)   # stored procedure from 02_triggers_functions.sql
    return jsonify(ok=True)

@app.route("/api/stats")
def stats():
    s = query("""SELECT (SELECT COUNT(*) FROM weather_readings) AS readings,
        (SELECT MIN(recorded_at)::date::text FROM weather_readings) AS first_day,
        (SELECT MAX(recorded_at)::date::text FROM weather_readings) AS last_day,
        (SELECT COUNT(*) FROM alerts WHERE status = 'OPEN') AS open_alerts""")[0]
    m = query("""SELECT name, version, accuracy::float8 AS accuracy, to_char(trained_at, 'DD Mon YYYY HH24:MI') AS trained
        FROM ml_models ORDER BY model_id DESC LIMIT 1""")
    s["model"] = m[0] if m else None
    s["live"] = {"last": LIVE["last"], "status": LIVE["status"], "next_in": max(0, int(LIVE["next"] - time.time()))}
    return jsonify(s)

MODEL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "model.joblib")
FEATS = ["avg_temp", "max_temp", "max_heat_index", "prev_max", "mean3"]

def bad(e):
    msg = str(e).splitlines()[0]
    if "check constraint" in msg:
        msg = "Value out of range (temperature -10 to 60, humidity 0 to 100, wind 0 or more)."
    return jsonify(error=msg), 400

def write_and_refresh(sql, args):
    conn = psycopg2.connect(DB)
    try:
        with conn.cursor() as cur:
            cur.execute(sql, args)
            cur.execute("REFRESH MATERIALIZED VIEW mv_city_daily_temp")
        conn.commit()
    finally:
        conn.close()

def lvl(p):
    return 3 if p >= 0.8 else 2 if p >= 0.6 else 1 if p >= 0.4 else 0

def rescore():
    """Re-run the trained model on the newest data. If a city's risk changed, replace its prediction,
    and the INSERT trigger raises a fresh alert."""
    if not os.path.exists(MODEL):
        raise RuntimeError("model.joblib not found. Run train_model.py once first.")
    model = joblib.load(MODEL)
    conn = psycopg2.connect(DB)
    try:
        cur = conn.cursor()
        cur.execute("SELECT city_id, day, avg_temp, max_temp, max_heat_index FROM mv_city_daily_temp ORDER BY city_id, day")
        df = pd.DataFrame(cur.fetchall(), columns=[d[0] for d in cur.description])
        for c in ["avg_temp", "max_temp", "max_heat_index"]:
            df[c] = df[c].astype(float)
        g = df.groupby("city_id")["max_temp"]
        df["prev_max"] = g.shift(1)
        df["mean3"] = g.transform(lambda x: x.rolling(3).mean())
        latest = df.groupby("city_id").tail(1).dropna(subset=FEATS)
        risk = model.predict_proba(latest[FEATS])[:, 1]
        cur.execute("SELECT model_id FROM ml_models ORDER BY model_id DESC LIMIT 1")
        mid = cur.fetchone()[0]
        for (_, r), p in zip(latest.iterrows(), risk):
            d, p = r.day + datetime.timedelta(days=1), round(float(p), 3)
            cur.execute("SELECT risk FROM predictions WHERE city_id=%s AND model_id=%s AND pred_date=%s", (int(r.city_id), mid, d))
            old = cur.fetchone()
            key = (int(r.city_id), mid, d)
            if old and lvl(float(old[0])) == lvl(p):      # same alert level: just update the number, no new alert
                if abs(float(old[0]) - p) >= 0.001:
                    cur.execute("UPDATE predictions SET risk=%s WHERE city_id=%s AND model_id=%s AND pred_date=%s", (p,) + key)
                continue
            if old:                                        # level changed: replace, so the INSERT trigger raises a new alert
                cur.execute("DELETE FROM predictions WHERE city_id=%s AND model_id=%s AND pred_date=%s", key)
            cur.execute("INSERT INTO predictions(city_id, model_id, pred_date, risk) VALUES (%s,%s,%s,%s)", key + (p,))
        conn.commit()
    finally:
        conn.close()

@app.post("/api/readings")
def add_reading():
    d = request.get_json(force=True)
    try:
        write_and_refresh("""INSERT INTO weather_readings(station_id, recorded_at, temp_c, humidity, wind_kmh)
            SELECT s.station_id, (SELECT MAX(w.recorded_at) FROM weather_readings w WHERE w.station_id = s.station_id) + interval '1 hour', %s, %s, %s
            FROM weather_stations s JOIN cities c USING (city_id) WHERE c.name = %s""",
            (float(d["temp_c"]), int(d["humidity"]), float(d.get("wind_kmh") or 0), d["city"]))
        rescore()
    except (psycopg2.Error, ValueError, KeyError, RuntimeError) as e:
        return bad(e)
    return jsonify(ok=True)

@app.post("/api/simulate")
def simulate():
    d = request.get_json(force=True)
    try:
        peak = float(d["peak"])
        if not 20 <= peak <= 55:
            raise ValueError("Peak temperature must be between 20 and 55.")
        write_and_refresh("""WITH nd AS (
              SELECT s.station_id, (SELECT MAX(m.day) FROM mv_city_daily_temp m WHERE m.city_id = c.city_id) + 1 AS day
              FROM cities c JOIN weather_stations s USING (city_id) WHERE c.name = %s)
            INSERT INTO weather_readings(station_id, recorded_at, temp_c, humidity, wind_kmh)
            SELECT nd.station_id, (nd.day + h * interval '1 hour')::timestamptz,
                   ROUND((%s - 8 * (1 - (1 + SIN(2 * PI() * (h - 9) / 24.0)) / 2) + (random() - 0.5))::numeric, 1),
                   (35 + random() * 20)::int, ROUND((5 + random() * 10)::numeric, 1)
            FROM nd, generate_series(0, 23) AS h""", (d["city"], peak))
        rescore()
    except (psycopg2.Error, ValueError, KeyError, RuntimeError) as e:
        return bad(e)
    return jsonify(ok=True)

@app.route("/api/readings/recent")
def recent():
    return jsonify(query("""SELECT c.name AS city, to_char(w.recorded_at, 'DD Mon HH24:MI') AS t, w.temp_c::float8 AS temp_c,
        w.humidity, w.wind_kmh::float8 AS wind, w.heat_index::float8 AS heat_index
        FROM weather_readings w JOIN weather_stations s USING (station_id) JOIN cities c USING (city_id)
        ORDER BY w.reading_id DESC LIMIT 8"""))

LIVE = {"last": None, "status": "starting", "next": time.time() + 5}
EVERY = 300  # seconds: live update every 5 minutes

def fetch_live():
    """Pull current real weather for every city (one API call), store it, refresh the view, re-score."""
    pts = query("SELECT c.latitude::float8 AS lat, c.longitude::float8 AS lon, s.station_id FROM cities c JOIN weather_stations s USING (city_id) ORDER BY c.city_id")
    vals = weather_api.current([(p["lat"], p["lon"]) for p in pts])
    now = datetime.datetime.now(datetime.timezone.utc)
    rows = [(p["station_id"], now, round(v["temperature_2m"], 1), max(0, min(100, round(v["relative_humidity_2m"]))), round(max(v.get("wind_speed_10m") or 0, 0), 1))
            for p, v in zip(pts, vals)
            if v.get("temperature_2m") is not None and v.get("relative_humidity_2m") is not None and -10 <= v["temperature_2m"] <= 60]
    conn = psycopg2.connect(DB)
    try:
        with conn.cursor() as cur:
            execute_values(cur, "INSERT INTO weather_readings(station_id, recorded_at, temp_c, humidity, wind_kmh) VALUES %s ON CONFLICT DO NOTHING", rows)
            cur.execute("REFRESH MATERIALIZED VIEW mv_city_daily_temp")
        conn.commit()
    finally:
        conn.close()
    LIVE.update(last=now.isoformat(), status="ok")
    rescore()

def live_loop():
    while True:
        try:
            fetch_live()
        except Exception as e:
            LIVE["status"] = "error: " + str(e)[:90]
            print("Live update failed:", e)
        LIVE["next"] = time.time() + EVERY
        time.sleep(EVERY)

@app.post("/api/live/refresh")
def live_refresh():
    try:
        fetch_live()
        LIVE["next"] = time.time() + EVERY
    except Exception as e:
        return bad(e)
    return jsonify(ok=True)

@app.post("/api/cities")
def add_city():
    name = (request.get_json(force=True).get("name") or "").strip()
    try:
        if not name:
            raise ValueError("Type a city name.")
        g = weather_api.geocode(name)
        if not g:
            raise ValueError("Could not find '%s' in India." % name)
        rows = weather_api.history(g["lat"], g["lon"])
        conn = psycopg2.connect(DB)
        try:
            cur = conn.cursor()
            cur.execute("SELECT 1 FROM cities WHERE lower(name) = lower(%s)", (g["name"],))
            if cur.fetchone():
                raise ValueError("%s is already added." % g["name"])
            cur.execute("INSERT INTO regions(name, parent_id) SELECT %s, region_id FROM regions WHERE name = 'India' ON CONFLICT (name) DO NOTHING", (g["region"],))
            cur.execute("INSERT INTO cities(name, region_id, population, vulnerability, latitude, longitude) SELECT %s, region_id, %s, 0.60, %s, %s FROM regions WHERE name = %s RETURNING city_id",
                        (g["name"], int(g["population"]), g["lat"], g["lon"], g["region"]))
            cid = cur.fetchone()[0]
            cur.execute("INSERT INTO weather_stations(city_id, name) VALUES (%s, %s) RETURNING station_id", (cid, g["name"] + " Central"))
            sid = cur.fetchone()[0]
            cur.execute("INSERT INTO cooling_centers(city_id, name, capacity) SELECT %s, %s || ' Cooling Hub ' || n::text, GREATEST(300, %s / 20000) FROM generate_series(1,3) n",
                        (cid, g["name"], int(g["population"])))
            execute_values(cur, "INSERT INTO weather_readings(station_id, recorded_at, temp_c, humidity, wind_kmh) VALUES %s ON CONFLICT DO NOTHING",
                           [(sid,) + r for r in rows], page_size=2000)
            cur.execute("REFRESH MATERIALIZED VIEW mv_city_daily_temp")
            conn.commit()
        finally:
            conn.close()
        rescore()
    except (psycopg2.Error, ValueError, KeyError, RuntimeError) as e:
        return bad(e)
    return jsonify(ok=True, city=g["name"])

if __name__ == "__main__":
    threading.Thread(target=live_loop, daemon=True).start()   # real weather every 5 minutes
    app.run(debug=False, threaded=True)
