-- 37 Indian cities (name, state, population, vulnerability 0-1, latitude, longitude)
-- Vulnerability is an illustrative score (heat exposure, density, poverty). Weather data comes from load_history.py.
CREATE TEMP TABLE seed_cities(name TEXT, state TEXT, population INT, vulnerability NUMERIC, latitude NUMERIC, longitude NUMERIC);
INSERT INTO seed_cities VALUES
('Delhi','Delhi',16800000,0.85,28.61,77.21),('Mumbai','Maharashtra',12400000,0.55,19.08,72.88),
('Pune','Maharashtra',3100000,0.50,18.52,73.86),('Nagpur','Maharashtra',2900000,0.80,21.15,79.09),
('Nashik','Maharashtra',1500000,0.60,19.99,73.79),('Ahmedabad','Gujarat',5600000,0.75,23.02,72.57),
('Surat','Gujarat',4500000,0.65,21.17,72.83),('Vadodara','Gujarat',1700000,0.65,22.31,73.18),
('Rajkot','Gujarat',1300000,0.70,22.30,70.80),('Jaipur','Rajasthan',3000000,0.78,26.91,75.79),
('Jodhpur','Rajasthan',1100000,0.82,26.24,73.02),('Bikaner','Rajasthan',650000,0.85,28.02,73.31),
('Kota','Rajasthan',1000000,0.75,25.18,75.83),('Hyderabad','Telangana',6800000,0.60,17.39,78.49),
('Warangal','Telangana',800000,0.70,17.97,79.59),('Chennai','Tamil Nadu',7100000,0.65,13.08,80.27),
('Madurai','Tamil Nadu',1500000,0.65,9.93,78.12),('Bengaluru','Karnataka',8400000,0.40,12.97,77.59),
('Kochi','Kerala',600000,0.45,9.93,76.27),('Visakhapatnam','Andhra Pradesh',2000000,0.65,17.69,83.22),
('Vijayawada','Andhra Pradesh',1000000,0.75,16.51,80.65),('Bhubaneswar','Odisha',900000,0.65,20.30,85.82),
('Kolkata','West Bengal',4500000,0.60,22.57,88.36),('Patna','Bihar',2000000,0.80,25.59,85.14),
('Ranchi','Jharkhand',1100000,0.60,23.34,85.31),('Lucknow','Uttar Pradesh',3500000,0.80,26.85,80.95),
('Kanpur','Uttar Pradesh',3100000,0.82,26.45,80.35),('Varanasi','Uttar Pradesh',1200000,0.80,25.32,82.97),
('Prayagraj','Uttar Pradesh',1500000,0.80,25.44,81.85),('Agra','Uttar Pradesh',1700000,0.80,27.18,78.01),
('Bhopal','Madhya Pradesh',1800000,0.65,23.26,77.41),('Indore','Madhya Pradesh',2200000,0.65,22.72,75.86),
('Raipur','Chhattisgarh',1100000,0.70,21.25,81.63),('Chandigarh','Chandigarh',1100000,0.60,30.73,76.78),
('Amritsar','Punjab',1200000,0.65,31.63,74.87),('Ludhiana','Punjab',1700000,0.65,30.90,75.86),
('Guwahati','Assam',1000000,0.45,26.14,91.74);

INSERT INTO regions(name, parent_id) VALUES ('India', NULL);
INSERT INTO regions(name, parent_id) SELECT DISTINCT state, (SELECT region_id FROM regions WHERE name = 'India') FROM seed_cities;
INSERT INTO cities(name, region_id, population, vulnerability, latitude, longitude)
SELECT s.name, r.region_id, s.population, s.vulnerability, s.latitude, s.longitude FROM seed_cities s JOIN regions r ON r.name = s.state;
INSERT INTO weather_stations(city_id, name) SELECT city_id, name || ' Central' FROM cities;
INSERT INTO cooling_centers(city_id, name, capacity)
SELECT c.city_id, c.name || ' Cooling Hub ' || g, GREATEST(300, (c.population / 20000.0 * (0.6 + random() * 0.8))::int)
FROM cities c, generate_series(1,3) g;
