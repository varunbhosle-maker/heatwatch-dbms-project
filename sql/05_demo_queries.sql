-- Run these one block at a time (select + F5 in pgAdmin Query Tool)

-- A) Window function: 7-day moving average per city
SELECT city, day, avg_temp,
  ROUND(AVG(avg_temp) OVER (PARTITION BY city ORDER BY day ROWS BETWEEN 6 PRECEDING AND CURRENT ROW), 1) AS moving_avg_7d
FROM mv_city_daily_temp WHERE day >= CURRENT_DATE - 14 ORDER BY city, day;

-- B) RANK: hottest city-days
SELECT * FROM (SELECT city, day, max_temp, RANK() OVER (ORDER BY max_temp DESC) AS rk FROM mv_city_daily_temp) t WHERE rk <= 10 ORDER BY rk;

-- C) CTE: days at or above 40 C per city
WITH hot AS (SELECT city, day FROM mv_city_daily_temp WHERE max_temp >= 40)
SELECT city, COUNT(*) AS hot_days FROM hot GROUP BY city ORDER BY hot_days DESC;

-- D) Recursive CTE: region hierarchy
WITH RECURSIVE tree AS (
  SELECT region_id, name, 0 AS depth, name::text AS path FROM regions WHERE parent_id IS NULL
  UNION ALL
  SELECT r.region_id, r.name, t.depth + 1, t.path || ' > ' || r.name FROM regions r JOIN tree t ON r.parent_id = t.region_id)
SELECT path, depth FROM tree ORDER BY path;

-- E) Function, procedure, views, audit log
SELECT * FROM get_city_risk_summary('Nagpur');
SELECT * FROM v_latest_risk ORDER BY risk DESC;
SELECT * FROM v_capacity_gap ORDER BY people_per_seat DESC;
CALL close_alert(1);
SELECT * FROM audit_log ORDER BY log_id DESC LIMIT 5;

-- F) Index demo: compare "Execution Time" before and after
EXPLAIN ANALYZE SELECT AVG(temp_c) FROM weather_readings WHERE recorded_at BETWEEN now() - interval '3 days' AND now() - interval '2 days';
CREATE INDEX idx_readings_time ON weather_readings(recorded_at);
ANALYZE weather_readings;
EXPLAIN ANALYZE SELECT AVG(temp_c) FROM weather_readings WHERE recorded_at BETWEEN now() - interval '3 days' AND now() - interval '2 days';
-- DROP INDEX idx_readings_time;   -- to repeat the demo

-- G) Transaction: change is visible inside, undone by ROLLBACK
BEGIN;
UPDATE alerts SET status = 'CLOSED' WHERE status = 'OPEN';
SELECT status, COUNT(*) FROM alerts GROUP BY status;
ROLLBACK;
SELECT status, COUNT(*) FROM alerts GROUP BY status;

-- H) Roles and permissions
DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'analyst') THEN CREATE ROLE analyst LOGIN PASSWORD 'analyst123'; END IF; END $$;
GRANT SELECT ON v_latest_risk, mv_city_daily_temp, v_capacity_gap TO analyst;
REVOKE ALL ON audit_log FROM analyst;
