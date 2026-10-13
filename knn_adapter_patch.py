"""
knn_adapter.py — PATCHES.

1) `load()` currently raises on ANY sklearn version difference. Pickles from
   the same major.minor are fine; only warn on a patch difference and raise
   only when the artifact format itself is wrong.
2) Add `train_synthetic()` so the dashboard/API can self-heal when the
   artifact is missing or incompatible.
"""
from __future__ import annotations

import logging
import random

import joblib
import sklearn

log = logging.getLogger("frostguard.knn")
ARTIFACT_FORMAT = "frostguard-knn-v1"


# ───── Replace the body of FrostGuardKNNAdapter.load() with this ─────
@classmethod
def load(cls, path: str) -> "FrostGuardKNNAdapter":
    art = joblib.load(path)
    if art.get("format") != ARTIFACT_FORMAT:
        raise ValueError(f"Unexpected artifact format {art.get('format')!r}")

    saved = str(art.get("sklearn", ""))
    cur = sklearn.__version__
    if saved.rsplit(".", 1)[0] != cur.rsplit(".", 1)[0]:
        # major.minor differ -> pickle layout may differ -> caller should retrain
        raise ValueError(f"sklearn {saved} != {cur} (major.minor mismatch)")
    if saved != cur:
        log.warning("KNN artifact built with sklearn %s, running %s (patch diff, OK).", saved, cur)

    return cls(pipeline=art["pipeline"], training_rows=art["training_rows"])


# ───── Add this module-level function (uses your existing _synthetic_sample) ─────
def train_synthetic(n_rows: int = 4000, seed: int = 42) -> "FrostGuardKNNAdapter":
    """Train a fresh adapter on synthetic telemetry. Used as a fallback."""
    rng = random.Random(seed)
    X, y = [], []
    for _ in range(n_rows):
        vec, label = _synthetic_sample(rng)  # noqa: F821 — defined in your file
        X.append(vec)
        y.append(label)
    return FrostGuardKNNAdapter().fit(X, y)  # noqa: F821
