from __future__ import annotations

from collections import deque, defaultdict
from datetime import datetime
import math
import os
from typing import Any

os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("LOKY_MAX_CPU_COUNT", "1")

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor, IsolationForest
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
try:
    from config import CONFIG
except Exception:
    CONFIG = {
        "thresholds": {"safe_max_c": 6.5, "critical_at_c": 8.0, "temp_ceil_c": 12.0, "temp_floor_c": 2.0},
        "truck": {"base_speed_kmh": 68.0},
        "weather_defaults": {"ambient_temp_c": 31.0, "ambient_humidity_pct": 58.0, "weather_risk_index": 0.35},
        "route": {"start": {"lat": 22.3072, "lon": 73.1812}, "dest": {"lat": 23.0225, "lon": 72.5714}},
    }

SAFE_MAX = float(CONFIG["thresholds"]["safe_max_c"])
CRITICAL_AT = float(CONFIG["thresholds"]["critical_at_c"])
TEMP_CEIL = float(CONFIG["thresholds"]["temp_ceil_c"])
TEMP_FLOOR = float(CONFIG["thresholds"]["temp_floor_c"])
BASE_SPEED = float(CONFIG["truck"]["base_speed_kmh"])
WEATHER_DEFAULTS = CONFIG["weather_defaults"]

