"""
Bridge.py — PATCHES (only if you decide to KEEP Bridge.py; the
recommendation in FIXES.md is to delete it and keep api.py).

1) Use the anon key, not the service-role key.
2) Stop swallowing Supabase errors.
3) Protect write routes.
"""
from __future__ import annotations

import logging
import os
from typing import Any

log = logging.getLogger("frostguard.bridge")

# ───── Replace the SUPABASE_* lines ─────
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
# The anon key + a Row-Level-Security INSERT policy is all a telemetry
# writer needs. The service-role key bypasses RLS entirely and must never
# ship inside a client/edge process.
SUPABASE_KEY = os.environ.get("SUPABASE_ANON_KEY", "")
if os.environ.get("SUPABASE_SERVICE_ROLE_KEY"):
    log.warning(
        "SUPABASE_SERVICE_ROLE_KEY is set but ignored — use SUPABASE_ANON_KEY "
        "with an RLS insert policy instead."
    )


# ───── Replace _sync_supabase() ─────
_SUPABASE_FAILS = 0


def _sync_supabase(table: str, row: dict[str, Any]) -> None:
    global _SUPABASE_FAILS
    client = _load_supabase()  # noqa: F821 — your existing function
    if client is None:
        return
    try:
        client.table(table).insert(row).execute()
        _SUPABASE_FAILS = 0
    except Exception as exc:  # network / auth / schema
        _SUPABASE_FAILS += 1
        # Log the first failure and then every 50th so a revoked key is visible
        # without flooding the log on every telemetry tick.
        if _SUPABASE_FAILS == 1 or _SUPABASE_FAILS % 50 == 0:
            log.error("Supabase insert into %s failed (%d so far): %s", table, _SUPABASE_FAILS, exc)


# ───── Protect the write routes ─────
# from security import flask_require_api_key
#
# @app.route("/command", methods=["POST"])
# @flask_require_api_key
# def command(): ...
#
# Same for /register_sim and any reset route.
# Bridge.py already binds to 127.0.0.1 — keep it that way.
