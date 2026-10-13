"""
FrostGuard ML engine (v2, drop-in replacement for frost_ml.py)

What changed compared with v1:
  * Trains at startup (a few seconds), so there is no .joblib/.pkl that can get corrupted.
    An artifact can still be saved/loaded, but it stores only fitted estimators + the sklearn
    version, and a mismatch or a damaged file simply triggers a retrain.
  * The forecaster is trained at the LIVE sampling rate (one step = seconds_per_step), on traces
    from a small thermal simulator (thermostat cooler box, door opens, compressor failure,
    slow drift, step jump, sensor glitch). v1 trained on hourly dataset rows but used the model
    every few seconds.
  * Forecasts predict the CHANGE in temperature (direct multi-horizon), not the next absolute
    value, so the model cannot look good just by repeating the current temperature.
  * Metrics are computed on held-out TRACES and reported next to a persistence baseline
    ("assume nothing changes"). Look at `skill_vs_persistence`: 0 = no better than persistence.
  * Constant / meaningless inputs (speed, GPS distance, weather defaults, health_index) removed.
  * Isolation Forest is trained on NORMAL traces only.
  * Startup prints exactly what the models were trained on. There is no silent fallback.

Everything the rest of the app uses is kept: FrostGuardML(...), analyze(), reset(),
performance_metrics, training_rows, is_trained, save_artifact(), load_artifact(),
and the same keys in the analyze() result.

Real data later: FrostGuardML.from_real_logs("logs.csv", trace_col=..., temp_col=..., seconds_per_step=300)
trains the same models on real logger exports (see the method's docstring for the CSV requirements).

Run `python frost_ml.py` for a self-test.
"""
from __future__ import annotations

import os
import time
from collections import defaultdict, deque
from datetime import datetime
from typing import Any

os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("LOKY_MAX_CPU_COUNT", "1")

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.ensemble import HistGradientBoostingRegressor, IsolationForest
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

try:
    from config import CONFIG
except Exception:
    CONFIG = {
        "thresholds": {"safe_max_c": 6.5, "critical_at_c": 8.0, "temp_ceil_c": 12.0, "temp_floor_c": 2.0},
        "truck": {"base_speed_kmh": 68.0},
        "weather_defaults": {"ambient_temp_c": 31.0, "ambient_humidity_pct": 58.0, "weather_risk_index": 0.35},
        "ml": {},
    }

SAFE_MAX = float(CONFIG["thresholds"]["safe_max_c"])
CRITICAL_AT = float(CONFIG["thresholds"]["critical_at_c"])
TEMP_CEIL = float(CONFIG["thresholds"]["temp_ceil_c"])
TEMP_FLOOR = float(CONFIG["thresholds"]["temp_floor_c"])
WEATHER_DEFAULTS = CONFIG["weather_defaults"]
DEFAULT_TIME_SCALE = float(CONFIG.get("ml", {}).get("time_scale", 50))

ARTIFACT_FORMAT = 2

# One feature list, used identically for training and live inference.
FORECAST_FEATURES = [
    "temperature", "temp_delta", "temp_delta_2", "temp_delta_3", "temp_delta_6",
    "temp_rolling_mean_6", "temp_rolling_std_6", "temp_range_6",
    "door_open", "ambient_temp_c", "headroom_c", "minutes_above_safe",
]
DETECTOR_FEATURES = [
    "temperature", "temp_delta", "temp_delta_2", "temp_delta_3",
    "temp_rolling_std_6", "temp_range_6", "door_open", "ambient_temp_c",
]