class FrostGuardML:
    feature_columns = [
        "temperature", "temp_min", "temp_max", "temp_std", "temp_change_rate", "temp_delta",
        "temp_delta_2", "temp_lag_1", "temp_lag_2", "temp_lag_3", "temp_lag_6", "temp_rolling_mean",
        "temp_rolling_mean_3", "temp_rolling_mean_6", "temp_rolling_std_6", "temp_rolling_std",
        "temp_range", "hour_sin", "hour_cos", "frac_temp_above_6", "frac_temp_above_8", "hum_mean",
        "hum_std", "door_count", "accel_rms", "handling_stress", "health_index", "ambient_temp_c",
        "ambient_humidity_pct", "weather_risk_index", "speed_kmh", "distance_step_km", "minutes_above_safe",
    ]

    def __init__(
        self,
        csv_path: str = "fleet_logs.csv",
        dataset_path: str | None = None,
        window_size: int = 120,
        training_sample_rows: int = 80000,
        forecast_steps: int = 10,
        seconds_per_step: int = 3,
    ) -> None:
        self.csv_path = csv_path
        self.dataset_path = dataset_path
        self.window_size = window_size
        self.training_sample_rows = training_sample_rows
        self.forecast_steps = forecast_steps
        self.seconds_per_step = seconds_per_step
        
        # Track history individually per truck to prevent mixed data
        self.histories = defaultdict(lambda: deque(maxlen=self.window_size))
        
        self.detector = Pipeline([("scale", StandardScaler()), ("isolation_forest", IsolationForest(n_estimators=180, contamination=0.12, random_state=42))])
        self.forecaster = HistGradientBoostingRegressor(max_iter=420, learning_rate=0.045, max_leaf_nodes=63, l2_regularization=0.02, random_state=42)
        self.fallback_forecaster = Pipeline([("scale", StandardScaler()), ("ridge", Ridge(alpha=1.0))])
        self.is_trained = False
        self.training_rows = 0
        self.performance_metrics: dict[str, float | int | str] = {}
        self.last_point: dict[str, Any] | None = None
        self.minutes_above_safe = 0.0
        self._train()

    def reset(self):
        self.histories.clear()

    def _train(self) -> None:
        frame = self._load_training_data()
        if len(frame) < 40:
            frame = self._synthetic_training_data()

        featured = self._build_features(frame)
        clean = featured.dropna(subset=self.feature_columns)
        self.detector.fit(clean[self.feature_columns])

        forecast_frame = clean.copy()
        if "bag_id" in forecast_frame:
            forecast_frame["next_temp"] = forecast_frame.groupby("bag_id")["temperature"].shift(-1)
        else:
            forecast_frame["next_temp"] = forecast_frame["temperature"].shift(-1)
        forecast_frame = forecast_frame.dropna(subset=["next_temp"])
        x = forecast_frame[self.feature_columns]
        y = forecast_frame["next_temp"]
        if len(forecast_frame) >= 200:
            x_train, x_val, y_train, y_val = train_test_split(x, y, test_size=0.2, random_state=42)
        else:
            x_train, x_val, y_train, y_val = x, x, y, y
        try:
            self.forecaster.fit(x_train, y_train)
            val_pred = self.forecaster.predict(x_val)
            model_name = "HistGradientBoostingRegressor"
        except Exception:
            self.forecaster = self.fallback_forecaster
            self.forecaster.fit(x_train, y_train)
            val_pred = self.forecaster.predict(x_val)
            model_name = "Ridge fallback"

        self.performance_metrics = {
            "forecast_model": model_name,
            "validation_rows": int(len(x_val)),
            "r2_score": round(float(r2_score(y_val, val_pred)), 4),
            "mae_celsius": round(float(mean_absolute_error(y_val, val_pred)), 4),
            "mse": round(float(mean_squared_error(y_val, val_pred)), 4),
            "rmse_celsius": round(float(mean_squared_error(y_val, val_pred) ** 0.5), 4),
        }

        self.training_rows = int(len(clean))
        self.is_trained = True

    def _load_training_data(self) -> pd.DataFrame:
        dataset = self._load_healthcare_dataset()
        if not dataset.empty:
            return dataset

        if not os.path.exists(self.csv_path):
            return pd.DataFrame()

        try:
            raw = pd.read_csv(self.csv_path)
        except Exception:
            return pd.DataFrame()

        rename_map = {"Current_Temp": "temperature", "Lat": "lat", "Lng": "lng", "Timestamp": "timestamp"}
        raw = raw.rename(columns=rename_map)
        if "temperature" not in raw:
            return pd.DataFrame()
        if "bag_id" not in raw:
            raw["bag_id"] = "fleet_log"

        raw["temperature"] = pd.to_numeric(raw["temperature"], errors="coerce")
        raw["lat"] = pd.to_numeric(raw.get("lat"), errors="coerce")
        raw["lng"] = pd.to_numeric(raw.get("lng"), errors="coerce")
        raw["timestamp"] = pd.to_datetime(raw.get("timestamp"), errors="coerce")
        raw = raw.dropna(subset=["temperature"]).sort_values("timestamp")
        raw = self._ensure_optional_columns(raw)
        return raw[
            ["bag_id", "temperature", "temp_min", "temp_max", "temp_std", "temp_change_rate", "frac_temp_above_6",
             "frac_temp_above_8", "hum_mean", "hum_std", "door_count", "accel_rms", "handling_stress", "health_index",
             "ambient_temp_c", "ambient_humidity_pct", "weather_risk_index", "lat", "lng", "timestamp", "speed_kmh"]
        ].tail(600)

    def _load_healthcare_dataset(self) -> pd.DataFrame:
        if not self.dataset_path or not os.path.exists(self.dataset_path):
            return pd.DataFrame()

        try:
            raw = pd.read_csv(self.dataset_path)
        except Exception:
            return pd.DataFrame()

        rename_map = {"temp_mean": "temperature", "Health_Index": "health_index"}
        raw = raw.rename(columns=rename_map)
        if "temperature" not in raw:
            return pd.DataFrame()
        if "bag_id" not in raw:
            raw["bag_id"] = "fleet_log"

        numeric_cols = ["temperature", "temp_min", "temp_max", "temp_std", "frac_temp_above_6", "frac_temp_above_8",
                        "hum_mean", "hum_std", "door_count", "accel_rms", "handling_stress", "health_index", "temp_change_rate"]
        for col in numeric_cols:
            if col in raw:
                raw[col] = pd.to_numeric(raw[col], errors="coerce")

        raw["timestamp"] = pd.to_datetime(raw.get("timestamp"), errors="coerce")
        raw = raw.dropna(subset=["temperature"]).sort_values(["bag_id", "timestamp"] if "bag_id" in raw else ["timestamp"])
        raw["lat"] = np.nan
        raw["lng"] = np.nan
        raw["speed_kmh"] = BASE_SPEED
        raw = self._ensure_optional_columns(raw)
        return raw[
            ["bag_id", "temperature", "temp_min", "temp_max", "temp_std", "temp_change_rate", "frac_temp_above_6",
             "frac_temp_above_8", "hum_mean", "hum_std", "door_count", "accel_rms", "handling_stress", "health_index",
             "ambient_temp_c", "ambient_humidity_pct", "weather_risk_index", "lat", "lng", "timestamp", "speed_kmh"]
        ].tail(self.training_sample_rows)

    def save_artifact(self, artifact_path: str) -> None:
        os.makedirs(os.path.dirname(artifact_path), exist_ok=True)
        joblib.dump(self, artifact_path)

    @classmethod
    def load_artifact(cls, artifact_path: str) -> "FrostGuardML":
        return joblib.load(artifact_path)

    def _ensure_optional_columns(self, frame: pd.DataFrame) -> pd.DataFrame:
        defaults = {
            "temp_min": frame["temperature"] if "temperature" in frame else 4.5,
            "temp_max": frame["temperature"] if "temperature" in frame else 4.5,
            "temp_std": 0.08, "temp_change_rate": 0.0, "frac_temp_above_6": 0.0, "frac_temp_above_8": 0.0,
            "hum_mean": 58.0, "hum_std": 2.5, "door_count": 0.0, "accel_rms": 0.04, "handling_stress": 0.45,
            "health_index": 0.98, "ambient_temp_c": float(WEATHER_DEFAULTS["ambient_temp_c"]),
            "ambient_humidity_pct": float(WEATHER_DEFAULTS["ambient_humidity_pct"]),
            "weather_risk_index": float(WEATHER_DEFAULTS["weather_risk_index"]), "speed_kmh": BASE_SPEED,
        }
        for col, default in defaults.items():
            if col not in frame:
                frame[col] = default
            frame[col] = pd.to_numeric(frame[col], errors="coerce")
            if isinstance(default, pd.Series):
                frame[col] = frame[col].fillna(default)
            else:
                frame[col] = frame[col].fillna(default)
        return frame

    def _synthetic_training_data(self) -> pd.DataFrame:
        rng = np.random.default_rng(42)
        rows = []
        temp = 4.6
        lat, lng = float(CONFIG["route"]["start"]["lat"]), float(CONFIG["route"]["start"]["lon"])
        for idx in range(240):
            if 80 <= idx < 115:
                temp += rng.uniform(0.05, 0.22)
            elif 150 <= idx < 172:
                temp += rng.uniform(0.45, 1.0)
            elif 172 <= idx < 210:
                temp += rng.uniform(-0.35, 0.05)
            else:
                temp += rng.uniform(-0.12, 0.14)
            temp = float(np.clip(temp, 2.0, TEMP_CEIL))
            rows.append({
                "temperature": round(temp, 2), "temp_min": round(temp - rng.uniform(0.05, 0.2), 2),
                "temp_max": round(temp + rng.uniform(0.05, 0.35), 2), "temp_std": rng.uniform(0.04, 0.28),
                "frac_temp_above_6": 1.0 if temp > 6.0 else rng.uniform(0.0, 0.08),
                "frac_temp_above_8": 1.0 if temp > CRITICAL_AT else rng.uniform(0.0, 0.03),
                "hum_mean": 58 + rng.normal(0, 2.5), "hum_std": rng.uniform(1.6, 3.4),
                "door_count": max(0.0, rng.normal(0.02, 0.08)), "accel_rms": rng.uniform(0.02, 0.08),
                "handling_stress": rng.uniform(0.35, 0.7), "health_index": float(np.clip(1.0 - max(temp - 4.5, 0) * 0.04, 0.55, 1.0)),
                "ambient_temp_c": float(WEATHER_DEFAULTS["ambient_temp_c"]) + rng.normal(0, 2.0),
                "ambient_humidity_pct": float(WEATHER_DEFAULTS["ambient_humidity_pct"]) + rng.normal(0, 6.0),
                "weather_risk_index": float(np.clip(float(WEATHER_DEFAULTS["weather_risk_index"]) + max(temp - SAFE_MAX, 0) * 0.08, 0.0, 1.0)),
                "lat": lat + idx * 0.0032, "lng": lng - idx * 0.0025,
                "timestamp": pd.Timestamp("2026-01-01") + pd.Timedelta(seconds=idx * 3), "speed_kmh": 68 + rng.normal(0, 4),
            })
        return pd.DataFrame(rows)

    def _build_features(self, frame: pd.DataFrame) -> pd.DataFrame:
        data = frame.copy()
        data["temperature"] = pd.to_numeric(data["temperature"], errors="coerce")
        data = self._ensure_optional_columns(data)
        data["speed_kmh"] = pd.to_numeric(data.get("speed_kmh", BASE_SPEED), errors="coerce").fillna(BASE_SPEED)

        group = data.groupby("bag_id", group_keys=False) if "bag_id" in data else None
        if group is not None:
            diff_1 = group["temperature"].diff()
            diff_2 = diff_1.groupby(data["bag_id"]).shift(1)
            data["temp_lag_1"] = group["temperature"].shift(1)
            data["temp_lag_2"] = group["temperature"].shift(2)
            data["temp_lag_3"] = group["temperature"].shift(3)
            data["temp_lag_6"] = group["temperature"].shift(6)
            data["temp_rolling_mean_3"] = group["temperature"].rolling(3, min_periods=1).mean().reset_index(level=0, drop=True)
            data["temp_rolling_mean_6"] = group["temperature"].rolling(6, min_periods=1).mean().reset_index(level=0, drop=True)
            data["temp_rolling_std_6"] = group["temperature"].rolling(6, min_periods=2).std().reset_index(level=0, drop=True)
        else:
            diff_1 = data["temperature"].diff()
            diff_2 = diff_1.shift(1)
            data["temp_lag_1"] = data["temperature"].shift(1)
            data["temp_lag_2"] = data["temperature"].shift(2)
            data["temp_lag_3"] = data["temperature"].shift(3)
            data["temp_lag_6"] = data["temperature"].shift(6)
            data["temp_rolling_mean_3"] = data["temperature"].rolling(3, min_periods=1).mean()
            data["temp_rolling_mean_6"] = data["temperature"].rolling(6, min_periods=1).mean()
            data["temp_rolling_std_6"] = data["temperature"].rolling(6, min_periods=2).std()

        data["temp_change_rate"] = pd.to_numeric(data["temp_change_rate"], errors="coerce").fillna(diff_1).fillna(0.0)
        data["temp_delta"] = data["temp_change_rate"].fillna(diff_1).fillna(0.0)
        data["temp_delta_2"] = diff_2.fillna(0.0)
        for col in ("temp_lag_1", "temp_lag_2", "temp_lag_3", "temp_lag_6"):
            data[col] = data[col].fillna(data["temperature"])
        data["temp_rolling_mean"] = data["temp_rolling_mean_6"].fillna(data["temperature"])
        data["temp_rolling_std"] = data["temp_rolling_std_6"].fillna(0.0)
        data["temp_rolling_std_6"] = data["temp_rolling_std_6"].fillna(0.0)
        data["temp_range"] = (data["temp_max"] - data["temp_min"]).fillna(0.0)
        timestamps = pd.to_datetime(data.get("timestamp"), errors="coerce")
        hours = timestamps.dt.hour.fillna(0) if hasattr(timestamps, "dt") else pd.Series(0, index=data.index)
        data["hour_sin"] = np.sin(2 * np.pi * hours / 24)
        data["hour_cos"] = np.cos(2 * np.pi * hours / 24)

        if "lat" in data and "lng" in data:
            data["prev_lat"] = data["lat"].shift(1)
            data["prev_lng"] = data["lng"].shift(1)
            data["distance_step_km"] = data.apply(
                lambda row: self._haversine(row["prev_lat"], row["prev_lng"], row["lat"], row["lng"]),
                axis=1,
            ).fillna(0.0)
        else:
            data["distance_step_km"] = 0.0

        data["above_safe"] = data["temperature"] > SAFE_MAX
        data["minutes_above_safe"] = (
            data["above_safe"].astype(int)
            .groupby((data["above_safe"] != data["above_safe"].shift()).cumsum())
            .cumsum()
            * 0.05
        )
        return data

    def analyze(self, telemetry: dict[str, Any]) -> dict[str, Any]:
        point = self._normalise_point(telemetry)
        truck_id = telemetry.get("truck_id", "TRK-DEFAULT")
        
        self.histories[truck_id].append(point)
        frame = pd.DataFrame(self.histories[truck_id])
        
        featured = self._build_features(frame)
        latest = featured.iloc[-1]
        x = latest[self.feature_columns].to_frame().T

        raw_score = float(self.detector.named_steps["isolation_forest"].decision_function(
            self.detector.named_steps["scale"].transform(x)
        )[0])
        anomaly = bool(self.detector.predict(x)[0] == -1)
        anomaly_score = int(np.clip((0.12 - raw_score) / 0.24 * 100, 0, 100))

        forecast = self._forecast_sequence(x, steps=self.forecast_steps)
        max_forecast = max(forecast) if forecast else float(point["temperature"])
        time_to_critical = 0 if point["temperature"] >= CRITICAL_AT else self._time_to_threshold(
            forecast, CRITICAL_AT, seconds_per_step=self.seconds_per_step
        )
        breach_probability = int(
            np.clip((max_forecast - SAFE_MAX) / (CRITICAL_AT - SAFE_MAX) * 70 + anomaly_score * 0.3, 0, 100)
        )
        if point["temperature"] >= CRITICAL_AT:
            breach_probability = max(breach_probability, 95)

        risk_level = self._risk_level(point["temperature"], anomaly, breach_probability, time_to_critical)
        recommendation = self._recommendation(risk_level, time_to_critical)

        return {
            "model": "Isolation Forest + Gradient Boosted Forecast",
            "trained": self.is_trained,
            "training_rows": self.training_rows,
            "anomaly": anomaly,
            "anomaly_score": anomaly_score,
            "risk_level": risk_level,
            "breach_probability": breach_probability,
            "predicted_temp_30s": round(float(forecast[-1]), 2) if forecast else round(point["temperature"], 2),
            "forecast_series": [round(float(v), 2) for v in forecast],
            "time_to_critical_sec": time_to_critical,
            "recommendation": recommendation,
        }

    def _normalise_point(self, telemetry: dict[str, Any]) -> dict[str, Any]:
        temp = float(telemetry.get("temperature", 4.5))
        lat = float(telemetry.get("lat", telemetry.get("latitude", 0.0)))
        lng = float(telemetry.get("lng", telemetry.get("lon", 0.0)))
        timestamp = telemetry.get("timestamp") or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        speed = float(telemetry.get("speed_kmh", BASE_SPEED))
        return {
            "temperature": temp, "temp_min": float(telemetry.get("temp_min", temp)),
            "temp_max": float(telemetry.get("temp_max", temp)), "temp_std": float(telemetry.get("temp_std", 0.08)),
            "frac_temp_above_6": float(telemetry.get("frac_temp_above_6", 1.0 if temp > 6.0 else 0.0)),
            "frac_temp_above_8": float(telemetry.get("frac_temp_above_8", 1.0 if temp > CRITICAL_AT else 0.0)),
            "hum_mean": float(telemetry.get("hum_mean", 58.0)), "hum_std": float(telemetry.get("hum_std", 2.5)),
            "door_count": float(telemetry.get("door_count", 0.0)), "accel_rms": float(telemetry.get("accel_rms", 0.04)),
            "handling_stress": float(telemetry.get("handling_stress", 0.45)), "health_index": float(telemetry.get("health_index", 0.98)),
            "ambient_temp_c": float(telemetry.get("ambient_temp_c", WEATHER_DEFAULTS["ambient_temp_c"])),
            "ambient_humidity_pct": float(telemetry.get("ambient_humidity_pct", WEATHER_DEFAULTS["ambient_humidity_pct"])),
            "weather_risk_index": float(telemetry.get("weather_risk_index", WEATHER_DEFAULTS["weather_risk_index"])),
            "lat": lat, "lng": lng, "timestamp": pd.to_datetime(timestamp, errors="coerce"), "speed_kmh": speed,
        }

    def _forecast_sequence(self, features: pd.DataFrame, steps: int) -> list[float]:
        sequence = []
        current = features.copy()
        for _ in range(steps):
            next_temp = float(self.forecaster.predict(current)[0])
            next_temp = float(np.clip(next_temp, 2.0, TEMP_CEIL))
            prev_temp = float(current["temperature"].iloc[0])
            if prev_temp >= CRITICAL_AT:
                next_temp = max(next_temp, prev_temp - 0.2)
            elif prev_temp >= SAFE_MAX:
                next_temp = max(next_temp, prev_temp - 0.12)
            sequence.append(next_temp)
            current = current.copy()
            previous_delta = float(current["temp_delta"].iloc[0])
            current["temp_delta_2"] = previous_delta
            current["temp_change_rate"] = next_temp - prev_temp
            current["temp_delta"] = next_temp - prev_temp
            current["temp_lag_6"] = float(current["temp_lag_3"].iloc[0])
            current["temp_lag_3"] = float(current["temp_lag_2"].iloc[0])
            current["temp_lag_2"] = float(current["temp_lag_1"].iloc[0])
            current["temp_lag_1"] = prev_temp
            current["temperature"] = next_temp
            current["temp_min"] = min(float(current["temp_min"].iloc[0]), next_temp)
            current["temp_max"] = max(float(current["temp_max"].iloc[0]), next_temp)
            current["temp_range"] = float(current["temp_max"].iloc[0]) - float(current["temp_min"].iloc[0])
            current["frac_temp_above_6"] = 1.0 if next_temp > 6.0 else float(current["frac_temp_above_6"].iloc[0]) * 0.9
            current["frac_temp_above_8"] = 1.0 if next_temp > CRITICAL_AT else float(current["frac_temp_above_8"].iloc[0]) * 0.9
            current["health_index"] = float(np.clip(float(current["health_index"].iloc[0]) - max(next_temp - SAFE_MAX, 0) * 0.01, 0.2, 1.0))
            current["weather_risk_index"] = float(current["weather_risk_index"].iloc[0])
            current["ambient_temp_c"] = float(current["ambient_temp_c"].iloc[0])
            current["ambient_humidity_pct"] = float(current["ambient_humidity_pct"].iloc[0])
            current["temp_rolling_mean_3"] = (float(current["temp_rolling_mean_3"].iloc[0]) * 2 + next_temp) / 3
            current["temp_rolling_mean_6"] = (float(current["temp_rolling_mean_6"].iloc[0]) * 5 + next_temp) / 6
            current["temp_rolling_mean"] = current["temp_rolling_mean_6"]
            current["temp_rolling_std_6"] = max(float(current["temp_rolling_std_6"].iloc[0]) * 0.92, 0.02)
            current["temp_rolling_std"] = current["temp_rolling_std_6"]
            current["minutes_above_safe"] = (float(current["minutes_above_safe"].iloc[0]) + 0.05 if next_temp > SAFE_MAX else 0.0)
        return sequence

    def _time_to_threshold(self, forecast: list[float], threshold: float, seconds_per_step: int) -> int | None:
        for idx, value in enumerate(forecast, start=1):
            if value >= threshold:
                return idx * seconds_per_step
        return None

    def _risk_level(self, temp: float, anomaly: bool, breach_probability: int, time_to_critical: int | None) -> str:
        if temp >= CRITICAL_AT or time_to_critical is not None and time_to_critical <= 15:
            return "CRITICAL"
        if temp >= SAFE_MAX or breach_probability >= 65 or anomaly:
            return "HIGH"
        if breach_probability >= 35:
            return "MEDIUM"
        return "LOW"

    def _recommendation(self, risk_level: str, time_to_critical: int | None) -> str:
        if risk_level == "CRITICAL":
            return "Trigger emergency reroute and alert driver immediately."
        if risk_level == "HIGH":
            eta = f" in about {time_to_critical}s" if time_to_critical else ""
            return f"Pre-cool aggressively and prepare nearest cold-storage reroute{eta}."
        if risk_level == "MEDIUM":
            return "Increase monitoring frequency and inspect compressor load."
        return "Continue normal monitoring."

    def _haversine(self, lat1: Any, lon1: Any, lat2: Any, lon2: Any) -> float:
        try:
            if any(pd.isna(v) for v in (lat1, lon1, lat2, lon2)):
                return 0.0
            radius = 6371
            dlat = math.radians(float(lat2) - float(lat1))
            dlon = math.radians(float(lon2) - float(lon1))
            a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(float(lat1))) * math.cos(math.radians(float(lat2))) * math.sin(dlon / 2) ** 2
            return radius * 2 * math.asin(math.sqrt(a))
        except Exception:
            return 0.0
