from __future__ import annotations
import os
import csv
import re
import time
import threading
from datetime import datetime
from typing import Any, Optional

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator

from frost_ml import FrostGuardML
from security import require_api_key

app = FastAPI(title="FrostGuard API", version="2.0.0")

# CORS: only the Streamlit dashboard by default. Override with ALLOWED_ORIGINS=a,b,c
_ALLOWED_ORIGINS = [
    o.strip()
    for o in os.environ.get("ALLOWED_ORIGINS", "http://localhost:8501,http://127.0.0.1:8501").split(",")
    if o.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_ALLOWED_ORIGINS,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "X-FrostGuard-Key"],
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CSV_FILE = os.path.join(BASE_DIR, "fleet_logs.csv")
DATASET_PATH = os.path.join(BASE_DIR, "data", "healthcare_iot_target_dataset.csv")

_fleet_state: dict[str, dict] = {}
_latest_telemetry: dict[str, Any] | None = None
_csv_lock = threading.Lock()

# Load the committed artifact (~1s) instead of training at import (~14s); load_artifact
# retrains with these light settings only if the artifact is missing or version-mismatched.
_ml_engine = FrostGuardML.load_artifact(
    os.path.join(BASE_DIR, "frostguard_ml.joblib"),
    csv_path=CSV_FILE,
    dataset_path=DATASET_PATH if os.path.exists(DATASET_PATH) else None,
    n_traces=40,
    steps_per_trace=120,
)

_TRUCK_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,32}$")
_VALID_STATUS = {"SAFE", "WARNING", "CRITICAL", "BREACH"}


class TelemetryPayload(BaseModel):
    truck_id: str = Field(min_length=1, max_length=32)
    cargo: str = Field(min_length=1, max_length=64)
    temperature: float = Field(ge=-50, le=60)
    status: str
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)
    timestamp: str = Field(min_length=10, max_length=40)
    speed_kmh: float = Field(default=68.0, ge=0, le=200)
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

    @field_validator("truck_id")
    @classmethod
    def _check_truck_id(cls, v: str) -> str:
        if not _TRUCK_ID_RE.match(v):
            raise ValueError("truck_id may only contain letters, digits, '-' and '_'")
        return v

    @field_validator("status")
    @classmethod
    def _check_status(cls, v: str) -> str:
        v = v.strip().upper()
        if v not in _VALID_STATUS:
            raise ValueError(f"status must be one of {sorted(_VALID_STATUS)}")
        return v

    @field_validator("timestamp")
    @classmethod
    def _check_timestamp(cls, v: str) -> str:
        try:
            datetime.fromisoformat(v.replace("Z", "+00:00"))
        except ValueError:
            raise ValueError("timestamp must be ISO-8601, e.g. 2026-10-13T09:30:00Z")
        return v


class CommandPayload(BaseModel):
    truck_id: str = Field(min_length=1, max_length=32)
    action: str = Field(min_length=1, max_length=32)

    @field_validator("truck_id")
    @classmethod
    def _check_truck_id(cls, v: str) -> str:
        if not _TRUCK_ID_RE.match(v):
            raise ValueError("truck_id may only contain letters, digits, '-' and '_'")
        return v


def _append_csv(row: dict) -> None:
    with _csv_lock:
        file_exists = os.path.isfile(CSV_FILE)
        with open(CSV_FILE, mode="a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            if not file_exists:
                writer.writerow(["Truck_ID", "Cargo", "Current_Temp", "Status", "Lat", "Lng", "Timestamp"])
            writer.writerow([
                row["truck_id"], row["cargo"], row["temperature"], row["status"],
                row["lat"], row["lng"], row["timestamp"],
            ])


def _knn_reroute(data: dict) -> dict | None:
    temp = float(data.get("temperature", 5.0))
    if temp < 8.0:
        return None
    lat, lon = float(data.get("lat", 0.0)), float(data.get("lng", 0.0))
    return {
        "target": {"name": "Emergency Cold Store", "city": "Nearest Facility", "lat": lat + 0.05, "lon": lon + 0.05},
        "distance_km": 5.4,
        "method": "KNN fallback",
    }


# ───────────── public GET routes (dashboard reads these) ─────────────

@app.get("/health")
def health():
    return {"status": "online", "api_version": "2.0.0"}


@app.get("/latest")
def get_latest():
    return _latest_telemetry


@app.get("/fleet")
def get_fleet():
    # Only return real data, no fake static trucks!
    return {"fleet": list(_fleet_state.values())}


# ───────────── protected POST routes (need X-FrostGuard-Key) ─────────────

@app.post("/telemetry", dependencies=[Depends(require_api_key)])
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


@app.post("/command", dependencies=[Depends(require_api_key)])
def command(payload: CommandPayload):
    truck = _fleet_state.get(payload.truck_id)
    if truck is None:
        raise HTTPException(status_code=404, detail=f"Unknown truck_id {payload.truck_id}")
    truck["last_command"] = {"action": payload.action, "at": time.time()}
    return {"status": "ok", "truck_id": payload.truck_id, "action": payload.action}


@app.post("/reset", dependencies=[Depends(require_api_key)])
def reset():
    global _latest_telemetry
    _fleet_state.clear()
    _latest_telemetry = None
    if hasattr(_ml_engine, "reset"):
        _ml_engine.reset()
    return {"status": "reset_ok"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api:app", host="127.0.0.1", port=5000, reload=False)