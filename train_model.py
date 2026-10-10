"""Train the FrostGuard forecaster + anomaly detector and save the artifact.

Run this whenever frost_ml.py changes or scikit-learn is upgraded, then
commit the regenerated frostguard_ml.joblib. The dashboard loads that file
at boot instead of retraining, which keeps cold starts fast on small hosts.

NOTE: scikit-learn is pinned in requirements.txt because the artifact
records the version it was trained with and is rejected on mismatch.
(KNN routing artifact: see train_knn.py.)
"""
from __future__ import annotations

from config import CONFIG, resolve_path
from frost_ml import FrostGuardML


def main() -> None:
    engine = FrostGuardML()  # trains on the built-in thermal simulator
    artifact_path = resolve_path(CONFIG["ml"]["model_artifact"])
    engine.save_artifact(artifact_path)
    print(f"Saved FrostGuard ML artifact: {artifact_path}")
    print(f"Training rows: {engine.training_rows}")


if __name__ == "__main__":
    main()
