"""
FrostGuard AI - Bridge Server
Runs locally on port 5000 and is auto-started by main_dashboard.py.
"""
from __future__ import annotations

import csv
import json
import math
import os
import signal
import time
import warnings
from datetime import datetime
from typing import Any

import joblib
import requests as http_requests
from flask import Flask, jsonify, request
try:
    from supabase import create_client
except Exception:
    create_client = None

from frost_ml import FrostGuardML

app = Flask(__name__)
warnings.filterwarnings("ignore", category=UserWarning, module="sklearn")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CSV_FILE = os.environ.get("FLEET_CSV", os.path.join(BASE_DIR, "fleet_logs.csv"))
DISCORD_WEBHOOK = os.environ.get("DISCORD_WEBHOOK", "")
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_KEY", "")
SAFE_MAX = 6.5
CRITICAL_AT = 8.0

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
    os.path.join(BASE_DIR, "config", "frostguard_config.json"),
    r"C:\Users\lenovo\OneDrive\Desktop\python\python for computer graphics\LAB11\FrostGuard_Final_Project\config\frostguard_config.json",
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


def _load_fleet_config() -> list[dict[str, Any]]:
    for path in FLEET_CONFIG_CANDIDATES:
        if not os.path.exists(path):
            continue
        try:
            with open(path, "r", encoding="utf-8") as f:
                fleet = json.load(f).get("fleet", [])
            if isinstance(fleet, list) and fleet:
                return fleet
        except Exception:
            continue
    return DEFAULT_FLEET_CONFIG


def _build_fleet_routes() -> list[dict[str, Any]]:
    routes: list[dict[str, Any]] = []
    for index, item in enumerate(_load_fleet_config()):
        route_text = str(item.get("route", "Vadodara -> Ahmedabad"))
        if "->" in route_text:
            origin, destination = [part.strip() for part in route_text.split("->", 1)]
        else:
            origin, destination = "Vadodara", "Ahmedabad"
        start = CITY_COORDS.get(origin, (22.3072, 73.1812))
        end = CITY_COORDS.get(destination, (23.0225, 72.5714))
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


FLEET_ROUTES = _build_fleet_routes()

KNN_FEATURES = [
    "temperature",
    "temp_min",
    "temp_max",
    "temp_std",
    "frac_temp_above_6",
    "frac_temp_above_8",
    "hum_mean",
    "hum_std",
    "door_count",
    "accel_rms",
    "handling_stress",
    "health_index",
    "ambient_temp_c",
    "ambient_humidity_pct",
    "weather_risk_index",
]

_state: dict[str, Any] = {
    "latest": None,
    "fleet": {},
    "predictions": {},
    "command": {"command": "normal"},
    "sim_pid": None,
    "sim_started_at": time.time(),
    "last_supabase_sync": 0.0,
}

_DATASET_CANDIDATES = [
    os.environ.get("DATASET_PATH", ""),
    os.path.join(BASE_DIR, "data", "healthcare_iot_target_dataset.csv"),
    os.path.join(BASE_DIR, "healthcare_iot_target_dataset.csv"),
    r"C:\Users\lenovo\OneDrive\Desktop\python\python for computer graphics\LAB11\FrostGuard_Final_Project\data\healthcare_iot_target_dataset.csv",
    r"C:\Users\lenovo\OneDrive\Desktop\FrostGaurd engine\healthcare_iot_target_dataset.csv",
]
DATASET_PATH = next((p for p in _DATASET_CANDIDATES if p and os.path.exists(p)), None)
_DATASET_ROWS: list[dict[str, Any]] | None = None

_ML = None
_ML_READY = False
_KNN = None
_KNN_READY = False
_SUPABASE = None
_SUPABASE_READY = False


def _load_ml():
    global _ML, _ML_READY
    if _ML is not None:
        return _ML if _ML else None
    try:
        _ML = FrostGuardML(csv_path=CSV_FILE, dataset_path=DATASET_PATH, training_sample_rows=5000)
        _ML_READY = bool(getattr(_ML, "is_trained", False))
        return _ML
    except Exception:
        _ML = False
        _ML_READY = False
        return None


