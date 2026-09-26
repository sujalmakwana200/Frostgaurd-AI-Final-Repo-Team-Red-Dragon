"""
Run this ONCE, locally, on a machine with normal internet access:

    python precompute_routes.py

It fetches all 14 fixed truck routes from the public OSRM server and saves
them to routes_cache.json. Commit that file to the repo.

Why this exists: main_dashboard.py used to call the live OSRM API for these
same 14 routes on every cold boot (see fetch_route() in main_dashboard.py).
On a resource-limited host (Render free tier, Streamlit Cloud), OSRM's
public rate limiting could make that take up to ~56s (14 calls x 4s
timeout) before the dashboard rendered anything — which is what was
causing the stuck black screen. Precomputing once, like the ML model
artifact, removes that live network dependency from every boot entirely.

If a route is ever missing from routes_cache.json (new truck added, etc.),
fetch_route() in main_dashboard.py just falls back to a live OSRM call for
that one route, same as before — this script only removes it from the
critical boot path for the routes it already has.
"""

import json
import time
from pathlib import Path

import requests

BASE_DIR = Path(__file__).resolve().parent

START_LAT, START_LON = 22.3072, 73.1812
DEST_LAT, DEST_LON = 23.0225, 72.5714

CITY_COORDS = {
    "Vadodara": (22.3072, 73.1812),
    "Ahmedabad": (23.0225, 72.5714),
    "Anand": (22.5645, 72.9289),
    "Nadiad": (22.6939, 72.8616),
    "Gandhinagar": (23.2156, 72.6369),
    "Sanand": (22.9922, 72.3818),
    "Mumbai": (19.0760, 72.8777),
    "Delhi": (28.6139, 77.2090),
    "Chennai": (13.0827, 80.2707),
    "Bangalore": (12.9716, 77.5946),
    "Jaipur": (26.9124, 75.7873),
}

# Same 13 routes as DEFAULT_FLEET_CONFIG in main_dashboard.py.
ROUTE_STRINGS = [
    "Vadodara -> Ahmedabad",
    "Vadodara -> Anand",
    "Anand -> Ahmedabad",
    "Nadiad -> Gandhinagar",
    "Ahmedabad -> Gandhinagar",
    "Vadodara -> Sanand",
    "Anand -> Gandhinagar",
    "Nadiad -> Ahmedabad",
    "Vadodara -> Gandhinagar",
    "Mumbai -> Delhi",
    "Chennai -> Bangalore",
    "Mumbai -> Jaipur",
    "Ahmedabad -> Chennai",
]


def route_endpoints():
    pairs = [(START_LAT, START_LON, DEST_LAT, DEST_LON)]  # the main route
    for route in ROUTE_STRINGS:
        origin, destination = [p.strip() for p in route.split("->", 1)]
        slat, slon = CITY_COORDS[origin]
        elat, elon = CITY_COORDS[destination]
        pairs.append((slat, slon, elat, elon))
    return pairs


def fetch_route(slat, slon, elat, elon):
    url = (
        f"https://router.project-osrm.org/route/v1/driving/"
        f"{slon},{slat};{elon},{elat}?overview=full&geometries=geojson"
    )
    resp = requests.get(url, timeout=10)
    resp.raise_for_status()
    d = resp.json()
    return [(c[1], c[0]) for c in d["routes"][0]["geometry"]["coordinates"]]


def main():
    cache = {}
    pairs = route_endpoints()
    print(f"Fetching {len(pairs)} routes from OSRM...")
    for i, (slat, slon, elat, elon) in enumerate(pairs, 1):
        key = f"{slon:.4f},{slat:.4f},{elon:.4f},{elat:.4f}"
        try:
            cache[key] = fetch_route(slat, slon, elat, elon)
            print(f"  [{i}/{len(pairs)}] ok: {key} ({len(cache[key])} points)")
        except Exception as exc:
            print(f"  [{i}/{len(pairs)}] FAILED: {key} -> {exc}")
        time.sleep(1.2)  # be polite to the public OSRM server

    out_path = BASE_DIR / "routes_cache.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(cache, f)
    print(f"\nSaved {len(cache)}/{len(pairs)} routes to {out_path}")
    print("Commit this file to the repo.")


if __name__ == "__main__":
    main()
