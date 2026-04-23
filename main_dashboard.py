"""
FrostGuard AI — Dashboard v3
- Old black dashboard UI preserved
- Live updates use Streamlit fragments instead of a blocking rerun loop
- Graceful fallback when bridge telemetry is not available
"""
from __future__ import annotations

import math
import os
import json
import html
import csv
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import pydeck as pdk
import requests
import streamlit as st
import streamlit.components.v1 as components

# ──────────────────────────────────────────────────────────────
#  PAGE CONFIG — must be first Streamlit call
# ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="FrostGuard AI — Cold Fleet",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ──────────────────────────────────────────────────────────────
#  CONSTANTS
# ──────────────────────────────────────────────────────────────
API_BASE = "http://127.0.0.1:5000"
SAFE_MAX = 6.5
CRITICAL_AT = 8.0
START_LAT, START_LON = 22.3072, 73.1812
DEST_LAT, DEST_LON = 23.0225, 72.5714
BASE_DIR = Path(__file__).resolve().parent

HEALTHCARE_DATASET_CANDIDATES = [
    os.environ.get("DATASET_PATH", ""),
    str(BASE_DIR / "data" / "healthcare_iot_target_dataset.csv"),
    str(BASE_DIR / "healthcare_iot_target_dataset.csv"),
    r"C:\Users\lenovo\OneDrive\Desktop\python\python for computer graphics\LAB11\FrostGuard_Final_Project\data\healthcare_iot_target_dataset.csv",
    r"C:\Users\lenovo\OneDrive\Desktop\FrostGaurd engine\healthcare_iot_target_dataset.csv",
]

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

COLD_STORAGES = [
    {"name": "GAIMFP PPC Cold Store", "city": "Vadodara", "lat": 22.3100, "lon": 73.1650},
    {"name": "Amar Cold Storage", "city": "Anand", "lat": 22.5907, "lon": 72.9316},
    {"name": "Nadiad BioCold Hub", "city": "Nadiad", "lat": 22.6939, "lon": 72.8616},
    {"name": "Kheda Vaccine Vault", "city": "Kheda", "lat": 22.7500, "lon": 72.6800},
    {"name": "Sanand Pharma Cold Chain", "city": "Sanand", "lat": 22.9922, "lon": 72.3818},
    {"name": "Ahmedabad MedCold Depot", "city": "Ahmedabad", "lat": 23.0258, "lon": 72.5873},
    {"name": "Gujarat Cold Storage Association", "city": "Ahmedabad", "lat": 23.0613, "lon": 72.5857},
    {"name": "Vrundavan Cold Storage", "city": "Gandhinagar", "lat": 23.1500, "lon": 72.6800},
    {"name": "Mumbai Hub", "city": "Mumbai", "lat": 19.0760, "lon": 72.8777},
    {"name": "Nashik Storage", "city": "Nashik", "lat": 19.9975, "lon": 73.7898},
    {"name": "Indore Cold", "city": "Indore", "lat": 22.7196, "lon": 75.8577},
    {"name": "Jaipur Storage", "city": "Jaipur", "lat": 26.9124, "lon": 75.7873},
    {"name": "Delhi Hub", "city": "Delhi", "lat": 28.6139, "lon": 77.2090},
    {"name": "Chennai Hub", "city": "Chennai", "lat": 13.0827, "lon": 80.2707},
    {"name": "Vellore Storage", "city": "Vellore", "lat": 12.9165, "lon": 79.1325},
    {"name": "Bangalore Hub", "city": "Bangalore", "lat": 12.9716, "lon": 77.5946},
]

FLEET_CONFIG_CANDIDATES = [
    BASE_DIR / "config" / "frostguard_config.json",
    Path(r"C:\Users\lenovo\OneDrive\Desktop\python\python for computer graphics\LAB11\FrostGuard_Final_Project\config\frostguard_config.json"),
]

DEFAULT_FLEET_CONFIG = [
    {"truck_id": "TRK-RD-001", "cargo": "Vaccines", "route": "Vadodara -> Ahmedabad", "profile": "critical-demo", "start_offset": 0},
    {"truck_id": "TRK-RD-014", "cargo": "Insulin", "route": "Vadodara -> Anand", "profile": "warning-demo", "start_offset": 18},
    {"truck_id": "TRK-RD-021", "cargo": "RBC Blood Bags", "route": "Anand -> Ahmedabad", "profile": "stable", "start_offset": 42},
    {"truck_id": "TRK-RD-033", "cargo": "Platelets", "route": "Nadiad -> Gandhinagar", "profile": "handling-risk", "start_offset": 64},
    {"truck_id": "TRK-RD-045", "cargo": "Frozen Biologics", "route": "Ahmedabad -> Gandhinagar", "profile": "stable", "start_offset": 84},
    {"truck_id": "TRK-RD-052", "cargo": "mRNA Booster Vials", "route": "Vadodara -> Sanand", "profile": "warning-demo", "start_offset": 104},
    {"truck_id": "TRK-RD-067", "cargo": "Plasma Units", "route": "Anand -> Gandhinagar", "profile": "stable", "start_offset": 126},
    {"truck_id": "TRK-RD-078", "cargo": "Oncology Injectables", "route": "Nadiad -> Ahmedabad", "profile": "handling-risk", "start_offset": 148},
    {"truck_id": "TRK-RD-092", "cargo": "Organ Transport Kit", "route": "Vadodara -> Gandhinagar", "profile": "critical-demo", "start_offset": 166},
    {"truck_id": "TRK-LH-104", "cargo": "Vaccines", "route": "Mumbai -> Delhi", "profile": "warning-demo", "start_offset": 210},
    {"truck_id": "TRK-LH-118", "cargo": "Frozen Biologics", "route": "Chennai -> Bangalore", "profile": "stable", "start_offset": 260},
    {"truck_id": "TRK-LH-127", "cargo": "Insulin", "route": "Mumbai -> Jaipur", "profile": "handling-risk", "start_offset": 320},
    {"truck_id": "TRK-LH-139", "cargo": "Organ Transport Kit", "route": "Ahmedabad -> Chennai", "profile": "critical-demo", "start_offset": 380},
]

PROFILE_OFFSETS = {
    "critical-demo": (1.35, 2.0),
    "warning-demo": (0.75, -1.5),
    "handling-risk": (0.35, -3.0),
    "stable": (-0.2, 1.0),
}


def load_fleet_config() -> list[dict[str, Any]]:
    for path in FLEET_CONFIG_CANDIDATES:
        if not path.exists():
            continue
        try:
            with path.open("r", encoding="utf-8") as f:
                fleet = json.load(f).get("fleet", [])
            if isinstance(fleet, list) and fleet:
                return fleet
        except Exception:
            continue
    return DEFAULT_FLEET_CONFIG


def build_fleet_routes() -> list[dict[str, Any]]:
    routes: list[dict[str, Any]] = []
    for index, item in enumerate(load_fleet_config()):
        route_text = str(item.get("route", "Vadodara -> Ahmedabad"))
        if "->" in route_text:
            origin, destination = [part.strip() for part in route_text.split("->", 1)]
        else:
            origin, destination = "Vadodara", "Ahmedabad"
        start = CITY_COORDS.get(origin, (START_LAT, START_LON))
        end = CITY_COORDS.get(destination, (DEST_LAT, DEST_LON))
        profile = str(item.get("profile", "stable"))
        temp_offset, speed_offset = PROFILE_OFFSETS.get(profile, (0.0, 0.0))
        truck_id = str(item.get("truck_id", f"TRK-{index + 1:03d}"))
        routes.append({
            "truck_id": truck_id,
            "truck_name": str(item.get("truck_name") or item.get("name") or truck_id),
            "cargo": str(item.get("cargo", "Medical Cargo")),
            "origin": origin,
            "destination": destination,
            "start": start,
            "end": end,
            "profile": profile,
            "start_offset": float(item.get("start_offset", index * 20)),
            "temp_offset": temp_offset,
            "speed_offset": speed_offset,
        })
    return routes


FLEET_ROUTES = build_fleet_routes()

# ──────────────────────────────────────────────────────────────
#  THEME — old black dashboard styling
# ──────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Mono:wght@400;700&family=DM+Sans:ital,opsz,wght@0,9..40,300;0,9..40,600;0,9..40,800&display=swap');

html, body,
[data-testid="stAppViewContainer"],
[data-testid="stMain"],
.main, .block-container {
    background: #000 !important;
    color: #E2E2E2 !important;
    font-family: 'DM Sans', sans-serif !important;
}
[data-testid="collapsedControl"],
[data-testid="stToolbar"],
[data-testid="stDecoration"],
[data-testid="stStatusWidget"],
#MainMenu, header { display: none !important; }

.block-container { padding: 1.2rem 1.8rem 2rem !important; }

