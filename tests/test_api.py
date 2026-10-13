"""
tests/test_api.py — FrostGuard API hardening tests.

Run from the repo root:
    export FROSTGUARD_API_KEY=testkey      # Windows: set FROSTGUARD_API_KEY=testkey
    pytest -q

If your routes are named differently (e.g. /ingest instead of /telemetry),
change the two path constants below.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

# Make `import api` work when tests live in tests/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

TEST_KEY = "testkey"
os.environ.setdefault("FROSTGUARD_API_KEY", TEST_KEY)
os.environ["FROSTGUARD_API_KEY"] = TEST_KEY

TELEMETRY_PATH = "/telemetry"
COMMAND_PATH = "/command"
HEADER = "X-FrostGuard-Key"


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient

    import api  # noqa: WPS433 — imported after env is set

    with TestClient(api.app) as c:
        yield c


def _payload(**overrides):
    base = {
        "truck_id": "GJ01-TEST",
        "cargo": "Vaccines",
        "temperature": 4.2,
        "status": "SAFE",
        "lat": 22.31,
        "lng": 73.18,
        "timestamp": "2026-10-13T09:30:00Z",
        "speed_kmh": 60.0,
    }
    base.update(overrides)
    return base


# ───────────── health ─────────────
def test_health_is_public(client):
    r = client.get("/health")
    assert r.status_code == 200


def test_health_returns_json(client):
    assert isinstance(client.get("/health").json(), dict)


# ───────────── auth ─────────────
def test_telemetry_without_key_is_401(client):
    r = client.post(TELEMETRY_PATH, json=_payload())
    assert r.status_code == 401


def test_telemetry_with_wrong_key_is_401(client):
    r = client.post(TELEMETRY_PATH, json=_payload(), headers={HEADER: "nope"})
    assert r.status_code == 401


def test_command_without_key_is_401(client):
    r = client.post(COMMAND_PATH, json={"truck_id": "GJ01-TEST", "action": "reroute"})
    assert r.status_code == 401


def test_telemetry_with_key_is_accepted(client):
    r = client.post(TELEMETRY_PATH, json=_payload(), headers={HEADER: TEST_KEY})
    assert r.status_code in (200, 201, 202)


# ───────────── validation ─────────────
def test_temperature_out_of_range_is_422(client):
    r = client.post(TELEMETRY_PATH, json=_payload(temperature=-200), headers={HEADER: TEST_KEY})
    assert r.status_code == 422


def test_latitude_out_of_range_is_422(client):
    r = client.post(TELEMETRY_PATH, json=_payload(lat=400), headers={HEADER: TEST_KEY})
    assert r.status_code == 422


def test_bad_timestamp_is_422(client):
    r = client.post(TELEMETRY_PATH, json=_payload(timestamp="yesterday"), headers={HEADER: TEST_KEY})
    assert r.status_code == 422


def test_unknown_status_is_422(client):
    r = client.post(TELEMETRY_PATH, json=_payload(status="MELTED"), headers={HEADER: TEST_KEY})
    assert r.status_code == 422


def test_lowercase_status_is_normalised(client):
    r = client.post(TELEMETRY_PATH, json=_payload(status="safe"), headers={HEADER: TEST_KEY})
    assert r.status_code in (200, 201, 202)


def test_truck_id_with_bad_chars_is_422(client):
    r = client.post(TELEMETRY_PATH, json=_payload(truck_id="GJ01 <script>"), headers={HEADER: TEST_KEY})
    assert r.status_code == 422
