DROP TABLE IF EXISTS audit_log, alerts, predictions, ml_models, cooling_centers, weather_readings, weather_stations, cities, regions CASCADE;
CREATE TABLE regions (region_id SERIAL PRIMARY KEY, name VARCHAR(60) NOT NULL UNIQUE, parent_id INT REFERENCES regions(region_id) ON DELETE SET NULL);
CREATE TABLE cities (
  city_id SERIAL PRIMARY KEY, name VARCHAR(60) NOT NULL UNIQUE,
  region_id INT NOT NULL REFERENCES regions(region_id),
  population INT NOT NULL CHECK (population > 0),
  vulnerability NUMERIC(3,2) NOT NULL CHECK (vulnerability BETWEEN 0 AND 1),
  latitude NUMERIC(8,5) NOT NULL, longitude NUMERIC(8,5) NOT NULL);
CREATE TABLE weather_stations (station_id SERIAL PRIMARY KEY, city_id INT NOT NULL REFERENCES cities(city_id) ON DELETE CASCADE, name VARCHAR(80) NOT NULL);
CREATE TABLE weather_readings (
  reading_id BIGSERIAL PRIMARY KEY,
  station_id INT NOT NULL REFERENCES weather_stations(station_id) ON DELETE CASCADE,
  recorded_at TIMESTAMPTZ NOT NULL,
  temp_c NUMERIC(4,1) NOT NULL CHECK (temp_c BETWEEN -10 AND 60),
  humidity INT NOT NULL CHECK (humidity BETWEEN 0 AND 100),
  wind_kmh NUMERIC(5,1) NOT NULL DEFAULT 0 CHECK (wind_kmh >= 0),
  heat_index NUMERIC(4,1),
  UNIQUE (station_id, recorded_at));
CREATE TABLE cooling_centers (center_id SERIAL PRIMARY KEY, city_id INT NOT NULL REFERENCES cities(city_id) ON DELETE CASCADE, name VARCHAR(80) NOT NULL, capacity INT NOT NULL CHECK (capacity > 0));
CREATE TABLE ml_models (model_id SERIAL PRIMARY KEY, name VARCHAR(60) NOT NULL, version VARCHAR(20) NOT NULL, accuracy NUMERIC(4,3) CHECK (accuracy BETWEEN 0 AND 1), trained_at TIMESTAMPTZ NOT NULL DEFAULT now());
CREATE TABLE predictions (
  prediction_id SERIAL PRIMARY KEY,
  city_id INT NOT NULL REFERENCES cities(city_id) ON DELETE CASCADE,
  model_id INT NOT NULL REFERENCES ml_models(model_id),
  pred_date DATE NOT NULL,
  risk NUMERIC(4,3) NOT NULL CHECK (risk BETWEEN 0 AND 1),
  UNIQUE (city_id, model_id, pred_date));
CREATE TABLE alerts (
  alert_id SERIAL PRIMARY KEY,
  prediction_id INT NOT NULL REFERENCES predictions(prediction_id) ON DELETE CASCADE,
  level VARCHAR(10) NOT NULL CHECK (level IN ('YELLOW','ORANGE','RED')),
  message TEXT NOT NULL,
  status VARCHAR(10) NOT NULL DEFAULT 'OPEN' CHECK (status IN ('OPEN','CLOSED')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now());
CREATE TABLE audit_log (log_id SERIAL PRIMARY KEY, table_name TEXT NOT NULL, action TEXT NOT NULL, row_data JSONB, changed_at TIMESTAMPTZ NOT NULL DEFAULT now());
