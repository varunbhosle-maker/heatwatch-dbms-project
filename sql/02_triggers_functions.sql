-- 1) Auto-compute apparent temperature ("heat index") on every new reading
CREATE OR REPLACE FUNCTION trg_heat_index() RETURNS trigger AS $$
BEGIN
  NEW.heat_index := ROUND(NEW.temp_c + 0.33 * (NEW.humidity/100.0 * 6.105 * EXP(17.27*NEW.temp_c/(237.7+NEW.temp_c))) - 4.0, 1);
  RETURN NEW;
END $$ LANGUAGE plpgsql;
CREATE TRIGGER heat_index_bi BEFORE INSERT ON weather_readings FOR EACH ROW EXECUTE FUNCTION trg_heat_index();

-- 2) A prediction with risk >= 0.4 automatically creates an alert
CREATE OR REPLACE FUNCTION trg_prediction_alert() RETURNS trigger AS $$
DECLARE lvl TEXT; cname TEXT;
BEGIN
  IF NEW.risk >= 0.4 THEN
    lvl := CASE WHEN NEW.risk >= 0.8 THEN 'RED' WHEN NEW.risk >= 0.6 THEN 'ORANGE' ELSE 'YELLOW' END;
    SELECT name INTO cname FROM cities WHERE city_id = NEW.city_id;
    INSERT INTO alerts(prediction_id, level, message)
    VALUES (NEW.prediction_id, lvl, format('%s alert for %s on %s (risk %s%%)', lvl, cname, NEW.pred_date, ROUND(NEW.risk*100)));
  END IF;
  RETURN NEW;
END $$ LANGUAGE plpgsql;
CREATE TRIGGER prediction_alert_ai AFTER INSERT ON predictions FOR EACH ROW EXECUTE FUNCTION trg_prediction_alert();

-- 3) Audit log for the alerts table
CREATE OR REPLACE FUNCTION trg_audit() RETURNS trigger AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    INSERT INTO audit_log(table_name, action, row_data) VALUES (TG_TABLE_NAME, TG_OP, to_jsonb(OLD));
  ELSE
    INSERT INTO audit_log(table_name, action, row_data) VALUES (TG_TABLE_NAME, TG_OP, to_jsonb(NEW));
  END IF;
  RETURN NULL;
END $$ LANGUAGE plpgsql;
CREATE TRIGGER alerts_audit AFTER INSERT OR UPDATE OR DELETE ON alerts FOR EACH ROW EXECUTE FUNCTION trg_audit();

-- 4) Stored function and procedure
CREATE OR REPLACE FUNCTION get_city_risk_summary(p_city TEXT, p_date DATE DEFAULT CURRENT_DATE)
RETURNS TABLE(city TEXT, avg_temp_7d NUMERIC, max_heat_index NUMERIC, latest_risk NUMERIC, alert_level TEXT) AS $$
  SELECT c.name::text, ROUND(AVG(r.temp_c),1), MAX(r.heat_index),
    (SELECT p.risk::numeric FROM predictions p WHERE p.city_id = c.city_id ORDER BY p.pred_date DESC, p.prediction_id DESC LIMIT 1),
    (SELECT a.level::text FROM alerts a JOIN predictions p USING (prediction_id) WHERE p.city_id = c.city_id ORDER BY a.created_at DESC LIMIT 1)
  FROM cities c
  JOIN weather_stations s ON s.city_id = c.city_id
  JOIN weather_readings r ON r.station_id = s.station_id AND r.recorded_at >= p_date - 7 AND r.recorded_at < p_date + 1
  WHERE c.name = p_city GROUP BY c.city_id, c.name;
$$ LANGUAGE sql;

CREATE OR REPLACE PROCEDURE close_alert(p_id INT) LANGUAGE plpgsql AS $$
BEGIN
  UPDATE alerts SET status = 'CLOSED' WHERE alert_id = p_id;
  IF NOT FOUND THEN RAISE EXCEPTION 'Alert % not found', p_id; END IF;
END $$;
