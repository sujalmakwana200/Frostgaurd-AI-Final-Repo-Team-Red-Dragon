from __future__ import annotations
import os
import csv
import math
import time
import signal
import threading
from datetime import datetime
from typing import Any, Optional
import requests as http_requests
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from frost_ml import FrostGuardML

app = FastAPI(title="FrostGuard API", version="2.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CSV_FILE = os.path.join(BASE_DIR, "fleet_logs.csv")
DATASET_PATH = os.path.join(BASE_DIR, "data", "healthcare_iot_target_dataset.csv")

_fleet_state: dict[str, dict] = {}
_latest_telemetry: dict[str, Any] | None = None
_sim_pid: int | None = None
_csv_lock = threading.Lock()

_ml_engine = FrostGuardML(csv_path=CSV_FILE, dataset_path=DATASET_PATH if os.path.exists(DATASET_PATH) else None)

class TelemetryPayload(BaseModel):
    truck_id: str
    cargo: str
    temperature: float
    status: str
    lat: float
    lng: float
    timestamp: str
    speed_kmh: float = Field(default=68.0)
    temp_min: Optional[float] = None
    temp_max: Optional[float] = None
    temp_std: Optional[float] = None
    frac_temp_above_6: Optional[float] = None
    frac_temp_above_8: Optional[float] = None
    hum_mean: Optional[float] = None
    hum_std: Optional[float] = None
    door_count: Optional[float] = None
    accel_rms: Optional[float] = None
    handling_stress: Optional[float] = None
    health_index: Optional[float] = None
    temp_change_rate: Optional[float] = None

def _append_csv(row: dict) -> None:
    with _csv_lock:
        file_exists = os.path.isfile(CSV_FILE)
        with open(CSV_FILE, mode="a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            if not file_exists:
                writer.writerow(["Truck_ID", "Cargo", "Current_Temp", "Status", "Lat", "Lng", "Timestamp"])
            writer.writerow([row["truck_id"], row["cargo"], row["temperature"], row["status"], row["lat"], row["lng"], row["timestamp"]])

def _knn_reroute(data: dict) -> dict | None:
    temp = float(data.get("temperature", 5.0))
    if temp < 8.0:
        return None
    lat, lon = float(data.get("lat", 0.0)), float(data.get("lng", 0.0))
    return {
        "target": {"name": "Emergency Cold Store", "city": "Nearest Facility", "lat": lat + 0.05, "lon": lon + 0.05},
        "distance_km": 5.4,
        "method": "KNN fallback"
    }

@app.post("/telemetry")
def ingest_telemetry(payload: TelemetryPayload):
    global _latest_telemetry
    data = payload.model_dump(exclude_none=True)
    
    data["ml_insight"] = _ml_engine.analyze(data)
    reroute = _knn_reroute(data)
    if reroute:
        data["reroute"] = reroute
        data["ml_insight"]["recommendation"] = f"Reroute to {reroute['target']['name']} immediately."

    data["last_updated"] = time.time()
    _fleet_state[data["truck_id"]] = data
    _latest_telemetry = data
    _append_csv(data)

    return {"status": "ok", "risk_level": data["ml_insight"]["risk_level"]}

@app.get("/latest")
def get_latest():
    return _latest_telemetry

@app.get("/fleet")
def get_fleet():
    # We stripped out the static fake trucks.
    # Now the API ONLY returns trucks that have sent REAL data.
    return {"fleet": list(_fleet_state.values())}

@app.get("/health")
def health():
    return {"status": "online", "api_version": "2.0.0"}

@app.post("/reset")
def reset():
    global _latest_telemetry, _sim_pid
    _fleet_state.clear()
    _latest_telemetry = None
    if hasattr(_ml_engine, 'reset'):
        _ml_engine.reset() 
    return {"status": "reset_ok"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api:app", host="0.0.0.0", port=5000, reload=False)
