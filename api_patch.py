"""
api.py — PATCHED HEADER + MODEL + MAIN BLOCK.

This is a drop-in replacement for three regions of your api.py:
  (1) everything from the first import down to `_ml_engine = ...`
  (2) the TelemetryPayload model
  (3) the `if __name__ == "__main__":` block
Your route bodies in between stay as they are — just add
`dependencies=[Depends(require_api_key)]` to every @app.post (see bottom).
"""
# ───────────────────────── (1) HEADER ─────────────────────────
from __future__ import annotations
import os
import csv
import math
import time
import signal
import logging
import threading
from datetime import datetime
from typing import Any, Optional

import requests as http_requests
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator

from frost_ml import FrostGuardML
from security import require_api_key

log = logging.getLogger("frostguard.api")
logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))

app = FastAPI(title="FrostGuard API", version="2.1.0")

# CORS: only the dashboard origin(s). Override with a comma-separated
# ALLOWED_ORIGINS env var when deploying (e.g. your Render URL).
_ALLOWED_ORIGINS = [
    o.strip()
    for o in os.environ.get(
        "ALLOWED_ORIGINS", "http://localhost:8501,http://127.0.0.1:8501"
    ).split(",")
    if o.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_ALLOWED_ORIGINS,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "X-FrostGuard-Key"],
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CSV_FILE = os.environ.get("FLEET_CSV", os.path.join(BASE_DIR, "fleet_logs.csv"))
DATASET_PATH = os.environ.get(
    "DATASET_PATH", os.path.join(BASE_DIR, "data", "healthcare_iot_target_dataset.csv")
)

_fleet_state: dict[str, dict] = {}
_latest_telemetry: dict[str, Any] | None = None
_sim_pid: int | None = None
_csv_lock = threading.Lock()

_ml_engine = FrostGuardML(
    csv_path=CSV_FILE,
    dataset_path=DATASET_PATH if os.path.exists(DATASET_PATH) else None,
)


# ───────────────────── (2) VALIDATED PAYLOAD ─────────────────────
# Physical bounds: a reefer truck can't be at -200 °C, and Gujarat is not
# at latitude 400. Garbage used to flow straight into the CSV and the
# risk index; now it is rejected with a 422.
_ALLOWED_STATUS = {"SAFE", "WARNING", "CRITICAL", "OK", "ALERT"}


class TelemetryPayload(BaseModel):
    truck_id: str = Field(min_length=1, max_length=32, pattern=r"^[A-Za-z0-9_\-]+$")
    cargo: str = Field(min_length=1, max_length=64)
    temperature: float = Field(ge=-40.0, le=60.0)
    status: str = Field(min_length=1, max_length=16)
    lat: float = Field(ge=-90.0, le=90.0)
    lng: float = Field(ge=-180.0, le=180.0)
    timestamp: str
    speed_kmh: float = Field(default=68.0, ge=0.0, le=200.0)
    temp_min: Optional[float] = Field(default=None, ge=-40.0, le=60.0)
    temp_max: Optional[float] = Field(default=None, ge=-40.0, le=60.0)
    temp_std: Optional[float] = Field(default=None, ge=0.0, le=50.0)
    frac_temp_above_6: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    frac_temp_above_8: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    hum_mean: Optional[float] = Field(default=None, ge=0.0, le=100.0)
    hum_std: Optional[float] = Field(default=None, ge=0.0, le=100.0)
    door_count: Optional[float] = Field(default=None, ge=0.0, le=1000.0)
    accel_rms: Optional[float] = Field(default=None, ge=0.0, le=100.0)
    handling_stress: Optional[float] = Field(default=None, ge=0.0, le=100.0)
    health_index: Optional[float] = Field(default=None, ge=0.0, le=100.0)
    temp_change_rate: Optional[float] = Field(default=None, ge=-50.0, le=50.0)

    @field_validator("status")
    @classmethod
    def _status_upper(cls, v: str) -> str:
        v = v.strip().upper()
        if v not in _ALLOWED_STATUS:
            raise ValueError(f"status must be one of {sorted(_ALLOWED_STATUS)}")
        return v

    @field_validator("timestamp")
    @classmethod
    def _timestamp_iso(cls, v: str) -> str:
        # Accept ISO-8601 (with or without 'Z'); normalise to ISO string.
        try:
            dt = datetime.fromisoformat(v.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("timestamp must be ISO-8601, e.g. 2026-10-13T09:30:00Z") from exc
        return dt.isoformat()


# ─────────────── (3) ROUTE DECORATORS — apply to each POST ───────────────
# Change these three (or however many write routes you have):
#
#   @app.post("/telemetry")                      ->  @app.post("/telemetry", dependencies=[Depends(require_api_key)])
#   @app.post("/command")                        ->  @app.post("/command",   dependencies=[Depends(require_api_key)])
#   @app.post("/reset")  (or whatever it's named) ->  @app.post("/reset",     dependencies=[Depends(require_api_key)])
#
# GET routes (/health, /fleet, /summary ...) stay public — they're read-only.


# ───────────────────────── (4) MAIN BLOCK ─────────────────────────
if __name__ == "__main__":
    import uvicorn

    # Loopback by default. Set API_HOST=0.0.0.0 only behind a reverse proxy / on Render.
    uvicorn.run(
        "api:app",
        host=os.environ.get("API_HOST", "127.0.0.1"),
        port=int(os.environ.get("PORT", os.environ.get("API_PORT", "5000"))),
        reload=False,
    )
