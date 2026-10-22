DROP MATERIALIZED VIEW IF EXISTS mv_city_daily_temp;
CREATE MATERIALIZED VIEW mv_city_daily_temp AS
SELECT c.city_id, c.name AS city, r.recorded_at::date AS day,
  ROUND(AVG(r.temp_c),1) AS avg_temp, MAX(r.temp_c) AS max_temp, MAX(r.heat_index) AS max_heat_index
FROM weather_readings r JOIN weather_stations s USING (station_id) JOIN cities c USING (city_id)
GROUP BY c.city_id, c.name, r.recorded_at::date;

CREATE OR REPLACE VIEW v_latest_risk AS
SELECT DISTINCT ON (c.city_id) c.city_id, c.name AS city, p.pred_date, p.risk::float8 AS risk,
  CASE WHEN p.risk >= 0.8 THEN 'RED' WHEN p.risk >= 0.6 THEN 'ORANGE' WHEN p.risk >= 0.4 THEN 'YELLOW' ELSE 'NORMAL' END AS level
FROM cities c JOIN predictions p USING (city_id)
ORDER BY c.city_id, p.pred_date DESC, p.prediction_id DESC;

CREATE OR REPLACE VIEW v_capacity_gap AS
SELECT c.name AS city, c.population, SUM(cc.capacity) AS total_capacity,
  ROUND(c.population::numeric / SUM(cc.capacity)) AS people_per_seat
FROM cities c JOIN cooling_centers cc USING (city_id) GROUP BY c.city_id, c.name, c.population;
