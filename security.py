"""
security.py — shared-secret API-key check for FrostGuard.

Set FROSTGUARD_API_KEY in the environment (see .env.example). Clients send
the same value in the `X-FrostGuard-Key` header on every POST.

FastAPI usage (api.py):
    from security import require_api_key
    @app.post("/telemetry", dependencies=[Depends(require_api_key)])

Flask usage (only if you kept Bridge.py):
    from security import flask_require_api_key
    @app.route("/command", methods=["POST"])
    @flask_require_api_key
    def command(): ...
"""
from __future__ import annotations

import hmac
import os
from functools import wraps
from typing import Optional

from fastapi import Header, HTTPException

API_KEY_HEADER = "X-FrostGuard-Key"


def _expected_key() -> str:
    key = os.environ.get("FROSTGUARD_API_KEY", "").strip()
    if not key:
        # Fail closed: a server with no key configured must not accept writes.
        raise HTTPException(
            status_code=503,
            detail="Server misconfigured: FROSTGUARD_API_KEY is not set",
        )
    return key


async def require_api_key(
    x_frostguard_key: Optional[str] = Header(default=None, alias=API_KEY_HEADER),
) -> None:
    """FastAPI dependency. Raises 401 unless the header matches the configured key."""
    expected = _expected_key()
    if x_frostguard_key is None or not hmac.compare_digest(x_frostguard_key, expected):
        raise HTTPException(
            status_code=401,
            detail="Missing or invalid API key",
            headers={"WWW-Authenticate": API_KEY_HEADER},
        )


def flask_require_api_key(fn):
    """Flask decorator equivalent of require_api_key (for Bridge.py, if kept)."""

    @wraps(fn)
    def wrapper(*args, **kwargs):
        from flask import abort, request  # imported lazily: flask is optional

        expected = os.environ.get("FROSTGUARD_API_KEY", "").strip()
        got = request.headers.get(API_KEY_HEADER, "")
        if not expected or not hmac.compare_digest(got, expected):
            abort(401)
        return fn(*args, **kwargs)

    return wrapper