[data-testid="metric-container"] {
    background: #0A0A0A;
    border: 1px solid #1C1C1C;
    border-radius: 10px;
    padding: 12px 16px !important;
}
[data-testid="stMetricLabel"] {
    color: #555 !important; font-size: 0.64rem !important;
    letter-spacing: 0.1em; text-transform: uppercase;
    font-family: 'Space Mono', monospace !important;
}
[data-testid="stMetricValue"] { color: #F2F2F2 !important; font-size: 1.35rem !important; font-weight: 800; }
[data-testid="stMetricDelta"] { font-size: 0.7rem !important; }

.fg-card {
    background: #080808;
    border: 1px solid #1A1A1A;
    border-radius: 10px;
    padding: 14px 18px;
}
.fg-card-title {
    font-family: 'Space Mono', monospace;
    font-size: 0.6rem; letter-spacing: 0.14em;
    text-transform: uppercase; color: #3A3A3A; margin-bottom: 10px;
}
.risk-badge {
    display: inline-block; padding: 3px 11px; border-radius: 20px;
    font-family: 'Space Mono', monospace; font-size: 0.65rem;
    font-weight: 700; letter-spacing: 0.06em;
}
.risk-LOW      { background:#061208; color:#4CAF50; border:1px solid #0e2e18; }
.risk-MEDIUM   { background:#141000; color:#FFC107; border:1px solid #2e2600; }
.risk-HIGH     { background:#180a00; color:#FF6B35; border:1px solid #341500; }
.risk-CRITICAL { background:#180000; color:#FF3B3B; border:1px solid #3a0000; }

.ev-item {
    background: #0A0A0A; border-left: 3px solid var(--c, #333);
    border-radius: 0 6px 6px 0; padding: 7px 10px; margin-bottom: 5px;
}
.ev-time { font-family:'Space Mono',monospace; font-size:0.58rem; color:#3A3A3A; }
.ev-msg  { font-size:0.72rem; color:#C0C0C0; margin-top:2px; line-height:1.4; }

.bars-wrap { display:flex; gap:3px; align-items:flex-end; height:38px; margin-top:6px; }
.bar { flex:1; border-radius:2px 2px 0 0; min-height:3px; }

.dot { display:inline-block; width:7px; height:7px; border-radius:50%; margin-right:5px; vertical-align:middle; }

[data-testid="stButton"] button {
    background: #0D0D0D !important; border: 1px solid #252525 !important;
    color: #AAA !important; border-radius: 8px !important; font-size: 0.78rem !important;
}
[data-testid="stButton"] button:hover { border-color: #FF3B3B !important; color: #FF3B3B !important; }

[data-testid="stSelectbox"] label {
    color: #555 !important; font-size: 0.64rem !important;
    letter-spacing: 0.1em; text-transform: uppercase;
    font-family: 'Space Mono', monospace !important;
}
[data-baseweb="select"] > div {
    background: #0A0A0A !important;
    border: 1px solid #1C1C1C !important;
    border-radius: 8px !important;
    color: #E2E2E2 !important;
}

.truck-row {
    display:grid; grid-template-columns: 0.95fr 0.9fr 0.8fr 0.8fr;
    gap:6px; align-items:center;
    background:#0A0A0A; border-left:3px solid var(--c,#333);
    border-radius:0 6px 6px 0; padding:7px 10px; margin-bottom:5px;
}
.truck-row div { font-size:0.68rem; color:#B8B8B8; line-height:1.25; }
.truck-row b { color:#F2F2F2; font-size:0.72rem; }

.fleet-board {
    background:#080808;
    border:1px solid #123A5A;
    border-radius:10px;
    padding:14px 16px;
    box-shadow:0 0 0 1px rgba(45,156,255,0.06);
}
.fleet-board .fg-card-title {
    color:#2D9CFF;
}
.fleet-card-grid {
    display:grid;
    grid-template-columns:repeat(auto-fit, minmax(286px, 1fr));
    gap:10px;
}
.fleet-card {
    --c:#4CAF50; --fleet-blue:#2D9CFF; --p:0%; --temp:0%; --breach:0%;
    background:#090909;
    border:1px solid #1A1A1A;
    border-top:2px solid var(--fleet-blue);
    border-radius:10px;
    padding:12px 13px;
    min-height:218px;
    position:relative;
    overflow:hidden;
    transition:border-color 180ms ease, background-color 180ms ease;
}
.fleet-card > * { position:relative; z-index:1; }
.fleet-card-top { display:flex; justify-content:space-between; gap:8px; align-items:flex-start; }
.fleet-name { color:#F2F2F2; font-weight:800; font-size:0.82rem; line-height:1.1; }
.fleet-id { color:#3A3A3A; font-family:'Space Mono',monospace; font-size:0.58rem; margin-top:2px; }
.fleet-status {
    color:var(--c); border:1px solid color-mix(in srgb,var(--c) 42%,#111);
    background:#070707; border-radius:20px; padding:2px 7px;
    font-family:'Space Mono',monospace; font-size:0.55rem; font-weight:700;
}
.fleet-meta { color:#858585; font-size:0.66rem; line-height:1.35; margin-top:8px; min-height:34px; }
.meter-track {
    height:6px; background:#111; border:1px solid #1C1C1C; border-radius:20px;
    overflow:hidden; position:relative;
}
.route-track {
    height:18px;
    margin-top:10px;
    overflow:visible;
    position:relative;
    border:1px solid #17476D;
    border-radius:7px;
    background:
        linear-gradient(180deg,rgba(255,255,255,0.07),transparent 38%,rgba(0,0,0,0.35)),
        #101010;
    box-shadow:inset 0 1px 0 #215B86, inset 0 -1px 0 #050505;
}
.route-track::before {
    content:"";
    position:absolute;
    left:8px; right:8px; top:50%;
    height:2px;
    transform:translateY(-50%);
    background:repeating-linear-gradient(90deg,rgba(210,210,210,0.7) 0 13px,transparent 13px 25px);
    opacity:0.55;
}
.route-fill, .temp-fill, .breach-fill {
    height:100%; width:var(--p); border-radius:20px; background:var(--c);
    transition:width 320ms ease;
}
.route-fill {
    position:absolute;
    left:0; bottom:-1px;
    height:3px;
    width:var(--p);
    border-radius:0 0 7px 7px;
    background:var(--fleet-blue);
    box-shadow:0 0 8px rgba(45,156,255,0.65);
}
.route-vehicle {
    position:absolute;
    top:50%; left:var(--p);
    width:22px; height:11px;
    border-radius:2px 3px 3px 2px;
    background:#8ED0FF;
    border:1px solid #1B6EA8;
    transform:translate(-50%,-50%);
    box-shadow:0 2px 8px rgba(0,0,0,0.45), 0 0 11px rgba(45,156,255,0.55);
    transition:left 420ms ease;
    animation:vehicle-idle 2.8s ease-in-out infinite;
}
.route-vehicle::before {
    content:"";
    position:absolute;
    right:-5px; top:2px;
    width:7px; height:7px;
    border-radius:1px 3px 3px 1px;
    background:#C9EAFF;
    border:1px solid #1B6EA8;
}
.route-vehicle::after {
    content:"";
    position:absolute;
    left:3px; bottom:-4px;
    width:4px; height:4px;
    border-radius:50%;
    background:#050505;
    border:1px solid #555;
    box-shadow:13px 0 0 #050505, 13px 0 0 1px #555;
}
.fleet-stat-row { display:grid; grid-template-columns:1fr 1fr; gap:7px; margin-top:9px; }
.fleet-stat-label {
    color:#3A3A3A; font-family:'Space Mono',monospace; font-size:0.52rem;
    letter-spacing:0.08em; text-transform:uppercase; margin-bottom:3px;
}
.fleet-stat-value { color:#D8D8D8; font-size:0.78rem; font-weight:800; }
.temp-fill { width:var(--temp); background:linear-gradient(90deg,#4CAF50,#FFC107,#FF3B3B); }
.breach-fill { width:var(--breach); background:linear-gradient(90deg,#4CAF50,#FF6B35,#FF3B3B); }
.fleet-evidence {
    display:grid; grid-template-columns:1fr 1fr 1fr;
    gap:6px; margin-top:9px;
}
.fleet-evidence-item {
    background:#050505; border:1px solid #151515;
    border-radius:7px; padding:7px 8px;
}
.fleet-note {
    margin-top:8px; color:#777; font-size:0.64rem; line-height:1.35;
}
.fleet- {
    margin-top:8px; padding:6px 7px; border-radius:7px; background:#060606;
    border:1px solid #151515; color:#ABABAB; font-size:0.64rem; line-height:1.25;
}
@keyframes vehicle-idle {
    0%,100% { transform:translate(-50%,-50%); }
    50% { transform:translate(-50%,calc(-50% - 1px)); }
}
@media (max-width: 1250px) { .fleet-card-grid { grid-template-columns:repeat(2, minmax(0,1fr)); } }
@media (max-width: 780px) { .fleet-card-grid { grid-template-columns:1fr; } }

[data-testid="stVegaLiteChart"] { background: transparent !important; }
[data-testid="stAlert"] { border-radius: 8px !important; }
::-webkit-scrollbar { width:4px; }
::-webkit-scrollbar-track { background:#000; }
::-webkit-scrollbar-thumb { background:#1C1C1C; border-radius:4px; }

.staleElement,
.stale-element,
[data-testid="staleElement"],
[data-testid="stale-element"],
[data-testid="staleWidget"],
[data-stale="true"] {
    opacity: 1 !important;
    filter: none !important;
}
</style>
""", unsafe_allow_html=True)


# ──────────────────────────────────────────────────────────────
#  SESSION STATE — init all keys upfront, no KeyError ever
# ──────────────────────────────────────────────────────────────
def fresh_defaults() -> dict[str, Any]:
    return {
        "services_launched": False,
        "temp_history": [],
        "speed_history": [],
        "warning_log": [],
        "waypoint_idx": 0,
        "dist_covered": 0.0,
        "prev_lat": START_LAT,
        "prev_lon": START_LON,
        "d": False,
        "reroute_target": None,
        "main_route": [],
        "active_route": [],
        "fleet_routes": {},
        "journey_complete": False,
        "last_temp": 5.0,
        "last_lat": START_LAT,
        "last_lon": START_LON,
        "last_snapshot": None,
        "last_snapshot_at": 0.0,
        "last_point_signature": None,
        "selected_truck_id": "AUTO",
        "last_voice_signature": None,
        "spoken_alert_keys": [],
        "demo_started_at": time.time(),
        "failure_until": 0.0,
        "bridge_process": None,
        "last_bridge_launch": 0.0,
    }


for _k, _v in fresh_defaults().items():
    if _k not in st.session_state:
        st.session_state[_k] = _v


# ──────────────────────────────────────────────────────────────
#  HELPERS
# ──────────────────────────────────────────────────────────────
def haversine(lat1, lon1, lat2, lon2):
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    return R * 2 * math.asin(math.sqrt(a))


def nearest_cold_storage(lat, lon):
    return min(COLD_STORAGES, key=lambda s: haversine(lat, lon, s["lat"], s["lon"]))


@st.cache_data(ttl=3600, show_spinner=False)
# Strip cache decorator, or use it smartly
# Strip cache decorator so straight lines aren't saved forever
def fetch_route(slon, slat, elon, elat):
    try:
        url = f"https://router.project-osrm.org/route/v1/driving/{slon},{slat};{elon},{elat}?overview=full&geometries=geojson"
        d = requests.get(url, timeout=4).json()
        return [(c[1], c[0]) for c in d["routes"][0]["geometry"]["coordinates"]]
    except Exception:
        steps = 180
        return [(slat + i / steps * (elat - slat), slon + i / steps * (elon - slon)) for i in range(steps + 1)]
def risk_color(level):
    return {
        "CRITICAL": "#FF3B3B", "HIGH": "#FF6B35",
        "MEDIUM": "#FFC107", "LOW": "#4CAF50",
    }.get(str(level).upper(), "#555")


def risk_from_temp(temp):
    if temp >= CRITICAL_AT:
        return "CRITICAL"
    if temp > SAFE_MAX:
        return "WARNING"
    return "SAFE"


def safe_float(value, default=0.0):
    try:
        if value is None:
            return default
        if isinstance(value, str):
            value = value.strip()
            if not value or value.lower() in {"nan", "none", "null"}:
                return default
        result = float(value)
        if math.isnan(result) or math.isinf(result):
            return default
        return result
    except Exception:
        return default


def default_ml(temp=5.0):
    pressure = max(float(temp) - SAFE_MAX, 0.0)
    risk = "CRITICAL" if temp >= CRITICAL_AT else ("HIGH" if temp > SAFE_MAX + 0.7 else ("MEDIUM" if temp > SAFE_MAX else "LOW"))
    forecast = [round(float(temp) + math.sin(i / 2) * 0.08 + pressure * i * 0.05, 2) for i in range(1, 11)]
    return {
        "risk_level": risk,
        "anomaly": pressure > 1.1,
        "anomaly_score": int(min(100, pressure * 42)),
        "breach_probability": int(min(100, pressure / max(CRITICAL_AT - SAFE_MAX, 0.1) * 78)),
        "forecast_series": forecast,
        "predicted_temp_30s": round(forecast[-1] if forecast else temp, 2),
        "time_to_critical_sec": 0 if temp >= CRITICAL_AT else None,
        "recommendation": "Waiting for sensor data…",
        "training_rows": 0,
    }


def normalise_dataset_sample(row: dict[str, Any], source_path: Path) -> dict[str, Any]:
    temp_mean = safe_float(row.get("temp_mean"), 5.0)
    temp_min = safe_float(row.get("temp_min"), temp_mean)
    temp_max = safe_float(row.get("temp_max"), temp_mean)
    data_temp = temp_max if temp_max > 0 else temp_mean
    health_index = safe_float(row.get("Health_Index", row.get("health_index")), 0.98)
    return {
        "bag_id": row.get("bag_id", "BAG"),
        "data_timestamp": row.get("timestamp", ""),
        "data_route": row.get("route", ""),
        "blood_type": row.get("blood_type", ""),
        "product_type": row.get("product_type", ""),
        "data_temperature": round(data_temp, 2),
        "temp_mean": round(temp_mean, 2),
        "temp_min": round(temp_min, 2),
        "temp_max": round(temp_max, 2),
        "temp_std": round(safe_float(row.get("temp_std"), 0.0), 3),
        "frac_temp_above_6": round(safe_float(row.get("frac_temp_above_6"), 0.0), 3),
        "frac_temp_above_8": round(safe_float(row.get("frac_temp_above_8"), 0.0), 3),
        "hum_mean": round(safe_float(row.get("hum_mean"), 0.0), 1),
        "hum_std": round(safe_float(row.get("hum_std"), 0.0), 2),
        "door_count": round(safe_float(row.get("door_count"), 0.0), 2),
        "accel_rms": round(safe_float(row.get("accel_rms"), 0.0), 3),
        "handling_stress": round(safe_float(row.get("handling_stress"), 0.0), 3),
        "health_index": round(max(0.0, min(1.0, health_index)), 3),
        "dataset_source": source_path.name,
    }


@st.cache_data(ttl=900, show_spinner=False)
def load_healthcare_samples() -> list[dict[str, Any]]:
    for candidate in HEALTHCARE_DATASET_CANDIDATES:
        if not candidate:
            continue
        path = Path(candidate)
        if not path.exists():
            continue
        samples: list[dict[str, Any]] = []
        try:
            with path.open("r", newline="", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                for row_no, row in enumerate(reader):
                    if row_no % 48 != 0:
                        continue
                    samples.append(normalise_dataset_sample(row, path))
                    if len(samples) >= 1200:
                        break
            if samples:
                return samples
        except Exception:
            continue
    return []


def dataset_sample_for_truck(index: int) -> dict[str, Any]:
    samples = load_healthcare_samples()
    if not samples:
        return {}
    tick = int(max(time.time() - st.session_state.demo_started_at, 0) / 2.0)
    return samples[(tick + index * 37) % len(samples)]


def attach_dataset_context(telemetry: dict[str, Any], sample: dict[str, Any]) -> dict[str, Any]:
    if not sample:
        return telemetry
    enriched = dict(telemetry)
    for key, value in sample.items():
        enriched.setdefault(key, value)
    return enriched


def enrich_fleet_with_dataset(fleet: list[dict[str, Any]]) -> list[dict[str, Any]]:
    enriched = []
    for index, truck in enumerate(fleet):
        enriched.append(attach_dataset_context(dict(truck), dataset_sample_for_truck(index)))
    return enriched


def api_online():
    try:
        return requests.get(f"{API_BASE}/health", timeout=0.8).status_code == 200
    except Exception:
        return False


def launch_services():
    if api_online():
        return
    # Clean up old handles and processes
    proc = st.session_state.get("bridge_process")
    if proc is not None:
        try:
            proc.terminate()
            if proc.stdout: proc.stdout.close()
            if proc.stderr: proc.stderr.close()
        except Exception:
            pass

    base = os.path.dirname(os.path.abspath(__file__))
    logs = os.path.join(base, "logs")
    os.makedirs(logs, exist_ok=True)
    
    # Call api.py, forget Bridge.py
    api_path = os.path.join(base, "api.py")
    if os.path.exists(api_path):
        stdout = open(os.path.join(logs, "api_stdout.log"), "a", encoding="utf-8")
        stderr = open(os.path.join(logs, "api_stderr.log"), "a", encoding="utf-8")
        popen_kwargs = {"cwd": base, "stdout": stdout, "stderr": stderr}
        if hasattr(subprocess, "CREATE_NO_WINDOW"): popen_kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        
        st.session_state.bridge_process = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "api:app", "--host", "0.0.0.0", "--port", "5000"],
            **popen_kwargs,
        )
        st.session_state.last_bridge_launch = time.time()
def ensure_services():
    if api_online():
        st.session_state.services_launched = True
        return
    if time.time() - float(st.session_state.get("last_bridge_launch", 0.0)) > 4.0:
        launch_services()
        st.session_state.services_launched = True


def ensure_routes():
    if not st.session_state.main_route:
        st.session_state.main_route = fetch_route(START_LON, START_LAT, DEST_LON, DEST_LAT)
    if not st.session_state.active_route:
        st.session_state.active_route = st.session_state.main_route
    if not st.session_state.fleet_routes:
        routes = {}
        for item in FLEET_ROUTES:
            slat, slon = item["start"]
            elat, elon = item["end"]
            routes[item["truck_id"]] = fetch_route(slon, slat, elon, elat)
        st.session_state.fleet_routes = routes


def fetch_latest():
    try:
        resp = requests.get(f"{API_BASE}/latest", timeout=0.8)
        if resp.status_code == 200:
            return resp.json()
    except Exception:
        pass
    return None


def fetch_fleet():
    try:
        resp = requests.get(f"{API_BASE}/fleet", timeout=1.2)
        if resp.status_code == 200:
            data = resp.json()
            fleet = data.get("fleet", data if isinstance(data, list) else [])
            if isinstance(fleet, list) and fleet:
                return fleet
    except Exception:
        pass
    return []


def route_point(route, progress):
    if not route:
        return START_LAT, START_LON
    idx = min(len(route) - 1, max(0, int(progress * (len(route) - 1))))
    return route[idx]


def route_distance_km(route):
    if len(route) < 2:
        return 0.0
    return sum(haversine(a[0], a[1], b[0], b[1]) for a, b in zip(route, route[1:]))


def local_reroute(telemetry):
    temp = float(telemetry.get("temperature", 5.0))
    status = telemetry.get("status", risk_from_temp(temp))
    if status != "CRITICAL" and temp < CRITICAL_AT:
        return None
    lat = float(telemetry.get("lat", START_LAT))
    lon = float(telemetry.get("lng", START_LON))
    target = nearest_cold_storage(lat, lon)
    return {
        "target": target,
        "distance_km": round(haversine(lat, lon, target["lat"], target["lon"]), 2),
        "method": "KNN fallback",
    }


def demo_fleet():
    elapsed = max(time.time() - st.session_state.demo_started_at, 0)
    failure = time.time() < st.session_state.failure_until
    fleet = []
    
    # --- ADD THIS SPEED BOOST ---
    SPEED_BOOST = 3.5  # 1.0 is normal, 3.5 is fast, 5.0 is zooming!
    
    for idx, item in enumerate(FLEET_ROUTES):
        route = st.session_state.fleet_routes.get(item["truck_id"]) or st.session_state.main_route
        sample = dataset_sample_for_truck(idx)
        route_total_hint = route_distance_km(route) if route else 0.0
        
        # --- DIVIDE THE CYCLE BY THE SPEED BOOST ---
        cycle = (260 + idx * 22 + min(route_total_hint, 600) * 0.25) / SPEED_BOOST
        
        progress = (((elapsed + float(item.get("start_offset", 0))) / cycle) + idx * 0.025) % 1.0
        lat, lon = route_point(route, progress)
        route_total = route_total_hint
        travelled = route_total * progress
        forced = 3.4 if failure and idx in {0, 2} else 0.0
        # ... keep the rest of the function exactly the same!

def choose_focus_truck(fleet):
    if not fleet:
        return {
            "truck_id": "TRK-RD-001",
            "cargo": "Vaccines",
            "temperature": st.session_state.last_temp,
            "status": "SAFE",
            "lat": st.session_state.last_lat,
            "lng": st.session_state.last_lon,
            "timestamp": "—",
            "speed_kmh": 0.0,
            "ml_insight": default_ml(st.session_state.last_temp),
        }
        
    selected_id = st.session_state.get("selected_truck_id", "AUTO")
    
    if selected_id and selected_id != "AUTO":
        selected = next((item for item in fleet if item.get("truck_id") == selected_id), None)
        if selected:
            return selected
        
        # If the backend forgot the truck, create a temporary placeholder
        configured = next((truck for truck in FLEET_ROUTES if truck.get("truck_id") == selected_id), None)
        if configured:
            fallback = dict(configured)
            fallback.update({
                "status": "WAITING FOR DATA", 
                "temperature": "—", 
                "speed_kmh": 0.0, 
                "distance_travelled_km": "—",
                "ml_insight": default_ml(5.0)
            })
            return fallback

    for status in ("CRITICAL", "WARNING"):
        match = next((item for item in fleet if item.get("status") == status), None)
        if match:
            return match
            
    return next((item for item in fleet if item.get("truck_id") == "TRK-RD-001"), fleet[0])

def target_from_reroute(telemetry, lat, lon):
    reroute = telemetry.get("reroute") or {}
    target = reroute.get("target") if isinstance(reroute, dict) else None
    if isinstance(target, dict) and "lat" in target and ("lon" in target or "lng" in target):
        return {
            "name": target.get("name", "KNN Cold Storage"),
            "city": target.get("city", "Emergency"),
            "lat": float(target["lat"]),
            "lon": float(target.get("lon", target.get("lng"))),
        }
    return nearest_cold_storage(lat, lon)


def demo_telemetry():
    return choose_focus_truck(demo_fleet())

    route = st.session_state.active_route or st.session_state.main_route or [(START_LAT, START_LON), (DEST_LAT, DEST_LON)]
    elapsed = max(time.time() - st.session_state.demo_started_at, 0)
    idx = int((elapsed / 2.0) % max(len(route), 1))
    lat, lon = route[idx]
    failure = time.time() < st.session_state.failure_until
    temp = 5.0 + math.sin(elapsed / 18.0) * 0.45 + (3.4 if failure else 0.0)
    temp = round(temp, 1)
    status = risk_from_temp(temp)
    speed = 66 + math.cos(elapsed / 14.0) * 6
    ml = default_ml(temp)
    if status == "WARNING":
        ml["recommendation"] = "Temp rising — compressor activated."
    elif status == "CRITICAL":
        ml["recommendation"] = "Reroute to nearest cold storage immediately."
    return {
        "truck_id": "TRK-RD-001",
        "cargo": "Vaccines",
        "temperature": temp,
        "status": status,
        "lat": lat,
        "lng": lon,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "speed_kmh": round(speed, 1),
        "ml_insight": ml,
    }


def apply_trip_state(telemetry):
    temp = float(telemetry.get("temperature", 5.0))
    lat = float(telemetry.get("lat", START_LAT))
    lon = float(telemetry.get("lng", START_LON))
    status = telemetry.get("status", "SAFE")
    ts = telemetry.get("timestamp", "—")
    speed_kmh = float(telemetry.get("speed_kmh", 68.0))
    signature = (telemetry.get("truck_id"), ts, round(lat, 5), round(lon, 5), temp)

    if st.session_state.last_point_signature == signature:
        return
    st.session_state.last_point_signature = signature

    st.session_state.temp_history.append(temp)
    st.session_state.speed_history.append(speed_kmh)
    st.session_state.temp_history = st.session_state.temp_history[-80:]
    st.session_state.speed_history = st.session_state.speed_history[-80:]

    step_km = haversine(st.session_state.prev_lat, st.session_state.prev_lon, lat, lon)
    if step_km < 25:
        st.session_state.dist_covered = round(st.session_state.dist_covered + step_km, 2)
    st.session_state.prev_lat = lat
    st.session_state.prev_lon = lon
    st.session_state.waypoint_idx += 1
    st.session_state.last_temp = temp
    st.session_state.last_lat = lat
    st.session_state.last_lon = lon

    truck_route = st.session_state.fleet_routes.get(telemetry.get("truck_id"))
    if status == "CRITICAL":
        target = target_from_reroute(telemetry, lat, lon)
        st.session_state.reroute_target = target
        st.session_state.rerouted = True
        st.session_state.active_route = fetch_route(lon, lat, target["lon"], target["lat"])
        prev_msgs = [e["msg"] for e in st.session_state.warning_log[:4]]
        msg = f"CRITICAL {temp}°C — {telemetry.get('truck_id')} rerouting to {target['name']}, {target['city']}"
        if not any(telemetry.get("truck_id", "") in m and "CRITICAL" in m for m in prev_msgs):
            st.session_state.warning_log.insert(0, {
                "time": ts, "icon": "🚨", "color": "#FF3B3B",
                "msg": msg,
            })
    elif status == "WARNING":
        if truck_route:
            st.session_state.active_route = truck_route
        st.session_state.rerouted = False
        st.session_state.reroute_target = None
        prev_msgs = [e["msg"] for e in st.session_state.warning_log[:2]]
        if not any("WARNING" in m or "rising" in m for m in prev_msgs):
            st.session_state.warning_log.insert(0, {
                "time": ts, "icon": "⚠️", "color": "#FFC107",
                "msg": f"{telemetry.get('truck_id')} temp rising: {temp}°C — compressor activated",
            })
    else:
        if truck_route:
            st.session_state.active_route = truck_route
        st.session_state.rerouted = False
        st.session_state.reroute_target = None


def get_dashboard_state(force=False):
    ensure_services()
    ensure_routes()

    now = time.monotonic()
    if not force and st.session_state.last_snapshot and now - st.session_state.last_snapshot_at < 2.8:
        return st.session_state.last_snapshot

    live_fleet = fetch_fleet()
    live_telemetry = fetch_latest()
    
    # 1. Start with the frontend's beautifully smooth, curvy OSRM simulation
    simulated_fleet = demo_fleet()
    
    # 2. Grab any REAL data that just came in from the API
    real_data = {t["truck_id"]: t for t in live_fleet} if live_fleet else {}
    if live_telemetry:
        real_data[live_telemetry["truck_id"]] = live_telemetry
        
    # 3. THE SMART MERGE: Keep the smooth GPS from the simulation, 
    # but overwrite the temperature and ML alerts with the real API data!
    fleet = []
    for sim_truck in simulated_fleet:
        tid = sim_truck["truck_id"]
        if tid in real_data:
            real_truck = real_data[tid]
            merged_truck = dict(sim_truck) # Inherit the smooth map coordinates
            
            # Inject the real data
            merged_truck["temperature"] = real_truck.get("temperature", merged_truck["temperature"])
            merged_truck["status"] = real_truck.get("status", merged_truck["status"])
            merged_truck["timestamp"] = real_truck.get("timestamp", merged_truck["timestamp"])
            
            if "ml_insight" in real_truck:
                merged_truck["ml_insight"] = real_truck["ml_insight"]
            if "reroute" in real_truck:
                merged_truck["reroute"] = real_truck["reroute"]
                
            fleet.append(merged_truck)
        else:
            fleet.append(sim_truck)

    fleet = enrich_fleet_with_dataset(fleet)
    telemetry = choose_focus_truck(fleet)
    apply_trip_state(telemetry)

    temp = float(telemetry.get("temperature", 5.0))
    lat = float(telemetry.get("lat", START_LAT))
    lon = float(telemetry.get("lng", START_LON))
    status = telemetry.get("status", "SAFE")
    cargo = telemetry.get("cargo", "Vaccines")
    truck_id = telemetry.get("truck_id", "TRK-RD-001")
    ts = telemetry.get("timestamp", "—")
    speed_kmh = float(telemetry.get("speed_kmh", 68.0))
    ml = telemetry.get("ml_insight") or default_ml(temp)
    risk = ml.get("risk_level", "LOW")
    remaining = max(len(st.session_state.active_route) - st.session_state.waypoint_idx, 0)
    eta_min = int(remaining * 3 / 60) if speed_kmh > 0 else 0

    snapshot = {
        "telemetry": telemetry,
        "live_telemetry": live_telemetry,
        "fleet": fleet,
        "api_ok": api_online(),
        "sim_ok": bool(fleet),
        "temp": temp,
        "lat": lat,
        "lon": lon,
        "status": status,
        "cargo": cargo,
        "truck_id": truck_id,
        "ts": ts,
        "speed_kmh": speed_kmh,
        "ml": ml,
        "risk": risk,
        "rc": risk_color(risk),
        "is_crit": status == "CRITICAL",
        "is_warn": status == "WARNING",
        "eta_min": eta_min,
    }
    st.session_state.last_snapshot = snapshot
    st.session_state.last_snapshot_at = now
    return snapshot
def voice_alert(snapshot):
    fleet = snapshot.get("fleet") or [snapshot]
    alert_trucks = [truck for truck in fleet if truck.get("status") in {"WARNING", "CRITICAL"}]
    safe_ids = {str(truck.get("truck_id", "")) for truck in fleet if truck.get("status") not in {"WARNING", "CRITICAL"}}
    spoken = [
        key for key in st.session_state.get("spoken_alert_keys", [])
        if key.split(":", 1)[0] not in safe_ids
    ]
    st.session_state.spoken_alert_keys = spoken
    if not alert_trucks:
        return

    truck = None
    alert_key = None
    for candidate in alert_trucks:
        candidate_key = f"{candidate.get('truck_id')}:{candidate.get('status')}"
        if candidate_key not in spoken:
            truck = candidate
            alert_key = candidate_key
            break
    if truck is None or alert_key is None:
        return

    status = truck.get("status")
    reroute = truck.get("reroute") or {}
    target = reroute.get("target") if isinstance(reroute, dict) else None
    if status == "CRITICAL" and target:
        message = (
            f"FrostGuard critical alert. {truck.get('truck_name', truck.get('truck_id'))} temperature "
            f"{truck.get('temperature')} degrees Celsius. Rerouting to {target.get('name')}, {target.get('city')}."
        )
    elif status == "CRITICAL":
        message = (
            f"FrostGuard critical alert. {truck.get('truck_name', truck.get('truck_id'))} temperature "
            f"{truck.get('temperature')} degrees Celsius."
        )
    else:
        message = (
            f"FrostGuard warning. {truck.get('truck_name', truck.get('truck_id'))} temperature rising to "
            f"{truck.get('temperature')} degrees Celsius."
        )

    st.session_state.spoken_alert_keys = spoken + [alert_key]

    components.html(
        f"""
<script>
(function() {{
  const message = {json.dumps(message)};
  if (!("speechSynthesis" in window)) return;
  try {{
    let spoken = false;
    const preferred = [
      /microsoft zira/i, /microsoft jenny/i, /microsoft aria/i,
      /google uk english female/i, /google us english/i,
      /samantha/i, /victoria/i, /karen/i, /tessa/i, /susan/i,
      /hazel/i, /natasha/i, /female/i, /woman/i
    ];
    const pickVoice = () => {{
      const voices = window.speechSynthesis.getVoices() || [];
      return (
        voices.find(v => preferred.some(rx => rx.test(v.name))) ||
        voices.find(v => /^en[-_]/i.test(v.lang) && preferred.some(rx => rx.test(v.name))) ||
        voices.find(v => /^en[-_]/i.test(v.lang)) ||
        voices[0] ||
        null
      );
    }};
    const speak = () => {{
      if (spoken) return true;
      const voice = pickVoice();
      if (!voice && (window.speechSynthesis.getVoices() || []).length === 0) return false;
      spoken = true;
      window.speechSynthesis.cancel();
      const utterance = new SpeechSynthesisUtterance(message);
      if (voice) utterance.voice = voice;
      utterance.lang = voice ? voice.lang : "en-US";
      utterance.rate = 0.94;
      utterance.pitch = 1.08;
      utterance.volume = 1.0;
      window.speechSynthesis.speak(utterance);
      return true;
    }};
    if (!speak()) {{
      window.speechSynthesis.onvoiceschanged = speak;
      setTimeout(speak, 250);
      setTimeout(speak, 900);
    }}
  }} catch (err) {{}}
}})();
</script>
""",
        height=0,
    )


def reset_dashboard_state():
    for k, v in fresh_defaults().items():
        st.session_state[k] = v


def invalidate_dashboard_state():
    st.session_state.last_snapshot_at = 0.0
    st.session_state.last_point_signature = None


def truck_option_label(option, fleet):
    if option == "AUTO":
        return "AUTO — priority alert truck"
    item = next((truck for truck in fleet if truck.get("truck_id") == option), None)
    if not item:
        item = next((truck for truck in FLEET_ROUTES if truck.get("truck_id") == option), None)
    if not item:
        return option
    name = str(item.get("truck_name") or item.get("cargo") or "Truck")
    lead = option if name == option else f"{option} — {name}"
    status = item.get("status")
    temp = item.get("temperature")
    route = f"{item.get('origin', 'Origin')} → {item.get('destination', 'Destination')}"
    live_part = f" · {status} · {temp}°C" if status is not None and temp is not None else ""
    return f"{lead} · {route}{live_part}"


def stable_truck_options(fleet):
    options = ["AUTO"]
    for truck in FLEET_ROUTES:
        truck_id = truck.get("truck_id")
        if truck_id and truck_id not in options:
            options.append(truck_id)
    for truck in fleet:
        truck_id = truck.get("truck_id")
        if truck_id and truck_id not in options:
            options.append(truck_id)
    selected = st.session_state.get("selected_truck_id", "AUTO")
    if selected and selected not in options:
        options.append(selected)
    return options


def selected_truck_for_caption(fleet):
    selected_id = st.session_state.get("selected_truck_id", "AUTO")
    if selected_id and selected_id != "AUTO":
        live = next((truck for truck in fleet if truck.get("truck_id") == selected_id), None)
        if live:
            return live
        configured = next((truck for truck in FLEET_ROUTES if truck.get("truck_id") == selected_id), None)
        if configured:
            fallback = dict(configured)
            fallback.setdefault("status", "CONNECTING")
            fallback.setdefault("temperature", "—")
            fallback.setdefault("distance_travelled_km", "—")
            fallback.setdefault("ml_insight", {})
            return fallback
    return choose_focus_truck(fleet)


def render_truck_selector():
    snapshot = get_dashboard_state(force=True)
    fleet = snapshot.get("fleet", [])
    options = stable_truck_options(fleet)

    left, right = st.columns([1.25, 4.75])
    with left:
        # Clear history when switching trucks to prevent chart spikes
        def handle_truck_change():
            invalidate_dashboard_state()
            st.session_state.temp_history = []
            st.session_state.speed_history = []
            st.session_state.warning_log = []
            
        st.selectbox(
            "Truck",
            options=options,
            key="selected_truck_id",
            format_func=lambda option: truck_option_label(option, fleet),
            on_change=handle_truck_change, 
        )
    with right:
        selected = selected_truck_for_caption(fleet)
        reroute = selected.get("reroute") or {}
        target = reroute.get("target", {}) if isinstance(reroute, dict) else {}
        route_text = f" · KNN reroute to {target.get('name')}, {target.get('city')}" if target else ""
        
        ml_insight = selected.get("ml_insight") or {}
        prediction = ml_insight.get("predicted_temp_30s", selected.get("temperature", "—"))
        
        st.caption(
            f"🚚 {selected.get('truck_name', selected.get('truck_id'))} · {selected.get('truck_id')} · {selected.get('cargo')} · "
            f"{selected.get('origin', 'Origin')} → {selected.get('destination', 'Destination')} · "
            f"{selected.get('distance_travelled_km', 0)} km traveled · "
            f"{selected.get('status', 'WAITING')} · prediction {prediction}°C"
            f"{route_text}"
        )
def render_header():
    s = get_dashboard_state()
    api_ok = s["api_ok"]
    sim_ok = s["sim_ok"]
    d_api = "#4CAF50" if api_ok else "#2A2A2A"
    d_sim = "#4CAF50" if sim_ok else "#2A2A2A"

    h_l, h_r = st.columns([4, 2])
    with h_l:
        st.markdown(
            f'<div style="margin-bottom:0.7rem;">'
            f'<div style="font-family:\'Space Mono\',monospace;font-size:0.62rem;color:#333;letter-spacing:0.18em;">🚚 FLEET ROUTES · COLD CHAIN INTELLIGENCE</div>'
            f'<div style="font-family:\'DM Sans\',sans-serif;font-size:1.45rem;font-weight:800;color:#F2F2F2;margin:2px 0 4px;">FrostGuard AI Command Center</div>'
            f'<span class="dot" style="background:{d_api};"></span>'
            f'<span style="font-size:0.62rem;color:#3A3A3A;font-family:\'Space Mono\',monospace;margin-right:12px;">FastAPI</span>'
            f'<span class="dot" style="background:{d_sim};"></span>'
            f'<span style="font-size:0.62rem;color:#3A3A3A;font-family:\'Space Mono\',monospace;">Simulator</span>'
            f'</div>',
            unsafe_allow_html=True,
        )

    with h_r:
        b1, b2 = st.columns(2)
        with b1:
            if st.button("🚨 Inject Failure", key="btn_fail"):
                st.session_state.failure_until = time.time() + 45
                try:
                    requests.post(f"{API_BASE}/command", json={"command": "compressor_fail"}, timeout=2)
                    st.toast("Failure injected!", icon="🚨")
                except Exception:
                    st.toast("API not reachable", icon="⚠️")
                st.session_state.last_snapshot_at = 0.0
        with b2:
            if st.button("🔄 Reset", key="btn_reset"):
                try:
                    requests.post(f"{API_BASE}/reset", timeout=2)
                except Exception:
                    pass
                reset_dashboard_state()
                st.rerun()


@st.fragment(run_every="4s")
def render_alerts():
    s = get_dashboard_state()
    voice_alert(s)
    if s["is_crit"] and st.session_state.rerouted:
        t = st.session_state.reroute_target
        st.error(f"🚨 CRITICAL {s['temp']}°C — REROUTING TO **{t['name'].upper()}** · {t['city'].upper()}")
    elif s["is_warn"]:
        st.warning(f"⚠️ WARNING — Temperature rising: **{s['temp']}°C** · Compressor activated")
    elif not s["api_ok"]:
        st.info("⏳ Connecting to bridge — dashboard rendering with last known state.")


@st.fragment(run_every="4s")
def render_metrics():
    s = get_dashboard_state()
    ml = s["ml"]
    m1, m2, m3, m4, m5, m6, m7, m8 = st.columns(8)
    m1.metric("📦 Cargo", s["cargo"])
    m2.metric("🌡 Temp", f"{s['temp']}°C", delta=f"{s['temp'] - 4.0:+.1f}°C", delta_color="inverse")
    m3.metric("🔴 Status", s["status"])
    m4.metric("🧠 ML Risk", s["risk"])
    m5.metric("🔬 Anomaly", f"{ml.get('anomaly_score', 0)}%")
    m6.metric("💥 Breach", f"{ml.get('breach_probability', 0)}%")
    m7.metric("🏎 Speed", f"{s['speed_kmh']:.0f} km/h")
    m8.metric("⏱ ETA", "REROUTING 🧊" if st.session_state.rerouted else f"{s['eta_min']} min")


def _legacy_render_fleet_board_unused():
    s = get_dashboard_state()
    cards = []
    for truck in s.get("fleet", []):
        ml = truck.get("ml_insight") or {}
        temp = float(truck.get("temperature", 0.0))
        breach = max(0, min(100, int(float(ml.get("breach_probability", 0)))))
        pred = float(ml.get("predicted_temp_30s", truck.get("temperature", 0)))
        total = max(float(truck.get("route_total_km", 0.0)), 0.1)
        covered = max(0.0, float(truck.get("distance_travelled_km", 0.0)))
        progress = max(0, min(100, int((covered / total) * 100)))
        temp_pct = max(0, min(100, int(((temp - 2.0) / 10.0) * 100)))
        reroute = truck.get("reroute") or {}
        target = reroute.get("target", {}) if isinstance(reroute, dict) else {}
        reroute_text = (
            f"KNN reroute: {target.get('name', 'Cold Store')} · {target.get('city', '')}"
            if target
            else "Planned route stable"
        )
        color = risk_color("CRITICAL" if truck.get("status") == "CRITICAL" else ml.get("risk_level", "LOW"))
        selected_style = "border-color:#2D9CFF;background:#0B0B0B;" if truck.get("truck_id") == s.get("truck_id") else ""
        cards.append(
            f'<div class="fleet-card" style="--c:{color};--p:{progress}%;--temp:{temp_pct}%;--breach:{breach}%;{selected_style}">'
            f'  <div class="fleet-card-top">'
            f'    <div><div class="fleet-name">{html.escape(str(truck.get("truck_name", truck.get("truck_id", ""))))}</div>'
            f'    <div class="fleet-id">{html.escape(str(truck.get("truck_id", "")))}</div></div>'
            f'    <div class="fleet-status">{html.escape(str(truck.get("status", "SAFE")))}</div>'
            f'  </div>'
            f'  <div class="fleet-meta">{html.escape(str(truck.get("cargo", "")))} · '
            f'{html.escape(str(truck.get("origin", "Origin")))} → {html.escape(str(truck.get("destination", "Destination")))}</div>'
            f'  <div class="route-track"><div class="route-fill"></div><div class="route-vehicle"></div></div>'
            f'  <div class="fleet-stat-row">'
            f'    <div><div class="fleet-stat-label">Covered</div><div class="fleet-stat-value">{covered:.1f}/{total:.1f} km</div></div>'
            f'    <div><div class="fleet-stat-label">Progress</div><div class="fleet-stat-value">{progress}%</div></div>'
            f'  </div>'
            f'  <div class="fleet-stat-row">'
            f'    <div><div class="fleet-stat-label">Live Temp</div><div class="fleet-stat-value">{temp:.1f}°C</div><div class="meter-track"><div class="temp-fill"></div></div></div>'
            f'    <div><div class="fleet-stat-label">Breach</div><div class="fleet-stat-value">{breach}%</div><div class="meter-track"><div class="breach-fill"></div></div></div>'
            f'  </div>'
            f'  <div class="fleet-stat-row">'
            f'    <div><div class="fleet-stat-label">Prediction</div><div class="fleet-stat-value">{pred:.1f}°C</div></div>'
            f'    <div><div class="fleet-stat-label">Speed</div><div class="fleet-stat-value">{float(truck.get("speed_kmh", 0.0)):.0f} km/h</div></div>'
            f'  </div>'
            f'  <div class="fleet-reroute">{html.escape(reroute_text)}</div>'
            f'</div>'
        )

    st.markdown(
        '<div class="fleet-board">'
        '<div class="fg-card-title">🚚 Live Fleet Details</div>'
        f'<div class="fleet-card-grid">{"".join(cards)}</div>'
        '</div>',
        unsafe_allow_html=True,
    )


@st.fragment(run_every="15s")
def render_map():
    s = get_dashboard_state()
    layers = []

    for idx, item in enumerate(FLEET_ROUTES):
        route = st.session_state.fleet_routes.get(item["truck_id"], [])
        if route:
            path = [[lo, la] for la, lo in route]
            layers.append(pdk.Layer(
                "PathLayer", data=[{"path": path}], get_path="path",
                get_color=[0, 130, 255, 42 + idx * 8],
                width_scale=9, width_min_pixels=2,
            ))

    main_path = [[lo, la] for la, lo in st.session_state.main_route]
    layers.append(pdk.Layer(
        "PathLayer", data=[{"path": main_path}], get_path="path",
        get_color=[25, 65, 190, 55] if st.session_state.rerouted else [0, 130, 255, 110],
        width_scale=13, width_min_pixels=3,
    ))

    if st.session_state.rerouted and st.session_state.active_route:
        rr_path = [[lo, la] for la, lo in st.session_state.active_route]
        layers.append(pdk.Layer(
            "PathLayer", data=[{"path": rr_path}], get_path="path",
            get_color=[255, 95, 0, 230], width_scale=15, width_min_pixels=4,
        ))

    layers.append(pdk.Layer(
        "ScatterplotLayer",
        data=[{"lat": c["lat"], "lon": c["lon"], "name": c["name"], "city": c["city"]} for c in COLD_STORAGES],
        get_position="[lon, lat]", get_color=[0, 195, 255, 175],
        get_radius=500, radiusMinPixels=8, pickable=True,
    ))

    if st.session_state.rerouted and st.session_state.reroute_target:
        t = st.session_state.reroute_target
        layers.append(pdk.Layer(
            "ScatterplotLayer", data=[{"lat": t["lat"], "lon": t["lon"]}],
            get_position="[lon, lat]", get_color=[255, 50, 50, 50],
            get_radius=1600, radiusMinPixels=24,
        ))

    truck_points = []
    for item in s.get("fleet", [s["telemetry"]]):
        status = item.get("status", "SAFE")
        color = [255, 35, 35, 255] if status == "CRITICAL" else ([255, 160, 0, 255] if status == "WARNING" else [0, 215, 95, 255])
        selected = item.get("truck_id") == s["truck_id"]
        truck_points.append({
            "lat": float(item.get("lat", START_LAT)),
            "lon": float(item.get("lng", START_LON)),
            "truck_id": item.get("truck_id", ""),
            "cargo": item.get("cargo", ""),
            "temperature": item.get("temperature", ""),
            "status": status,
            "color": color,
            "radius": 360 if selected else 230,
        })

    layers.append(pdk.Layer(
        "ScatterplotLayer", data=truck_points,
        get_position="[lon, lat]", get_color="color",
        get_radius="radius", radiusMinPixels=9, radiusMaxPixels=22,
        pickable=True,
    ))

    st.pydeck_chart(pdk.Deck(
        layers=layers,
        initial_view_state=pdk.ViewState(latitude=s["lat"], longitude=s["lon"], zoom=10, pitch=50),
        map_style="https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json",
        tooltip={"text": "📍 {name}{truck_id}\n{city}{cargo} {temperature}°C {status}"},
    ))


@st.fragment(run_every="6s")
def render_details():
    s = get_dashboard_state()
    ml = s["ml"]
    temp = s["temp"]
    risk = s["risk"]
    rc = s["rc"]

    c1, c2, c3, c4 = st.columns([1, 1, 1.15, 1])
    _waiting_html = '<div style="height:105px;display:flex;align-items:center;justify-content:center;color:#2A2A2A;font-family:\'Space Mono\',monospace;font-size:0.7rem;">WAITING FOR DATA</div>'

    with c1:
        st.markdown('<div class="fg-card"><div class="fg-card-title">⚡ Speed km/h</div>', unsafe_allow_html=True)
        if st.session_state.speed_history:
            st.line_chart({"km/h": st.session_state.speed_history}, height=105)
        else:
            st.markdown(_waiting_html, unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)

    with c2:
        st.markdown('<div class="fg-card"><div class="fg-card-title">🌡 Temperature °C</div>', unsafe_allow_html=True)
        if st.session_state.temp_history:
            st.line_chart({"°C": st.session_state.temp_history}, height=105)
        else:
            st.markdown(_waiting_html, unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)

    with c3:
        forecast = ml.get("forecast_series", [])
        anomaly_s = ml.get("anomaly_score", 0)
        breach_p = ml.get("breach_probability", 0)
        rec = ml.get("recommendation", "Monitoring…")
        time_crit = ml.get("time_to_critical_sec")
        pred_temp = ml.get("predicted_temp_30s", temp)
        train_rows = ml.get("training_rows", 0)
        is_anomaly = ml.get("anomaly", False)

        bars_html = ""
        if forecast:
            max_f = max(max(forecast), 0.1)
            for v in forecast:
                h = max(int((v / max_f) * 34), 3)
                bc = risk_color("CRITICAL" if v > CRITICAL_AT else ("HIGH" if v > SAFE_MAX else "LOW"))
                bars_html += f'<div class="bar" style="height:{h}px;background:{bc};"></div>'

        tc_html = f"<b style='color:{rc}'>{time_crit}s</b>" if time_crit else "<span style='color:#2A2A2A'>—</span>"
        anom_html = "<b style='color:#FF3B3B'>YES</b>" if is_anomaly else "<b style='color:#4CAF50'>NO</b>"
        pred_rc = risk_color("CRITICAL" if pred_temp > CRITICAL_AT else ("HIGH" if pred_temp > SAFE_MAX else "LOW"))

        st.markdown(
            f'<div class="fg-card">'
            f'<div class="fg-card-title">🧠 Isolation Forest + Linear Forecast</div>'
            f'<div style="display:flex;align-items:center;gap:8px;margin-bottom:10px;">'
            f'  <span class="risk-badge risk-{risk}">{risk}</span>'
            f'  <span style="font-size:0.6rem;color:#3A3A3A;font-family:\'Space Mono\',monospace;">{train_rows} training rows</span>'
            f'</div>'
            f'<div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:5px;margin-bottom:10px;">'
            f'  <div style="background:#0D0D0D;border:1px solid #181818;border-radius:7px;padding:7px 9px;">'
            f'    <div style="font-size:0.55rem;color:#3A3A3A;text-transform:uppercase;letter-spacing:0.1em;margin-bottom:3px;font-family:\'Space Mono\',monospace;">Anomaly Score</div>'
            f'    <div style="font-size:1.05rem;font-weight:800;color:{rc};">{anomaly_s}%</div>'
            f'  </div>'
            f'  <div style="background:#0D0D0D;border:1px solid #181818;border-radius:7px;padding:7px 9px;">'
            f'    <div style="font-size:0.55rem;color:#3A3A3A;text-transform:uppercase;letter-spacing:0.1em;margin-bottom:3px;font-family:\'Space Mono\',monospace;">Breach Prob</div>'
            f'    <div style="font-size:1.05rem;font-weight:800;color:{rc};">{breach_p}%</div>'
            f'  </div>'
            f'  <div style="background:#0D0D0D;border:1px solid #181818;border-radius:7px;padding:7px 9px;">'
            f'    <div style="font-size:0.55rem;color:#3A3A3A;text-transform:uppercase;letter-spacing:0.1em;margin-bottom:3px;font-family:\'Space Mono\',monospace;">Pred. 30s</div>'
            f'    <div style="font-size:1.05rem;font-weight:800;color:{pred_rc};">{pred_temp}°C</div>'
            f'  </div>'
            f'</div>'
            f'<div style="font-size:0.55rem;color:#3A3A3A;text-transform:uppercase;letter-spacing:0.1em;margin-bottom:3px;font-family:\'Space Mono\',monospace;">10-step temp forecast (3s/step)</div>'
            f'<div class="bars-wrap">'
            f'  {bars_html if bars_html else "<span style=\'color:#2A2A2A;font-size:0.68rem;font-family:Space Mono;\'>NO FORECAST YET</span>"}'
            f'</div>'
            f'<div style="display:flex;gap:14px;margin-top:8px;">'
            f'  <div style="font-size:0.65rem;color:#555;">Anomaly: {anom_html}</div>'
            f'  <div style="font-size:0.65rem;color:#555;">To critical: {tc_html}</div>'
            f'</div>'
            f'<div style="margin-top:8px;padding:8px 10px;background:#050505;border:1px solid #141414;border-radius:7px;">'
            f'  <div style="font-size:0.55rem;color:#3A3A3A;text-transform:uppercase;letter-spacing:0.1em;margin-bottom:3px;font-family:\'Space Mono\',monospace;">ML Recommendation</div>'
            f'  <div style="font-size:0.72rem;color:#ABABAB;line-height:1.5;">{rec}</div>'
            f'</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

    with c4:
        st.markdown('<div class="fg-card"><div class="fg-card-title">📋 Event Log</div>', unsafe_allow_html=True)
        if st.session_state.warning_log:
            for ev in st.session_state.warning_log[:7]:
                c = ev.get("color", "#333")
                st.markdown(
                    f'<div class="ev-item" style="--c:{c};">'
                    f'<div class="ev-time">{ev["time"]}</div>'
                    f'<div class="ev-msg">{ev["icon"]} {ev["msg"]}</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
        else:
            st.markdown(
                '<div class="ev-item" style="--c:#0e2e18;">'
                '<div class="ev-msg">✅ All systems nominal</div>'
                '</div>',
                unsafe_allow_html=True,
            )
        st.markdown('</div>', unsafe_allow_html=True)

    st.markdown("<div style='height:0.3rem'></div>", unsafe_allow_html=True)
    f1, f2, f3, f4 = st.columns(4)
    dest = st.session_state.reroute_target["city"] if st.session_state.rerouted else "Ahmedabad"
    f1.caption(f"📍 {s['lat']:.5f}°N  {s['lon']:.5f}°E")
    f2.caption(f"🏁 Destination: {dest}")
    f3.caption(f"🛣 {'NH48 → Emergency Reroute' if st.session_state.rerouted else 'NH48  Vadodara → Ahmedabad'}")
    f4.caption(f"📊 WP {st.session_state.waypoint_idx}  ·  {st.session_state.dist_covered:.1f} km covered")


@st.fragment(run_every="6s")
def render_fleet_board():
    s = get_dashboard_state()
    cards = []

    for index, truck in enumerate(s.get("fleet", [])):
        truck = attach_dataset_context(dict(truck), dataset_sample_for_truck(index))
        ml = truck.get("ml_insight") or {}
        temp = safe_float(truck.get("temperature"), safe_float(truck.get("data_temperature"), 0.0))
        breach = max(0, min(100, int(safe_float(ml.get("breach_probability"), 0))))
        pred = safe_float(ml.get("predicted_temp_30s"), temp)
        total = max(safe_float(truck.get("route_total_km"), 0.0), 0.1)
        covered = max(0.0, safe_float(truck.get("distance_travelled_km"), 0.0))
        remaining = max(0.0, safe_float(truck.get("distance_remaining_km"), total - covered))
        progress = max(0, min(100, int((covered / total) * 100)))
        temp_pct = max(0, min(100, int(((temp - 2.0) / 10.0) * 100)))
        status = str(truck.get("status", "SAFE"))
        temp_min = safe_float(truck.get("temp_min"), temp)
        temp_max = safe_float(truck.get("temp_max"), temp)
        health_index = safe_float(truck.get("health_index"), 0.0)
        health_pct = int(round(health_index * 100 if health_index <= 1 else health_index))
        humidity = safe_float(truck.get("hum_mean"), 0.0)
        handling = safe_float(truck.get("handling_stress"), 0.0)
        door_idx = safe_float(truck.get("door_count"), 0.0)
        accel = safe_float(truck.get("accel_rms"), 0.0)
        above_6 = safe_float(truck.get("frac_temp_above_6"), 0.0)
        product = str(truck.get("product_type") or truck.get("cargo", ""))
        blood = str(truck.get("blood_type") or "")
        bag = str(truck.get("bag_id") or "")
        data_route = str(truck.get("data_route") or "")
        data_ts = str(truck.get("data_timestamp") or "")
        source = str(truck.get("dataset_source") or "live bridge")
        product_label = f"{product} {blood}".strip()
        source_bits = [bit for bit in (bag, product_label, data_route) if bit]
        source_line = " · ".join(source_bits) if source_bits else "Live bridge telemetry"
        source_meta = f"{source} {data_ts[:16]}".strip()

        reroute = truck.get("reroute") or {}
        target = reroute.get("target", {}) if isinstance(reroute, dict) else {}
        if target:
            target_name = str(target.get("name", "Cold Store"))
            target_city = str(target.get("city", ""))
            reroute_text = f"KNN reroute: {target_name}" + (f", {target_city}" if target_city else "")
        else:
            reroute_text = "Planned route stable"

        color_key = "CRITICAL" if status == "CRITICAL" else ("MEDIUM" if status == "WARNING" else ml.get("risk_level", "LOW"))
        color = risk_color(color_key)
        selected_style = "border-color:#2D9CFF;background:#0B0B0B;" if truck.get("truck_id") == s.get("truck_id") else ""
        truck_id = str(truck.get("truck_id", ""))
        display_name = str(truck.get("truck_name") or truck_id)
        sub_label = f'{truck.get("origin", "Origin")} → {truck.get("destination", "Destination")}' if display_name == truck_id else truck_id

        cards.append(
            f'<div class="fleet-card" style="--c:{color};--p:{progress}%;--temp:{temp_pct}%;--breach:{breach}%;{selected_style}">'
            f'  <div class="fleet-card-top">'
            f'    <div><div class="fleet-name">{html.escape(display_name)}</div>'
            f'    <div class="fleet-id">{html.escape(str(sub_label))}</div></div>'
            f'    <div class="fleet-status">{html.escape(status)}</div>'
            f'  </div>'
            f'  <div class="fleet-meta">{html.escape(str(truck.get("cargo", "")))} · '
            f'{html.escape(str(truck.get("origin", "Origin")))} → {html.escape(str(truck.get("destination", "Destination")))}</div>'
            f'  <div class="fleet-note">{html.escape(source_line)}'
            f'    <span style="color:#3A3A3A;"> · {html.escape(source_meta)}</span></div>'
            f'  <div class="route-track"><div class="route-fill"></div><div class="route-vehicle"></div></div>'
            f'  <div class="fleet-stat-row">'
            f'    <div><div class="fleet-stat-label">Covered</div><div class="fleet-stat-value">{covered:.1f}/{total:.1f} km</div></div>'
            f'    <div><div class="fleet-stat-label">Remaining</div><div class="fleet-stat-value">{remaining:.1f} km</div></div>'
            f'  </div>'
            f'  <div class="fleet-stat-row">'
            f'    <div><div class="fleet-stat-label">Live Temp</div><div class="fleet-stat-value">{temp:.1f}°C</div><div class="meter-track"><div class="temp-fill"></div></div></div>'
            f'    <div><div class="fleet-stat-label">Temp Range</div><div class="fleet-stat-value">{temp_min:.1f}-{temp_max:.1f}°C</div></div>'
            f'  </div>'
            f'  <div class="fleet-stat-row">'
            f'    <div><div class="fleet-stat-label">Prediction</div><div class="fleet-stat-value">{pred:.1f}°C</div></div>'
            f'    <div><div class="fleet-stat-label">Speed</div><div class="fleet-stat-value">{safe_float(truck.get("speed_kmh"), 0.0):.0f} km/h</div></div>'
            f'  </div>'
            f'  <div class="fleet-evidence">'
            f'    <div class="fleet-evidence-item"><div class="fleet-stat-label">Health</div><div class="fleet-stat-value">{health_pct}%</div></div>'
            f'    <div class="fleet-evidence-item"><div class="fleet-stat-label">Humidity</div><div class="fleet-stat-value">{humidity:.1f}%</div></div>'
            f'    <div class="fleet-evidence-item"><div class="fleet-stat-label">Breach</div><div class="fleet-stat-value">{breach}%</div></div>'
            f'    <div class="fleet-evidence-item"><div class="fleet-stat-label">Handling</div><div class="fleet-stat-value">{handling:.2f}</div></div>'
            f'    <div class="fleet-evidence-item"><div class="fleet-stat-label">Door idx</div><div class="fleet-stat-value">{door_idx:.2f}</div></div>'
            f'    <div class="fleet-evidence-item"><div class="fleet-stat-label">Accel RMS</div><div class="fleet-stat-value">{accel:.3f}</div></div>'
            f'  </div>'
            f'  <div class="fleet-note">Above 6°C fraction: {above_6:.2f}</div>'
            f'  <div class="fleet-reroute">{html.escape(reroute_text)}</div>'
            f'</div>'
        )

    st.markdown(
        '<div class="fleet-board">'
        '<div class="fg-card-title">ðŸšš Live Fleet Details</div>'
        f'<div class="fleet-card-grid">{"".join(cards)}</div>'
        '</div>',
        unsafe_allow_html=True,
    )


def render_dashboard():
    ensure_services()
    ensure_routes()
    render_truck_selector()
    render_header()
    render_alerts()
    render_metrics()
    st.markdown("<div style='height:0.5rem'></div>", unsafe_allow_html=True)
    render_map()
    st.markdown("<div style='height:0.5rem'></div>", unsafe_allow_html=True)
    render_fleet_board()
    st.markdown("<div style='height:0.5rem'></div>", unsafe_allow_html=True)
    render_details()


render_dashboard()
