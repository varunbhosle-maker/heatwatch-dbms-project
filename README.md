# HeatWatch: DBMS mini project (PostgreSQL + Flask + ML + live weather)

37 Indian cities. Real weather from Open-Meteo (free, no key). Live update every 5 minutes.

## Run it (Windows)
1. pgAdmin: create a database named `heatwatch`. In its Query Tool run these files from `sql/` in order (F5):
   `01_schema.sql`, `02_triggers_functions.sql`, `03_seed.sql`, `04_views.sql`
2. Terminal in this folder:
   ```
   python -m venv venv
   venv\Scripts\activate
   pip install -r requirements.txt
   ```
   If your Postgres password is not `postgres`: `set DATABASE_URL=postgresql://postgres:YOURPASS@localhost:5432/heatwatch`
3. `python load_history.py`   (downloads one year of real hourly weather for all cities; a few minutes, needs internet)
4. `python train_model.py`    (trains the model, saves model.joblib, writes predictions; triggers create alerts)
5. `python app.py`  then open http://127.0.0.1:5000

## What is live
- On start and then every 5 minutes, `app.py` fetches current weather for all cities (one API call), inserts it,
  refreshes the materialized view, re-scores with the model and lets the trigger raise alerts. The Dashboard shows a
  countdown and a "Fetch now" button. Open-Meteo refreshes its current values about every 15 minutes, so a value can
  repeat between two fetches.
- Add data page: add one reading, simulate a whole day, or add a NEW CITY by name.

## Demo flow for the teacher
Problem, ER diagram, dashboard, Add data (simulate a heatwave and watch the alert pop up), Compare, then
`sql/05_demo_queries.sql` block by block.

## Credit for your report
Weather data by Open-Meteo.com (https://open-meteo.com), licensed CC BY 4.0. Historical values come from reanalysis,
current values from forecast-model analysis. City populations and vulnerability scores are approximate and illustrative.
