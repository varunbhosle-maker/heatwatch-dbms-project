"""Downloads one year of REAL hourly weather (Open-Meteo, free, no key) for every city in the database.
Run once after the SQL files. Safe to re-run: cities that already have data are skipped."""
import os, sys, time
import psycopg2
from psycopg2.extras import execute_values
import weather_api

DB = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/heatwatch")
conn = psycopg2.connect(DB); cur = conn.cursor()
cur.execute("SELECT c.name, c.latitude::float8, c.longitude::float8, s.station_id FROM cities c JOIN weather_stations s USING (city_id) ORDER BY c.city_id")
cities = cur.fetchall()
if not cities:
    sys.exit("No cities found. Run the SQL files 01 to 04 first.")
for i, (name, lat, lon, sid) in enumerate(cities, 1):
    cur.execute("SELECT 1 FROM weather_readings WHERE station_id = %s LIMIT 1", (sid,))
    if cur.fetchone():
        print(f"[{i}/{len(cities)}] {name}: already has data, skipped"); continue
    rows = weather_api.history(lat, lon)
    execute_values(cur, "INSERT INTO weather_readings(station_id, recorded_at, temp_c, humidity, wind_kmh) VALUES %s ON CONFLICT DO NOTHING",
                   [(sid,) + r for r in rows], page_size=2000)
    conn.commit()
    print(f"[{i}/{len(cities)}] {name}: {len(rows)} hourly rows loaded")
    time.sleep(0.5)
cur.execute("REFRESH MATERIALIZED VIEW mv_city_daily_temp")
conn.commit(); conn.close()
print("Done. Now run: python train_model.py")
