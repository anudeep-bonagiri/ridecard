"""Open map data: OSRM for road geometry, Open-Meteo for the forecast.

Routes are cached to data/routes so a planned ride works with no signal.
"""
import hashlib
import json
import math
import urllib.parse
import urllib.request
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"
PLACES = json.loads((DATA / "places.json").read_text())
ROUTES = DATA / "routes"
UA = {"User-Agent": "ridecard/0.1 (github.com/anudeep-bonagiri/ridecard)"}


def place(name):
    for k, v in PLACES.items():
        if k.lower() == name.lower():
            return k, v
    raise KeyError(f"unknown place '{name}'. Known: {', '.join(sorted(PLACES))}")


def _get(url, timeout=30):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
        return json.load(r)


def route_key(names):
    return hashlib.sha1("|".join(n.lower() for n in names).encode()).hexdigest()[:12]


def route(names, offline=False):
    """Road route through the named places, start and end included. Returns dict with km, minutes, coords [[lat, lon], ...]."""
    ROUTES.mkdir(exist_ok=True)
    cache = ROUTES / f"{route_key(names)}.json"
    if cache.exists():
        return json.loads(cache.read_text())
    if offline:
        return None
    pts = [place(n)[1] for n in names]
    coords = ";".join(f"{p['lon']},{p['lat']}" for p in pts)
    url = f"https://router.project-osrm.org/route/v1/driving/{coords}?overview=full&geometries=geojson"
    data = _get(url)
    r = data["routes"][0]
    out = {
        "waypoints": names,
        "km": round(r["distance"] / 1000, 1),
        "minutes": round(r["duration"] / 60),
        "coords": [[round(lat, 5), round(lon, 5)] for lon, lat in r["geometry"]["coordinates"]],
    }
    cache.write_text(json.dumps(out))
    return out


def forecast(lat, lon, date):
    """Daily forecast for one date (YYYY-MM-DD). Returns None when offline or out of range."""
    q = urllib.parse.urlencode({
        "latitude": lat, "longitude": lon,
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max,wind_speed_10m_max,wind_gusts_10m_max,sunrise,sunset",
        "temperature_unit": "fahrenheit", "wind_speed_unit": "mph",
        "timezone": "America/Chicago", "start_date": date, "end_date": date,
    })
    try:
        d = _get("https://api.open-meteo.com/v1/forecast?" + q, timeout=15)["daily"]
    except Exception:
        return None
    return {
        "high_f": d["temperature_2m_max"][0], "low_f": d["temperature_2m_min"][0],
        "rain_pct": d["precipitation_probability_max"][0],
        "wind_mph": d["wind_speed_10m_max"][0], "gust_mph": d["wind_gusts_10m_max"][0],
        "sunrise": d["sunrise"][0][-5:], "sunset": d["sunset"][0][-5:],
    }


def haversine_km(a, b):
    (lat1, lon1), (lat2, lon2) = a, b
    p = math.pi / 180
    h = math.sin((lat2 - lat1) * p / 2) ** 2 + math.cos(lat1 * p) * math.cos(lat2 * p) * math.sin((lon2 - lon1) * p / 2) ** 2
    return 12742 * math.asin(math.sqrt(h))
