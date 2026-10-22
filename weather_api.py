"""Open-Meteo helpers (free, no API key). Weather data by Open-Meteo.com, CC BY 4.0."""
import time, datetime as dt
import requests

ARCHIVE = "https://archive-api.open-meteo.com/v1/archive"
FORECAST = "https://api.open-meteo.com/v1/forecast"
GEO = "https://geocoding-api.open-meteo.com/v1/search"
HOURLY = "temperature_2m,relative_humidity_2m,wind_speed_10m"

def _get(url, params, tries=4):
    last = None
    for i in range(tries):
        try:
            r = requests.get(url, params=params, timeout=60)
            if r.status_code == 429:
                last = "rate limited"; time.sleep(10 * (i + 1)); continue
            r.raise_for_status()
            return r.json()
        except requests.RequestException as e:
            last = e; time.sleep(3 * (i + 1))
    raise RuntimeError(f"Open-Meteo request failed: {last}")

def _rows(h, until=None):
    out = []
    for t, temp, rh, ws in zip(h["time"], h["temperature_2m"], h["relative_humidity_2m"], h["wind_speed_10m"]):
        if temp is None or rh is None or not -10 <= temp <= 60:
            continue
        ts = dt.datetime.fromisoformat(t).replace(tzinfo=dt.timezone.utc)
        if until and ts > until:
            continue
        out.append((ts, round(temp, 1), max(0, min(100, round(rh))), round(max(ws or 0, 0), 1)))
    return out

def history(lat, lon, days=365):
    """Hourly (time, temp_c, humidity, wind_kmh) for the last `days` days up to now."""
    today = dt.date.today()
    a = _get(ARCHIVE, {"latitude": lat, "longitude": lon, "hourly": HOURLY, "timezone": "GMT",
                       "start_date": (today - dt.timedelta(days=days)).isoformat(),
                       "end_date": (today - dt.timedelta(days=6)).isoformat()})
    rows = _rows(a["hourly"])
    f = _get(FORECAST, {"latitude": lat, "longitude": lon, "hourly": HOURLY, "past_days": 7, "forecast_days": 1, "timezone": "GMT"})
    now = dt.datetime.now(dt.timezone.utc)
    last = rows[-1][0] if rows else dt.datetime.min.replace(tzinfo=dt.timezone.utc)
    return rows + [r for r in _rows(f["hourly"], until=now) if r[0] > last]

def current(points):
    """Current conditions for a list of (lat, lon). One API call for all points."""
    j = _get(FORECAST, {"latitude": ",".join(str(p[0]) for p in points), "longitude": ",".join(str(p[1]) for p in points),
                        "current": "temperature_2m,relative_humidity_2m,wind_speed_10m", "timezone": "GMT"})
    if isinstance(j, dict):
        j = [j]
    return [x.get("current", {}) for x in j]

def geocode(name):
    j = _get(GEO, {"name": name, "count": 10, "language": "en", "format": "json"})
    for r in j.get("results") or []:
        if r.get("country_code") == "IN":
            return {"name": r["name"], "region": r.get("admin1") or "India", "lat": r["latitude"],
                    "lon": r["longitude"], "population": r.get("population") or 500000}
    return None
