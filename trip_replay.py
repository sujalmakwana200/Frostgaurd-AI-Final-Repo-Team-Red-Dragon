from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import pandas as pd
import requests


DATA_FILE = Path(__file__).resolve().parent / "data" / "cleaned_healthcare_iot_data.csv"
BRIDGE_URL = "http://127.0.0.1:5000/telemetry"
TRIP_BAG_ID = "BAG_0001"
REPLAY_DELAY_SECONDS = 2


def clean_float(value: Any, default: float = 0.0) -> float:
    numeric = pd.to_numeric(value, errors="coerce")
    if pd.isna(numeric):
        return float(default)
    return float(numeric)


def clean_int(value: Any, default: int = 0) -> int:
    numeric = pd.to_numeric(value, errors="coerce")
    if pd.isna(numeric):
        return int(default)
    return int(round(float(numeric)))


def status_from_temperature(temperature: float) -> str:
    if temperature >= 8.0:
        return "CRITICAL"
    if temperature >= 6.5:
        return "WARNING"
    return "SAFE"


def load_trip() -> pd.DataFrame:
    if not DATA_FILE.exists():
        raise FileNotFoundError(f"Dataset not found: {DATA_FILE}")

    frame = pd.read_csv(DATA_FILE)
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], errors="coerce")
    frame = frame.dropna(subset=["timestamp"])

    trip = frame.loc[frame["bag_id"].astype(str) == TRIP_BAG_ID].copy()
    if trip.empty:
        raise ValueError(f"No rows found for bag_id={TRIP_BAG_ID!r}")

    return trip.sort_values("timestamp").reset_index(drop=True)


def build_payload(row: pd.Series) -> dict[str, Any]:
    temperature = clean_float(row.get("temp_mean"), 4.5)

    return {
        "truck_id": "TRK-RD-001",
        "cargo": "Vaccines",
        "bag_id": str(row.get("bag_id", TRIP_BAG_ID)),
        "route": str(row.get("route", "Historical Trip Replay")),
        "temperature": round(temperature, 2),
        "temp_min": round(clean_float(row.get("temp_min"), temperature), 2),
        "temp_max": round(clean_float(row.get("temp_max"), temperature), 2),
        "temp_std": round(clean_float(row.get("temp_std"), 0.08), 4),
        "frac_temp_above_6": round(clean_float(row.get("frac_temp_above_6"), 0.0), 4),
        "frac_temp_above_8": round(clean_float(row.get("frac_temp_above_8"), 0.0), 4),
        "hum_mean": round(clean_float(row.get("hum_mean"), 58.0), 2),
        "hum_std": round(clean_float(row.get("hum_std"), 2.5), 4),
        "door_count": max(0, clean_int(row.get("door_count"), 0)),
        "accel_rms": round(clean_float(row.get("accel_rms"), 0.04), 4),
        "handling_stress": round(clean_float(row.get("handling_stress"), 0.45), 4),
        "health_index": round(clean_float(row.get("Health_Index"), 0.98), 4),
        "temp_change_rate": round(clean_float(row.get("temp_change_rate"), 0.0), 4),
        "ambient_temp_c": 34.0,
        "ambient_humidity_pct": 66.0,
        "weather_risk_index": 0.48,
        "lat": 22.30,
        "lng": 73.18,
        "speed_kmh": 68.0,
        "status": status_from_temperature(temperature),
        "timestamp": pd.to_datetime(row["timestamp"]).strftime("%Y-%m-%d %H:%M:%S"),
    }


def replay_trip() -> None:
    trip = load_trip()
    print(f"Replaying {len(trip)} rows for {TRIP_BAG_ID} from {DATA_FILE}")
    print(f"Posting telemetry to {BRIDGE_URL}")

    for _, row in trip.iterrows():
        payload = build_payload(row)

        try:
            response = requests.post(BRIDGE_URL, json=payload, timeout=5)
            response.raise_for_status()
            print(
                f"[Replaying Timestamp {payload['timestamp']}] "
                f"Sent Temp: {payload['temperature']:.2f} C | "
                f"Status: {payload['status']}"
            )
        except requests.RequestException as exc:
            print(
                f"[Replaying Timestamp {payload['timestamp']}] "
                f"Failed to send telemetry: {exc}"
            )

        time.sleep(REPLAY_DELAY_SECONDS)


if __name__ == "__main__":
    replay_trip()
