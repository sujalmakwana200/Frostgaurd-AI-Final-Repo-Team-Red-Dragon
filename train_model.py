from __future__ import annotations

import os

from config import CONFIG, resolve_path
from frost_ml import FrostGuardML


def first_existing_dataset() -> str | None:
    datasets = CONFIG["datasets"]
    for key in ("primary", "fallback"):
        path = resolve_path(datasets[key])
        if os.path.exists(path):
            return path
    return None


def main() -> None:
    bridge = CONFIG["bridge"]
    ml_config = CONFIG["ml"]
    dataset_path = first_existing_dataset()
    artifact_path = resolve_path(ml_config["model_artifact"])
    pickle_path = resolve_path(ml_config["pickle_artifact"])
    csv_path = resolve_path(bridge["csv_file"])

    model = FrostGuardML(
        csv_path=csv_path,
        dataset_path=dataset_path,
        window_size=int(ml_config["window_size"]),
        training_sample_rows=int(ml_config["training_sample_rows"]),
        forecast_steps=int(ml_config["forecast_steps"]),
        seconds_per_step=int(ml_config["seconds_per_step"]),
    )
    model.save_artifact(artifact_path)
    model.save_artifact(pickle_path)
    print(f"Saved FrostGuard ML artifact: {artifact_path}")
    print(f"Saved FrostGuard pickle artifact: {pickle_path}")
    print(f"Training rows: {model.training_rows}")
    print(f"Dataset: {dataset_path or 'fleet logs / synthetic fallback'}")


if __name__ == "__main__":
    main()
