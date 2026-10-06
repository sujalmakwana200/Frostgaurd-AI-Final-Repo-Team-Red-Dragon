"""
FrostGuardKNNAdapter — a real, trainable KNN breach-risk classifier.

This replaces a version that referenced a `train_from_config()` function
that never existed, so `train_knn.py` crashed immediately if run.

What this model actually predicts: given a 15-feature telemetry snapshot
(temperature stats, humidity, door activity, handling/weather signals —
the same vector Bridge.py's `_knn_vector()` builds), it predicts the
probability the shipment is heading for a temperature breach. That
probability feeds `_knn_reroute()` in Bridge.py, which combines it with
haversine distance to each of the 16 cold-storage nodes to pick a target
— the facility choice itself is a scoring loop, not what the KNN model
predicts directly.
"""
from __future__ import annotations

import os
import random
from typing import Any

import joblib
import sklearn
from sklearn.neighbors import KNeighborsClassifier
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

ARTIFACT_FORMAT = "frostguard-knn-v1"


class FrostGuardKNNAdapter:
    """Thin wrapper around a scikit-learn Pipeline(StandardScaler, KNeighborsClassifier)."""

    def __init__(self, pipeline: Pipeline | None = None, training_rows: int = 0):
        self.pipeline = pipeline
        self.training_rows = training_rows

    # ------------------------------------------------------------ training
    def fit(self, X: list[list[float]], y: list[int]) -> "FrostGuardKNNAdapter":
        self.pipeline = Pipeline([
            ("scale", StandardScaler()),
            ("knn", KNeighborsClassifier(n_neighbors=15, weights="distance")),
        ])
        self.pipeline.fit(X, y)
        self.training_rows = len(X)
        return self

    # ------------------------------------------------------------ inference
    def predict(self, X):
        return self.pipeline.predict(X)

    def predict_proba(self, X):
        if hasattr(self.pipeline, "predict_proba"):
            return self.pipeline.predict_proba(X)
        return None

    def kneighbors(self, X, n_neighbors=None, return_distance=True):
        model = getattr(self, "pipeline", self)
        if hasattr(model, "kneighbors"):
            return model.kneighbors(X, n_neighbors=n_neighbors, return_distance=return_distance)
        if hasattr(model, "named_steps"):
            for _, step in reversed(model.steps):
                if hasattr(step, "kneighbors"):
                    return step.kneighbors(X, n_neighbors=n_neighbors, return_distance=return_distance)
        raise AttributeError("KNN artifact does not expose kneighbors().")

    @property
    def classes_(self):
        model = getattr(self, "pipeline", self)
        if hasattr(model, "named_steps"):
            return model.named_steps["knn"].classes_
        return getattr(model, "classes_", [0, 1])

    # ------------------------------------------------------------ persistence
    def save(self, artifact_path: str) -> None:
        os.makedirs(os.path.dirname(artifact_path) or ".", exist_ok=True)
        joblib.dump({
            "format": ARTIFACT_FORMAT,
            "sklearn": sklearn.__version__,
            "pipeline": self.pipeline,
            "training_rows": self.training_rows,
        }, artifact_path)

    @classmethod
    def load(cls, artifact_path: str) -> "FrostGuardKNNAdapter":
        art = joblib.load(artifact_path)
        if art.get("format") != ARTIFACT_FORMAT:
            raise ValueError("KNN artifact format mismatch")
        if art.get("sklearn") != sklearn.__version__:
            raise ValueError(f"sklearn {art.get('sklearn')} != {sklearn.__version__}")
        return cls(pipeline=art["pipeline"], training_rows=art["training_rows"])


def _synthetic_sample(rng: random.Random) -> tuple[list[float], int]:
    """One synthetic (feature_vector, breach_label) pair.

    Breach is defined by a slightly richer rule than Bridge.py's simple
    linear fallback (temperature alone) — it also factors in handling
    stress, health index, and weather risk, so the trained classifier
    genuinely captures more than the fallback it's meant to improve on.
    """
    temp = rng.uniform(1.0, 11.0)
    temp_min = temp - rng.uniform(0.0, 1.5)
    temp_max = temp + rng.uniform(0.0, 1.5)
    temp_std = rng.uniform(0.02, 0.6)
    frac_above_6 = min(1.0, max(0.0, (temp - 5.0) / 3.0 + rng.uniform(-0.1, 0.1)))
    frac_above_8 = min(1.0, max(0.0, (temp - 7.0) / 3.0 + rng.uniform(-0.1, 0.1)))
    hum_mean = rng.uniform(45.0, 75.0)
    hum_std = rng.uniform(0.5, 6.0)
    door_count = float(rng.randint(0, 6))
    accel_rms = rng.uniform(0.01, 0.25)
    handling_stress = rng.uniform(0.1, 0.95)
    health_index = rng.uniform(0.2, 1.0)
    ambient_temp = rng.uniform(22.0, 42.0)
    ambient_humidity = rng.uniform(35.0, 80.0)
    weather_risk = rng.uniform(0.1, 0.9)

    risk_score = (
        0.55 * max(0.0, (temp - 6.5) / 5.0)
        + 0.15 * handling_stress
        + 0.15 * (1.0 - health_index)
        + 0.10 * weather_risk
        + 0.05 * door_count / 6.0
        + rng.uniform(-0.05, 0.05)
    )
    label = 1 if risk_score > 0.42 else 0

    vector = [
        temp, temp_min, temp_max, temp_std, frac_above_6, frac_above_8,
        hum_mean, hum_std, door_count, accel_rms, handling_stress,
        health_index, ambient_temp, ambient_humidity, weather_risk,
    ]
    return vector, label


def train_from_config(n_samples: int = 8000, seed: int = 42) -> FrostGuardKNNAdapter:
    rng = random.Random(seed)
    X, y = [], []
    for _ in range(n_samples):
        vec, label = _synthetic_sample(rng)
        X.append(vec)
        y.append(label)
    model = FrostGuardKNNAdapter().fit(X, y)
    print(f"[FrostGuardKNNAdapter] trained on {model.training_rows} synthetic samples "
          f"({sum(y)} breach / {len(y) - sum(y)} safe)")
    return model
