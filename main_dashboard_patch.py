"""
main_dashboard.py — PATCHES.

Two edits. Everything else in the dashboard stays as-is.
"""

# ───────────── EDIT 1: replace the whole launcher + ensure_services() ─────────────
# Delete the function that builds `popen_kwargs` and calls subprocess.Popen(
#   [sys.executable, "-m", "uvicorn", "api:app", "--host", "0.0.0.0", "--port", "5000"], ...)
# and delete ensure_services(). Replace both with this:

import os
import requests
import streamlit as st

API_BASE = os.environ.get("FROSTGUARD_API_BASE", "http://127.0.0.1:5000")


def ensure_services() -> bool:
    """
    The dashboard runs its ML models in-process (get_ml_engine / get_knn_router),
    so it no longer spawns a backend. If an API is running we use it for
    the fleet feed; if not, we fall back to the in-process simulation.
    Returns True when the external API is reachable.
    """
    if "api_online" in st.session_state:
        return st.session_state.api_online
    try:
        r = requests.get(f"{API_BASE}/health", timeout=1.5)
        st.session_state.api_online = r.ok
    except requests.RequestException:
        st.session_state.api_online = False
    return st.session_state.api_online


# Then remove the now-unused imports at the top of the file:
#   import subprocess
#   import sys
# (keep `time` if it's used elsewhere.)


# ───────────── EDIT 2: warn loudly when the KNN artifact is missing ─────────────
# Find _load_knn() (or wherever `frostguard_knn.joblib` is loaded) and
# replace the silent `if os.path.exists(...)` with:

import logging
from pathlib import Path

log = logging.getLogger("frostguard.dashboard")
KNN_ARTIFACT = Path(__file__).resolve().parent / "frostguard_knn.joblib"


@st.cache_resource(show_spinner=False)
def get_knn_router():
    from knn_adapter import FrostGuardKNNAdapter

    if KNN_ARTIFACT.exists():
        try:
            return FrostGuardKNNAdapter.load(str(KNN_ARTIFACT))
        except ValueError as exc:
            # sklearn version mismatch -> retrain instead of crashing
            log.warning("KNN artifact unusable (%s); retraining in-process.", exc)
    else:
        log.warning("KNN artifact %s not found; training in-process.", KNN_ARTIFACT)
        st.toast("KNN routing model not found — training a fresh one (≈2 s).", icon="⚠️")

    from knn_adapter import train_synthetic  # see knn_adapter_patch.py
    return train_synthetic()