def _f(value: Any, default: float) -> float:
    """float() that never returns NaN/inf or raises."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return default
    return v if np.isfinite(v) else default


# --------------------------------------------------------------------------- thermal simulator
def simulate_trace(rng: np.random.Generator, n_steps: int, seconds_per_step: float,
                   time_scale: float, fault_prob: float = 0.65) -> pd.DataFrame:
    """
    One cooler-box temperature trace sampled at the live rate.

    time_scale = how much faster than real time the demo feed runs (a whole truck route in a few
    minutes => ~50). One step therefore covers seconds_per_step * time_scale real seconds of
    thermal behaviour. Set time_scale=1 for a real-time feed.
    """
    minutes_per_step = seconds_per_step * time_scale / 60.0
    n_sub = max(1, int(round(minutes_per_step)))
    dt = minutes_per_step / n_sub                       # minutes per sub-step
    leak, door_leak, cool = 0.0018, 0.010, 0.12         # per minute

    ambient = rng.uniform(25, 40)
    lo = rng.uniform(3.2, 4.0)
    hi = lo + rng.uniform(0.6, 1.2)
    T = rng.uniform(lo, hi)
    on = False

    fault = str(rng.choice(["compressor", "door", "drift", "step", "glitch"])) if rng.random() < fault_prob else "none"
    onset = int(rng.integers(30, max(31, n_steps - 60)))
    dur = int(rng.integers(15, 120))
    step_size = rng.uniform(2.0, 5.0)
    glitch_steps = set(int(x) for x in rng.integers(20, n_steps - 5, size=int(rng.integers(1, 4)))) if fault == "glitch" else set()

    true_t = np.empty(n_steps)
    meas_t = np.empty(n_steps)
    door = np.zeros(n_steps)
    amb = np.empty(n_steps)
    for i in range(n_steps):
        in_fault = onset <= i < onset + dur
        comp_dead = fault == "compressor" and in_fault
        lo_i, hi_i = lo, hi
        if fault == "drift" and i >= onset:
            creep = min(3.5, 0.03 * (i - onset))
            lo_i, hi_i = lo + creep, hi + creep
        door_now = rng.random() < 0.02 or (fault == "door" and onset <= i < onset + max(2, dur // 10))
        amb_i = ambient + 3.0 * np.sin(i / 50.0)
        for _ in range(n_sub):
            k = door_leak if door_now else leak
            if T > hi_i:
                on = True
            elif T < lo_i:
                on = False
            cooling = cool if (on and not comp_dead) else 0.0
            T += (k * (amb_i - T) - cooling) * dt + rng.normal(0, 0.02) * np.sqrt(dt)
        offset = step_size if (fault == "step" and in_fault) else 0.0
        true_t[i] = T + offset
        meas = true_t[i] + rng.normal(0, 0.04)
        if i in glitch_steps:
            meas += rng.uniform(6, 20)                   # bogus sensor spike; the truth stays normal
        meas_t[i] = meas
        door[i] = 1.0 if door_now else 0.0
        amb[i] = amb_i

    return pd.DataFrame({
        "temperature": meas_t, "true_temperature": true_t, "door_open": door, "ambient_temp_c": amb,
        "fault": 0 if fault == "none" else 1, "fault_type": fault,
    })


# --------------------------------------------------------------------------- engine
class FrostGuardML:
    feature_columns = FORECAST_FEATURES
    # Raise HIGH as soon as the forecast says the safe limit will be crossed within the horizon.
    FORECAST_BREACH_ALERT = True

    def __init__(
        self,
        csv_path: str = "fleet_logs.csv",
        dataset_path: str | None = None,          # kept for compatibility, not used (see notes in analyze docs)
        window_size: int = 120,
        training_sample_rows: int = 80000,        # kept for compatibility, not used
        forecast_steps: int = 10,
        seconds_per_step: int = 3,
        time_scale: float | None = None,
        n_traces: int = 200,
        steps_per_trace: int = 300,
        seed: int = 42,
        train: bool = True,
    ) -> None:
        self.csv_path = csv_path
        self.window_size = window_size
        self.forecast_steps = int(forecast_steps)
        self.seconds_per_step = int(seconds_per_step)
        self.time_scale = float(DEFAULT_TIME_SCALE if time_scale is None else time_scale)
        self.n_traces = int(n_traces)
        self.steps_per_trace = int(steps_per_trace)
        self.seed = int(seed)

        fs = self.forecast_steps
        self.horizons = sorted({max(1, round(fs * 0.2)), max(1, round(fs * 0.5)), fs})

        self.histories = defaultdict(lambda: deque(maxlen=self.window_size))
        self.forecasters: dict[int, HistGradientBoostingRegressor] = {}
        self.detector: Pipeline | None = None
        self._score_lo = 0.0
        self._score_hi = -0.3
        self.is_trained = False
        self.training_rows = 0
        self.data_source = "simulated live-rate traces"
        self.performance_metrics: dict[str, float | int | str] = {}
        if train:
            self._train()

    def reset(self) -> None:
        self.histories.clear()

    # ----------------------------------------------------------------- features
    def _build_features(self, frame: pd.DataFrame) -> pd.DataFrame:
        d = frame.copy()
        t = pd.to_numeric(d["temperature"], errors="coerce").astype(float)
        first = t.iloc[0]
        d["temperature"] = t
        d["door_open"] = pd.to_numeric(d.get("door_open", 0.0), errors="coerce").fillna(0.0)
        d["ambient_temp_c"] = pd.to_numeric(d.get("ambient_temp_c", WEATHER_DEFAULTS["ambient_temp_c"]),
                                            errors="coerce").fillna(float(WEATHER_DEFAULTS["ambient_temp_c"]))
        d["temp_delta"] = t.diff().fillna(0.0)
        d["temp_delta_2"] = d["temp_delta"].shift(1).fillna(0.0)
        d["temp_delta_3"] = t - t.shift(3).fillna(first)
        d["temp_delta_6"] = t - t.shift(6).fillna(first)
        roll = t.rolling(6, min_periods=1)
        d["temp_rolling_mean_6"] = roll.mean()
        d["temp_rolling_std_6"] = t.rolling(6, min_periods=2).std().fillna(0.0)
        d["temp_range_6"] = roll.max() - roll.min()
        d["headroom_c"] = SAFE_MAX - t
        above = t > SAFE_MAX
        run = (above != above.shift()).cumsum()
        d["minutes_above_safe"] = above.astype(int).groupby(run).cumsum() * self.seconds_per_step / 60.0
        return d

    # ----------------------------------------------------------------- training
    def _train(self) -> None:
        """Default: train on simulated live-rate traces (no data files needed)."""
        rng = np.random.default_rng(self.seed)
        frames = []
        for tid in range(self.n_traces):
            tr = simulate_trace(rng, self.steps_per_trace, self.seconds_per_step, self.time_scale)
            frames.append(self._prepare_trace(tr, tid, truth=tr["true_temperature"]))
        self._fit_frames(frames, rng)

    def _prepare_trace(self, tr: pd.DataFrame, tid: int, truth: pd.Series) -> pd.DataFrame:
        f = self._build_features(tr)
        f["trace_id"] = tid
        f["fault"] = tr["fault"].values
        for h in self.horizons:
            f[f"y{h}"] = truth.shift(-h) - tr["temperature"]      # future truth minus what we see now
        return f

    @classmethod
    def from_real_logs(cls, csv_path: str, trace_col: str = "trace_id", temp_col: str = "temperature",
                       door_col: str | None = None, ambient_col: str | None = None,
                       seconds_per_step: int = 300, forecast_steps: int = 6, **kwargs: Any) -> "FrostGuardML":
        """
        Train on REAL logger data instead of the simulator.

        CSV requirements: one row per reading, rows sorted by time inside each trace (one trace = one
        truck trip / one cooler), readings at a FIXED interval (resample first if not). Set
        seconds_per_step to that interval (e.g. 300 for 5-minute loggers). Real data means
        time_scale=1 and a horizon of forecast_steps * interval (6 x 5 min = 30 minutes).
        A trace counts as a 'fault trace' if it ever reaches SAFE_MAX; those traces are excluded from
        the Isolation Forest's training data and used for the fault-focused skill score.
        """
        df = pd.read_csv(csv_path)
        ml = cls(train=False, seconds_per_step=seconds_per_step, forecast_steps=forecast_steps,
                 time_scale=1.0, **kwargs)
        frames = []
        for _, g in df.groupby(trace_col, sort=False):
            temp = pd.to_numeric(g[temp_col], errors="coerce").reset_index(drop=True)
            if temp.notna().sum() < 30:
                continue
            temp = temp.interpolate(limit_direction="both")
            tr = pd.DataFrame({
                "temperature": temp,
                "door_open": (pd.to_numeric(g[door_col], errors="coerce").fillna(0).reset_index(drop=True) > 0.5).astype(float)
                if door_col else 0.0,
                "ambient_temp_c": pd.to_numeric(g[ambient_col], errors="coerce").reset_index(drop=True)
                if ambient_col else float(WEATHER_DEFAULTS["ambient_temp_c"]),
            })
            tr["fault"] = int((tr["temperature"] >= SAFE_MAX).any())
            frames.append(ml._prepare_trace(tr, len(frames), truth=tr["temperature"]))
        if len(frames) < 5:
            raise ValueError(f"need at least 5 usable traces, found {len(frames)}")
        ml.data_source = f"REAL logs from {os.path.basename(csv_path)}"
        ml._fit_frames(frames, np.random.default_rng(ml.seed))
        return ml

    def _fit_frames(self, frames: list[pd.DataFrame], rng: np.random.Generator) -> None:
        t0 = time.time()
        data = pd.concat(frames, ignore_index=True)
        n_tr = len(frames)
        ids = rng.permutation(n_tr)
        val_ids = set(ids[: max(1, int(0.2 * n_tr))].tolist())
        is_val = data["trace_id"].isin(val_ids)
        train_df, val_df = data[~is_val], data[is_val]

        for h in self.horizons:
            tr_h = train_df.dropna(subset=[f"y{h}"])
            model = HistGradientBoostingRegressor(max_iter=150, learning_rate=0.08, max_leaf_nodes=31,
                                                  l2_regularization=0.05, random_state=self.seed)
            model.fit(tr_h[FORECAST_FEATURES], tr_h[f"y{h}"])
            self.forecasters[h] = model

        normal = train_df[train_df["fault"] == 0][DETECTOR_FEATURES]
        self.detector = Pipeline([
            ("scale", StandardScaler()),
            ("isolation_forest", IsolationForest(n_estimators=150, contamination=0.003, random_state=self.seed)),
        ]).fit(normal)
        raw = self.detector.named_steps["isolation_forest"].decision_function(
            self.detector.named_steps["scale"].transform(normal))
        self._score_lo = float(np.percentile(raw, 5))
        self._score_hi = float(raw.min())

        self._evaluate(val_df)
        self.training_rows = int(len(train_df))
        self.is_trained = True
        print(f"[FrostGuardML] trained on {self.training_rows} {self.data_source} "
              f"({n_tr} traces, ~{len(data) // n_tr} steps each, {self.seconds_per_step}s/step, "
              f"time_scale={self.time_scale:g}) in {time.time() - t0:.1f}s | "
              f"skill vs persistence: {self.performance_metrics['skill_vs_persistence']:+.2f} "
              f"(fault traces: {self.performance_metrics['skill_vs_persistence_fault_windows']:+.2f})")

    def _evaluate(self, val_df: pd.DataFrame) -> None:
        h = self.horizons[-1]
        v = val_df.dropna(subset=[f"y{h}"])
        y = v[f"y{h}"].to_numpy()
        pred = self.forecasters[h].predict(v[FORECAST_FEATURES])
        mae_m = float(mean_absolute_error(y, pred))
        mae_p = float(mean_absolute_error(y, np.zeros_like(y)))
        fmask = (v["fault"] == 1).to_numpy()
        skill_f = 1.0 - float(mean_absolute_error(y[fmask], pred[fmask])) / max(
            float(mean_absolute_error(y[fmask], np.zeros(fmask.sum()))), 1e-9) if fmask.any() else float("nan")
        cur = v["temperature"].to_numpy()
        self.performance_metrics = {
            "forecast_model": "HistGradientBoostingRegressor (direct multi-horizon, predicts temperature change)",
            "data_source": self.data_source,
            "split": "held-out traces",
            "horizon_steps": int(h),
            "horizon_seconds": int(h * self.seconds_per_step),
            "validation_rows": int(len(v)),
            "r2_score": round(float(r2_score(y, pred)), 4),                 # R2 on the temperature CHANGE
            "mae_celsius": round(mae_m, 4),
            "mse": round(float(mean_squared_error(y, pred)), 4),
            "rmse_celsius": round(float(mean_squared_error(y, pred) ** 0.5), 4),
            "persistence_mae_celsius": round(mae_p, 4),
            "skill_vs_persistence": round(1.0 - mae_m / max(mae_p, 1e-9), 4),   # 0 = no better than "nothing changes"
            "skill_vs_persistence_fault_windows": round(float(skill_f), 4),
            "r2_temperature": round(float(r2_score(cur + y, cur + pred)), 4),
            "r2_temperature_persistence": round(float(r2_score(cur + y, cur)), 4),
        }

    # ----------------------------------------------------------------- artifact (estimators only)
    def save_artifact(self, artifact_path: str) -> None:
        os.makedirs(os.path.dirname(artifact_path) or ".", exist_ok=True)
        joblib.dump({
            "format": ARTIFACT_FORMAT, "sklearn": sklearn.__version__,
            "config": dict(forecast_steps=self.forecast_steps, seconds_per_step=self.seconds_per_step,
                           time_scale=self.time_scale, n_traces=self.n_traces,
                           steps_per_trace=self.steps_per_trace, seed=self.seed, window_size=self.window_size),
            "forecasters": self.forecasters, "detector": self.detector,
            "score_lo": self._score_lo, "score_hi": self._score_hi,
            "metrics": self.performance_metrics, "training_rows": self.training_rows,
        }, artifact_path)

    @classmethod
    def load_artifact(cls, artifact_path: str, **kwargs: Any) -> "FrostGuardML":
        """Load a saved artifact; if it is missing, damaged or from another sklearn version, retrain."""
        try:
            art = joblib.load(artifact_path)
            if art.get("format") != ARTIFACT_FORMAT:
                raise ValueError("artifact format mismatch")
            if art.get("sklearn") != sklearn.__version__:
                raise ValueError(f"sklearn {art.get('sklearn')} != {sklearn.__version__}")
            obj = cls(train=False, **art["config"])
            obj.forecasters, obj.detector = art["forecasters"], art["detector"]
            obj._score_lo, obj._score_hi = art["score_lo"], art["score_hi"]
            obj.performance_metrics, obj.training_rows = art["metrics"], art["training_rows"]
            obj.is_trained = True
            print(f"[FrostGuardML] loaded artifact {artifact_path}")
            return obj
        except Exception as exc:
            print(f"[FrostGuardML] could not use artifact ({exc}); retraining instead")
            return cls(**kwargs)

    # ----------------------------------------------------------------- live inference
    def _normalise_point(self, telemetry: dict[str, Any]) -> dict[str, Any]:
        temp = _f(telemetry.get("temperature"), 4.5)
        door = _f(telemetry.get("door_count"), 0.0)
        return {
            "temperature": temp,
            "door_open": 1.0 if door > 0.5 else 0.0,
            "ambient_temp_c": _f(telemetry.get("ambient_temp_c"), float(WEATHER_DEFAULTS["ambient_temp_c"])),
            "timestamp": telemetry.get("timestamp") or datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }

    def _forecast_sequence(self, x: pd.DataFrame, steps: int) -> list[float]:
        current = float(x["temperature"].iloc[0])
        hs = [0] + self.horizons
        deltas = [0.0] + [float(self.forecasters[h].predict(x[FORECAST_FEATURES])[0]) for h in self.horizons]
        series = current + np.interp(np.arange(1, steps + 1), hs, deltas)
        return [float(np.clip(v, TEMP_FLOOR, TEMP_CEIL)) for v in series]

    def analyze(self, telemetry: dict[str, Any]) -> dict[str, Any]:
        point = self._normalise_point(telemetry)
        truck_id = telemetry.get("truck_id", "TRK-DEFAULT")
        self.histories[truck_id].append(point)
        frame = pd.DataFrame(self.histories[truck_id])
        featured = self._build_features(frame)
        x = featured.iloc[[-1]]

        scaler = self.detector.named_steps["scale"]
        iso = self.detector.named_steps["isolation_forest"]
        xd = scaler.transform(x[DETECTOR_FEATURES])
        raw_score = float(iso.decision_function(xd)[0])
        anomaly = bool(iso.predict(xd)[0] == -1)
        span = max(self._score_lo - self._score_hi, 1e-6)
        anomaly_score = int(np.clip((self._score_lo - raw_score) / span * 100, 0, 100))

        forecast = self._forecast_sequence(x, self.forecast_steps)
        temp = point["temperature"]
        max_forecast = max(forecast) if forecast else temp
        time_to_critical = 0 if temp >= CRITICAL_AT else self._time_to_threshold(
            forecast, CRITICAL_AT, seconds_per_step=self.seconds_per_step)

        breach_probability = int(np.clip(
            (max_forecast - SAFE_MAX) / (CRITICAL_AT - SAFE_MAX) * 70 + anomaly_score * 0.3, 0, 100))
        if temp >= CRITICAL_AT:
            breach_probability = max(breach_probability, 95)

        risk_level = self._risk_level(temp, anomaly, breach_probability, time_to_critical,
                                      forecast_max=max_forecast if self.FORECAST_BREACH_ALERT else None)
        return {
            "model": "Isolation Forest + Gradient Boosted Forecast",
            "trained": self.is_trained,
            "training_rows": self.training_rows,
            "data_source": self.data_source,
            "anomaly": anomaly,
            "anomaly_score": anomaly_score,
            "risk_level": risk_level,
            "breach_probability": breach_probability,
            "predicted_temp_30s": round(float(forecast[-1]), 2) if forecast else round(temp, 2),
            "forecast_series": [round(float(v), 2) for v in forecast],
            "time_to_critical_sec": time_to_critical,
            "recommendation": self._recommendation(risk_level, time_to_critical),
        }

    @staticmethod
    def _time_to_threshold(forecast: list[float], threshold: float, seconds_per_step: int) -> int | None:
        for idx, value in enumerate(forecast, start=1):
            if value >= threshold:
                return idx * seconds_per_step
        return None

    @staticmethod
    def _risk_level(temp: float, anomaly: bool, breach_probability: int, time_to_critical: int | None,
                    forecast_max: float | None = None) -> str:
        if temp >= CRITICAL_AT or (time_to_critical is not None and time_to_critical <= 15):
            return "CRITICAL"
        if temp >= SAFE_MAX or breach_probability >= 65 or anomaly or (forecast_max is not None and forecast_max >= SAFE_MAX):
            return "HIGH"
        if breach_probability >= 35:
            return "MEDIUM"
        return "LOW"

    @staticmethod
    def _recommendation(risk_level: str, time_to_critical: int | None) -> str:
        if risk_level == "CRITICAL":
            return "Trigger emergency reroute and alert driver immediately."
        if risk_level == "HIGH":
            eta = f" in about {time_to_critical}s" if time_to_critical else ""
            return f"Pre-cool aggressively and prepare nearest cold-storage reroute{eta}."
        if risk_level == "MEDIUM":
            return "Increase monitoring frequency and inspect compressor load."
        return "Continue normal monitoring."


# --------------------------------------------------------------------------- self-test
def _replay(ml: FrostGuardML, temps: list[float], truck: str = "SELFTEST") -> list[dict[str, Any]]:
    ml.histories.pop(truck, None)
    return [ml.analyze({"truck_id": truck, "temperature": t}) for t in temps]


def _selftest() -> None:
    ml = FrostGuardML()
    print("\nMetrics:")
    for k, v in ml.performance_metrics.items():
        print(f"  {k}: {v}")

    rng = np.random.default_rng(7)
    calm = list(4.5 + rng.normal(0, 0.05, 60))

    # 1) failing compressor: temperature ramps up
    ramp = calm[:30] + [4.5 + 0.15 * k for k in range(1, 31)]
    out = _replay(ml, ramp)
    cross = next((i for i, t in enumerate(ramp) if t >= SAFE_MAX), None)
    first = next((i for i, r in enumerate(out) if i >= 30 and r["risk_level"] in ("HIGH", "CRITICAL")), None)
    false_alarms = sum(r["risk_level"] in ("HIGH", "CRITICAL") for r in out[:30])
    print(f"\nRamp test: threshold ({SAFE_MAX}C) crossed at step {cross}; model raised HIGH/CRITICAL at step {first} "
          f"-> lead {None if first is None or cross is None else cross - first} steps; false alarms in calm part: {false_alarms}/30")

    # 2) sudden step jump (like the dashboard's 'Inject Failure')
    jump = calm[:30] + [4.5 + 3.4] * 15
    out = _replay(ml, jump)
    print(f"Step-jump test: risk after jump = {out[30]['risk_level']} (temp {jump[30]:.1f}C)")

    # 3) single-reading sensor glitch: should not stay alarmed
    glitch = calm[:30] + [15.0] + calm[30:45]
    out = _replay(ml, glitch)
    print(f"Glitch test: at spike = {out[30]['risk_level']}, 3 readings later = {out[33]['risk_level']}")


if __name__ == "__main__":
    _selftest()