def _load_supabase():
    global _SUPABASE, _SUPABASE_READY
    if _SUPABASE is not None:
        return _SUPABASE
    if not create_client or not SUPABASE_URL or not SUPABASE_KEY:
        _SUPABASE = False
        _SUPABASE_READY = False
        return None
    try:
        _SUPABASE = create_client(SUPABASE_URL, SUPABASE_KEY)
        _SUPABASE_READY = True
        return _SUPABASE
    except Exception:
        _SUPABASE = False
        _SUPABASE_READY = False
        return None


def _sync_supabase(table: str, row: dict[str, Any]) -> None:
    client = _load_supabase()
    if not client:
        return
    try:
        client.table(table).insert(row).execute()
    except Exception:
        pass


def _load_knn():
    global _KNN, _KNN_READY
    if _KNN is not None:
        return _KNN
    artifact = os.path.join(BASE_DIR, "frostguard_knn.joblib")
    try:
        _KNN = joblib.load(artifact) if os.path.exists(artifact) else False
        _KNN_READY = bool(_KNN)
    except Exception:
        _KNN = False
        _KNN_READY = False
    return _KNN


def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dlon / 2) ** 2
    )
    return radius * 2 * math.asin(math.sqrt(a))


def _route_distance_km(route: dict[str, Any]) -> float:
    slat, slon = route["start"]
    elat, elon = route["end"]
    return _haversine(slat, slon, elat, elon) * 1.16


def _status_from_temp(temp: float) -> str:
    if temp >= CRITICAL_AT:
        return "CRITICAL"
    if temp > SAFE_MAX:
        return "WARNING"
    return "SAFE"


def _safe_float(value: Any, default: float = 0.0) -> float:
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


def _normalise_dataset_row(row: dict[str, Any]) -> dict[str, Any]:
    temp_mean = _safe_float(row.get("temp_mean"), 5.0)
    temp_min = _safe_float(row.get("temp_min"), temp_mean)
    temp_max = _safe_float(row.get("temp_max"), temp_mean)
    data_temp = temp_max if temp_max > 0 else temp_mean
    health_index = _safe_float(row.get("Health_Index", row.get("health_index")), 0.98)
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
        "temp_std": round(_safe_float(row.get("temp_std"), 0.0), 3),
        "frac_temp_above_6": round(_safe_float(row.get("frac_temp_above_6"), 0.0), 3),
        "frac_temp_above_8": round(_safe_float(row.get("frac_temp_above_8"), 0.0), 3),
        "hum_mean": round(_safe_float(row.get("hum_mean"), 58.0), 1),
        "hum_std": round(_safe_float(row.get("hum_std"), 2.5), 2),
        "door_count": round(_safe_float(row.get("door_count"), 0.0), 2),
        "accel_rms": round(_safe_float(row.get("accel_rms"), 0.04), 3),
        "handling_stress": round(_safe_float(row.get("handling_stress"), 0.45), 3),
        "health_index": round(max(0.0, min(1.0, health_index)), 3),
        "dataset_source": os.path.basename(DATASET_PATH or ""),
    }


