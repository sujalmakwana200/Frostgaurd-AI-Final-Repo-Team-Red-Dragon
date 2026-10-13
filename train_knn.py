from __future__ import annotations

from config import CONFIG, resolve_path
from knn_adapter import train_from_config


def main() -> None:
    model = train_from_config()
    artifact_path = resolve_path(CONFIG["ml"]["knn_artifact"])
    model.save(artifact_path)
    print(f"Saved FrostGuard KNN adapter: {artifact_path}")
    print(f"Training rows: {model.training_rows}")


if __name__ == "__main__":
    main()
