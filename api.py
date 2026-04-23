"""
FrostGuard AI — FastAPI Backend
Replaces the broken bridge.py with a proper async REST API.
Handles: telemetry ingestion, ML inference, command bus, fleet log, health.
"""
from __future__ import annotations

import csv
import os
import signal
from datetime import datetime
from typing import Any

import requests as http_requests
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# ── Local ML engine (unchanged, still works) ──────────────────
from frost_ml import FrostGuardML

app = FastAPI(title="FrostGuard API", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Runtime state ──────────────────────────────────────────────
_latest_telemetry: dict[str, Any] | None = None
_pending_command: dict[str, str] = {"command": "normal"}
_sim_pid: int | None = None

# ── Config ────────────────────────────────────────────────────
CSV_FILE = os.environ.get("FLEET_CSV", "fleet_logs.csv")
DISCORD_WEBHOOK = os.environ.get("DISCORD_WEBHOOK", "")
DATASET_PATH = os.environ.get(
    "DATASET_PATH",
    r"C:\Users\lenovo\OneDrive\Desktop\FrostGaurd engine\healthcare_iot_target_dataset.csv",
)

# ── ML engine singleton ───────────────────────────────────────
_ml_engine = FrostGuardML(
    csv_path=CSV_FILE,
    dataset_path=DATASET_PATH if os.path.exists(DATASET_PATH) else None,
)


# ── Pydantic schemas ──────────────────────────────────────────

class TelemetryPayload(BaseModel):
    truck_id: str
    cargo: str
    temperature: float
    status: str
    lat: float
    lng: float
    timestamp: str
    # Optional enrichment fields (simulator may omit them)
    speed_kmh: float = Field(default=68.0)
    hum_mean: float = Field(default=58.0)
    door_count: float = Field(default=0.0)
    accel_rms: float = Field(default=0.04)
    handling_stress: float = Field(default=0.45)
    health_index: float = Field(default=0.98)


class CommandPayload(BaseModel):
    command: str  # "normal" | "compressor_fail" | "boost_cooling"


class SimRegistration(BaseModel):
    pid: int


# ── Helpers ───────────────────────────────────────────────────

def _append_csv(row: dict) -> None:
    file_exists = os.path.isfile(CSV_FILE)
    with open(CSV_FILE, mode="a", newline="") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(["Truck_ID", "Cargo", "Current_Temp",
                             "Status", "Lat", "Lng", "Timestamp"])
        writer.writerow([
            row["truck_id"], row["cargo"], row["temperature"],
            row["status"], row["lat"], row["lng"], row["timestamp"],
        ])


def _send_discord_alert(data: dict) -> None:
    if not DISCORD_WEBHOOK or "discord.com" not in DISCORD_WEBHOOK:
        return
    msg = {
        "content": (
            f"🐉 **FROSTGUARD ALERT**\n"
            f"Truck `{data['truck_id']}` | Cargo: {data['cargo']}\n"
            f"🌡 Temperature: **{data['temperature']}°C** — CRITICAL\n"
            f"📍 {data['lat']}, {data['lng']}\n"
            f"🕐 {data['timestamp']}"
        )
    }
    try:
        http_requests.post(DISCORD_WEBHOOK, json=msg, timeout=4)
    except Exception:
        pass


# ── Routes ────────────────────────────────────────────────────

@app.post("/register_sim")
def register_sim(payload: SimRegistration):
    global _sim_pid
    _sim_pid = payload.pid
    return {"status": "registered", "pid": _sim_pid}


@app.post("/telemetry")
def ingest_telemetry(payload: TelemetryPayload):
    global _latest_telemetry

    data = payload.model_dump()

    # ML inference — the only part that was working; keep it central
    ml_insight = _ml_engine.analyze(data)
    data["ml_insight"] = ml_insight

    _latest_telemetry = data
    _append_csv(data)

    if data["status"] == "CRITICAL":
        _send_discord_alert(data)

    return {"status": "ok", "risk_level": ml_insight["risk_level"]}


@app.get("/latest")
def get_latest():
    if _latest_telemetry is None:
        raise HTTPException(status_code=404, detail="No telemetry yet")
    return _latest_telemetry


@app.get("/ml_insight")
def get_ml_insight():
    if _latest_telemetry is None or "ml_insight" not in _latest_telemetry:
        raise HTTPException(status_code=404, detail="No ML insight yet")
    return _latest_telemetry["ml_insight"]


@app.get("/command")
def get_command():
    return dict(_pending_command)


@app.post("/command")
def set_command(payload: CommandPayload):
    global _pending_command
    _pending_command = {"command": payload.command}
    return {"status": "ok", "command": payload.command}


@app.get("/health")
def health():
    return {
        "status": "online",
        "api_version": "2.0.0",
        "ml_trained": _ml_engine.is_trained,
        "ml_training_rows": _ml_engine.training_rows,
        "csv": CSV_FILE,
        "has_telemetry": _latest_telemetry is not None,
    }


@app.post("/reset")
def reset():
    global _latest_telemetry, _pending_command, _sim_pid
    if _sim_pid:
        try:
            os.kill(_sim_pid, signal.SIGTERM)
        except Exception:
            pass
        _sim_pid = None
    _latest_telemetry = None
    _pending_command = {"command": "normal"}
    return {"status": "reset_ok"}


# ── Entry point ───────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api:app", host="0.0.0.0", port=5000, reload=False)