def _dataset_rows() -> list[dict[str, Any]]:
    global _DATASET_ROWS
    if _DATASET_ROWS is not None:
        return _DATASET_ROWS
    rows: list[dict[str, Any]] = []
    if DATASET_PATH:
        try:
            with open(DATASET_PATH, newline="", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                for row_no, row in enumerate(reader):
                    if row_no % 48 != 0:
                        continue
                    rows.append(_normalise_dataset_row(row))
                    if len(rows) >= 1200:
                        break
        except Exception:
            rows = []
    _DATASET_ROWS = rows
    return _DATASET_ROWS


def _dataset_row_for(index: int, elapsed: float) -> dict[str, Any]:
    rows = _dataset_rows()
    if not rows:
        return {}
    tick = int(max(elapsed, 0.0) / 2.0)
    return rows[(tick + index * 37) % len(rows)]


def _default_ml(temp: float) -> dict[str, Any]:
    pressure = max(temp - SAFE_MAX, 0.0)
    risk = "CRITICAL" if temp >= CRITICAL_AT else ("HIGH" if temp > SAFE_MAX + 0.7 else ("MEDIUM" if temp > SAFE_MAX else "LOW"))
    forecast = [round(temp + math.sin(i / 2) * 0.08 + pressure * i * 0.05, 2) for i in range(1, 11)]
    return {
        "model": "fallback",
        "trained": False,
        "training_rows": 0,
        "anomaly": pressure > 1.1,
        "anomaly_score": int(min(100, pressure * 42)),
        "risk_level": risk,
        "breach_probability": int(min(100, pressure / max(CRITICAL_AT - SAFE_MAX, 0.1) * 78)),
        "predicted_temp_30s": round(forecast[-1] if forecast else temp, 2),
        "forecast_series": forecast,
        "time_to_critical_sec": 0 if temp >= CRITICAL_AT else None,
        "recommendation": "Monitoring local bridge telemetry.",
    }


def _append_csv(row: dict[str, Any]) -> None:
    try:
        exists = os.path.isfile(CSV_FILE)
        with open(CSV_FILE, mode="a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            if not exists:
                writer.writerow(["Truck_ID", "Cargo", "Current_Temp", "Status", "Lat", "Lng", "Timestamp"])
            writer.writerow([
                row.get("truck_id", ""),
                row.get("cargo", ""),
                row.get("temperature", ""),
                row.get("status", ""),
                row.get("lat", ""),
                row.get("lng", ""),
                row.get("timestamp", ""),
            ])
    except Exception:
        pass


def _discord(data: dict[str, Any]) -> None:
    if not DISCORD_WEBHOOK or "discord.com" not in DISCORD_WEBHOOK:
        return
    try:
        http_requests.post(
            DISCORD_WEBHOOK,
            json={"content": f"FROSTGUARD ALERT: {data.get('truck_id')} {data.get('temperature')}C CRITICAL"},
            timeout=4,
        )
    except Exception:
        pass


def _knn_vector(data: dict[str, Any], temp_override: float | None = None) -> list[float]:
    temp = float(temp_override if temp_override is not None else data.get("temperature", 5.0))
    return [
        temp,
        float(data.get("temp_min", min(temp, float(data.get("temperature", temp))))),
        float(data.get("temp_max", max(temp, float(data.get("temperature", temp))))),
        float(data.get("temp_std", 0.12)),
        float(data.get("frac_temp_above_6", 1.0 if temp > 6.0 else 0.0)),
        float(data.get("frac_temp_above_8", 1.0 if temp > CRITICAL_AT else 0.0)),
        float(data.get("hum_mean", 58.0)),
        float(data.get("hum_std", 2.5)),
        float(data.get("door_count", 0.0)),
        float(data.get("accel_rms", 0.04)),
        float(data.get("handling_stress", 0.45)),
        float(data.get("health_index", max(0.45, 1.0 - max(temp - 4.5, 0) * 0.04))),
        float(data.get("ambient_temp_c", 31.0)),
        float(data.get("ambient_humidity_pct", 58.0)),
        float(data.get("weather_risk_index", min(1.0, 0.35 + max(temp - SAFE_MAX, 0) * 0.08))),
    ]


def _knn_breach_risk(data: dict[str, Any], temp_override: float | None = None) -> float:
    model = _load_knn()
    temp = float(temp_override if temp_override is not None else data.get("temperature", 5.0))
    fallback = min(1.0, max(0.0, (temp - SAFE_MAX) / max(CRITICAL_AT - SAFE_MAX, 0.1)))
    if not model:
        return fallback

    try:
        vector = [_knn_vector(data, temp_override)]
        if hasattr(model, "predict_proba"):
            proba = model.predict_proba(vector)
            classes = getattr(getattr(model, "pipeline", model), "classes_", [0, 1])
            idx = list(classes).index(1) if 1 in list(classes) else -1
            return float(proba[0][idx])
        return float(model.predict(vector)[0])
    except Exception:
        return fallback


def _knn_reroute(data: dict[str, Any]) -> dict[str, Any] | None:
    temp = float(data.get("temperature", 5.0))
    status = data.get("status") or _status_from_temp(temp)
    if status != "CRITICAL" and temp < CRITICAL_AT:
        return None

    lat = float(data.get("lat", 0.0))
    lon = float(data.get("lng", data.get("lon", 0.0)))
    best: dict[str, Any] | None = None
    for storage in COLD_STORAGES:
        distance = _haversine(lat, lon, storage["lat"], storage["lon"])
        projected_temp = min(12.0, temp + (distance / 70.0) * 0.18)
        risk = _knn_breach_risk(data, projected_temp)
        score = risk * 100.0 + distance * 0.55
        candidate = {
            "target": storage,
            "distance_km": round(distance, 2),
            "projected_temp_c": round(projected_temp, 2),
            "knn_breach_risk": round(risk, 3),
            "score": round(score, 3),
            "method": "KNN" if _KNN_READY else "KNN fallback",
        }
        if best is None or candidate["score"] < best["score"]:
            best = candidate
    return best


def _normalise_payload(payload: dict[str, Any]) -> dict[str, Any]:
    data = dict(payload)
    temp = float(data.get("temperature", 5.0))
    data.setdefault("truck_id", "TRK-RD-001")
    data.setdefault("cargo", "Vaccines")
    data["temperature"] = temp
    data.setdefault("status", _status_from_temp(temp))
    data.setdefault("lat", 22.3072)
    data.setdefault("lng", 73.1812)
    data.setdefault("timestamp", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    data.setdefault("speed_kmh", 68.0)
    data.setdefault("hum_mean", 58.0)
    data.setdefault("door_count", 0.0)
    data.setdefault("accel_rms", 0.04)
    data.setdefault("handling_stress", 0.45)
    data.setdefault("health_index", 0.98)
    return data


def _enrich(data: dict[str, Any], run_ml: bool = True) -> dict[str, Any]:
    data = _normalise_payload(data)
    if run_ml:
        ml = _load_ml()
        try:
            data["ml_insight"] = ml.analyze(data) if ml else _default_ml(float(data.get("temperature", 5.0)))
        except Exception:
            data["ml_insight"] = _default_ml(float(data.get("temperature", 5.0)))
    else:
        data["ml_insight"] = _default_ml(float(data.get("temperature", 5.0)))

    reroute = _knn_reroute(data)
    if reroute:
        data["reroute"] = reroute
        data["ml_insight"]["recommendation"] = (
            f"KNN reroute: divert to {reroute['target']['name']}, {reroute['target']['city']} "
            f"({reroute['distance_km']} km)."
        )
    _state["predictions"][data["truck_id"]] = data["ml_insight"]
    return data


def _telemetry_supabase_row(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "truck_id": data.get("truck_id"),
        "cargo": data.get("cargo"),
        "temperature": data.get("temperature"),
        "status": data.get("status"),
        "lat": data.get("lat"),
        "lng": data.get("lng"),
        "timestamp": data.get("timestamp"),
        "speed_kmh": data.get("speed_kmh"),
        "ml_insight": data.get("ml_insight"),
        "reroute": data.get("reroute"),
    }


def _sync_fleet_supabase(fleet: list[dict[str, Any]]) -> None:
    now = time.time()
    if now - float(_state.get("last_supabase_sync", 0.0)) < 15.0:
        return
    _state["last_supabase_sync"] = now
    for item in fleet:
        _sync_supabase("telemetry", _telemetry_supabase_row(item))


def _simulate_fleet() -> list[dict[str, Any]]:
    elapsed = time.time() - float(_state.get("sim_started_at", time.time()))
    command = _state.get("command", {}).get("command", "normal")
    fleet = []

    for idx, route in enumerate(FLEET_ROUTES):
        sample = _dataset_row_for(idx, elapsed)
        route_total = _route_distance_km(route)
        cycle = 260.0 + idx * 22.0 + min(route_total, 600.0) * 0.25
        progress = (((elapsed + float(route.get("start_offset", 0))) / cycle) + idx * 0.025) % 1.0
        slat, slon = route["start"]
        elat, elon = route["end"]
        curve = math.sin(progress * math.pi)
        lat = slat + (elat - slat) * progress + curve * 0.025
        lon = slon + (elon - slon) * progress - curve * 0.018
        wave = math.sin(elapsed / 18.0 + idx * 1.2)
        forced = 3.4 if command == "compressor_fail" and idx in {0, 2} else 0.0
        dataset_temp = _safe_float(sample.get("data_temperature"), 0.0)
        simulated_temp = 4.8 + route["temp_offset"] + wave * 0.45
        temp = round((dataset_temp if dataset_temp > 0 else simulated_temp) + forced, 1)
        speed = round(max(0.0, 66.0 + route["speed_offset"] + math.cos(elapsed / 16.0 + idx) * 5.5), 1)
        travelled = route_total * progress
        payload = {
            "truck_id": route["truck_id"],
            "truck_name": route["truck_name"],
            "cargo": route["cargo"],
            "origin": route["origin"],
            "destination": route["destination"],
            "temperature": temp,
            "status": _status_from_temp(temp),
            "lat": round(lat, 6),
            "lng": round(lon, 6),
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "speed_kmh": speed,
            "progress": round(progress, 4),
            "route_total_km": round(route_total, 2),
            "distance_travelled_km": round(travelled, 2),
            "distance_remaining_km": round(max(route_total - travelled, 0.0), 2),
        }
        payload.update({key: value for key, value in sample.items() if value not in ("", None)})
        data = _enrich(
            payload,
            run_ml=False,
        )
        fleet.append(data)

    _state["fleet"] = {item["truck_id"]: item for item in fleet}
    _state["latest"] = next((item for item in fleet if item["truck_id"] == "TRK-RD-001"), fleet[0])
    _sync_fleet_supabase(fleet)
    return fleet


@app.route("/health")
def health():
    _load_supabase()
    return jsonify(
        {
            "status": "online",
            "bridge": "flask",
            "ml_trained": _ML_READY,
            "training_rows": int(getattr(_ML, "training_rows", 0)) if _ML else 0,
            "knn_ready": _KNN_READY,
            "supabase_ready": _SUPABASE_READY,
            "fleet_size": len(FLEET_ROUTES),
            "has_telemetry": _state["latest"] is not None,
        }
    )


@app.route("/telemetry", methods=["POST"])
def telemetry():
    data = _enrich(dict(request.json or {}))
    _state["latest"] = data
    _state["fleet"][data["truck_id"]] = data
    _append_csv(data)
    _sync_supabase("telemetry", _telemetry_supabase_row(data))
    if data.get("status") == "CRITICAL":
        _discord(data)
    return jsonify({"status": "ok", "risk_level": data["ml_insight"]["risk_level"], "reroute": data.get("reroute")})


@app.route("/latest")
def latest():
    if _state["latest"] is None:
        _simulate_fleet()
    return jsonify(_state["latest"])


@app.route("/fleet")
def fleet():
    return jsonify({"fleet": _simulate_fleet()})


@app.route("/truck/<truck_id>")
def truck_detail(truck_id: str):
    fleet_items = _simulate_fleet()
    truck = next((item for item in fleet_items if item.get("truck_id") == truck_id), None)
    if truck is None:
        return jsonify({"error": "truck not found", "truck_id": truck_id}), 404
    return jsonify(
        {
            "truck": truck,
            "analysis": truck.get("ml_insight", {}),
            "prediction": _state["predictions"].get(truck_id, truck.get("ml_insight", {})),
            "reroute": truck.get("reroute"),
        }
    )


@app.route("/ml_insight")
def ml_insight():
    if _state["latest"] is None:
        _simulate_fleet()
    return jsonify((_state["latest"] or {}).get("ml_insight", _default_ml(5.0)))


@app.route("/predictions")
def predictions():
    if not _state["predictions"]:
        _simulate_fleet()
    return jsonify({"predictions": _state["predictions"]})


@app.route("/summary")
def summary():
    fleet_items = _simulate_fleet()
    return jsonify(
        {
            "fleet_size": len(fleet_items),
            "safe": sum(1 for item in fleet_items if item.get("status") == "SAFE"),
            "warning": sum(1 for item in fleet_items if item.get("status") == "WARNING"),
            "critical": sum(1 for item in fleet_items if item.get("status") == "CRITICAL"),
            "knn_ready": _KNN_READY,
            "supabase_ready": _SUPABASE_READY,
        }
    )


@app.route("/command", methods=["GET"])
def get_command():
    return jsonify(_state["command"])


@app.route("/command", methods=["POST"])
def set_command():
    cmd = (request.json or {}).get("command", "normal")
    _state["command"] = {"command": cmd}
    return jsonify({"status": "ok", "command": cmd})


@app.route("/register_sim", methods=["POST"])
def register_sim():
    _state["sim_pid"] = (request.json or {}).get("pid")
    return jsonify({"status": "registered", "pid": _state["sim_pid"]})


@app.route("/reset", methods=["POST"])
def reset():
    pid = _state.get("sim_pid")
    if pid:
        try:
            os.kill(pid, signal.SIGTERM)
        except Exception:
            pass
    _state["latest"] = None
    _state["fleet"] = {}
    _state["predictions"] = {}
    _state["command"] = {"command": "normal"}
    _state["sim_pid"] = None
    _state["sim_started_at"] = time.time()
    _state["last_supabase_sync"] = 0.0
    return jsonify({"status": "reset_ok"})


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False, use_reloader=False, threaded=True)
