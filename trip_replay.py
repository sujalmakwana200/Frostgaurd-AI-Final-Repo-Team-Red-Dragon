from __future__ import annotations
import time
from pathlib import Path
from typing import Any
import pandas as pd
import requests

DATA_FILE = Path(__file__).resolve().parent / "data" / "healthcare_iot_target_dataset.csv"
BRIDGE_URL = "http://127.0.0.1:5000/telemetry"
TRIP_BAG_ID = "BAG_0001"
REPLAY_DELAY_SECONDS = 2

# Waypoints to calculate movement
START_LAT, START_LON = 22.3072, 73.1812
DEST_LAT, DEST_LON = 23.0225, 72.5714

def clean_float(value: Any, default: float = 0.0) -> float:
    numeric = pd.to_numeric(value, errors="coerce")
    return float(default) if pd.isna(numeric) else float(numeric)

def load_trip() -> pd.DataFrame:
    if not DATA_FILE.exists():
        # Fallback to current dir if not in /data/
        alt_path = Path(__file__).resolve().parent / "healthcare_iot_target_dataset.csv"
        if alt_path.exists():
            global DATA_FILE
            DATA_FILE = alt_path
        else:
            raise FileNotFoundError(f"Dataset not found: {DATA_FILE}")

    frame = pd.read_csv(DATA_FILE)
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], errors="coerce")
    frame = frame.dropna(subset=["timestamp"])
    trip = frame.loc[frame["bag_id"].astype(str) == TRIP_BAG_ID].copy()
    return trip.sort_values("timestamp").reset_index(drop=True)

def build_payload(row: pd.Series) -> dict[str, Any]:
    temperature = clean_float(row.get("temp_mean"), 4.5)
    return {
        "truck_id": "TRK-RD-001",
        "cargo": "Vaccines",
        "temperature": round(temperature, 2),
        "temp_min": round(clean_float(row.get("temp_min"), temperature), 2),
        "temp_max": round(clean_float(row.get("temp_max"), temperature), 2),
        "temp_std": round(clean_float(row.get("temp_std"), 0.08), 4),
        "frac_temp_above_6": round(clean_float(row.get("frac_temp_above_6"), 0.0), 4),
        "frac_temp_above_8": round(clean_float(row.get("frac_temp_above_8"), 0.0), 4),
        "hum_mean": round(clean_float(row.get("hum_mean"), 58.0), 2),
        "hum_std": round(clean_float(row.get("hum_std"), 2.5), 4),
        "door_count": max(0, int(clean_float(row.get("door_count"), 0))),
        "accel_rms": round(clean_float(row.get("accel_rms"), 0.04), 4),
        "handling_stress": round(clean_float(row.get("handling_stress"), 0.45), 4),
        "health_index": round(clean_float(row.get("Health_Index", row.get("health_index")), 0.98), 4),
        "temp_change_rate": round(clean_float(row.get("temp_change_rate"), 0.0), 4),
        "speed_kmh": 68.0,
        "status": "CRITICAL" if temperature >= 8.0 else ("WARNING" if temperature >= 6.5 else "SAFE"),
        "timestamp": pd.to_datetime(row["timestamp"]).strftime("%Y-%m-%d %H:%M:%S"),
    }

def replay_trip() -> None:
    trip = load_trip()
    total_rows = len(trip)
    print(f"Replaying {total_rows} rows for {TRIP_BAG_ID}...")

    for idx, row in trip.iterrows():
        payload = build_payload(row)
        
        # Interpolate GPS so the truck actually moves on the map
        progress = idx / total_rows if total_rows > 1 else 0
        payload["lat"] = round(START_LAT + (DEST_LAT - START_LAT) * progress, 5)
        payload["lng"] = round(START_LON + (DEST_LON - START_LON) * progress, 5)

        try:
            requests.post(BRIDGE_URL, json=payload, timeout=5)
            print(f"[Sent] Temp: {payload['temperature']}C | Lat: {payload['lat']} Lng: {payload['lng']}")
        except Exception as exc:
            print(f"Failed: {exc}")
        time.sleep(REPLAY_DELAY_SECONDS)

if __name__ == "__main__":
    replay_trip()
