# FrostGuard AI — Security & Bug Fix Pack

Apply in this order. ~45 minutes total. Each step is independently committable,
so you get a clean, readable commit history a recruiter can scroll through.

---

## 0. Branch

```bash
git checkout -b hardening
```

## 1. Drop the files from this pack into the repo root

```
security.py            -> repo root (new file)
tests/test_api.py      -> tests/ (new folder; add an empty tests/__init__.py)
.gitignore             -> repo root (replace)
requirements.txt       -> repo root (replace)
.env.example           -> repo root (new)
```

## 2. Purge committed binaries and logs from git

```bash
git rm --cached frostguard_knn.joblib frostguard_ml.joblib frostguard_ml.pkl
git rm -r --cached logs fleet_logs.csv 2>/dev/null
git commit -m "chore: stop tracking model binaries, logs and runtime CSV"
```

The files stay on your disk; they're just no longer in the repo. The app
retrains on boot when they're absent (see step 5).

## 3. Retire Bridge.py (one backend, not two)

`api.py` and `Bridge.py` both bind port 5000 and do overlapping work. Keep
FastAPI (async, pydantic validation, auto docs at `/docs`).

```bash
git rm Bridge.py
git commit -m "refactor: remove Flask bridge; FastAPI is the single backend"
```

If `Bridge.py` has a route `api.py` lacks (e.g. `/ml_insight`, Discord webhook),
port that route into `api.py` first. If you must keep Bridge.py for now, apply
`bridge_patch.py` instead.

## 4. Patch api.py — `api_patch.py`

- Replace the header region (imports → `_ml_engine = ...`) with section (1).
- Replace `class TelemetryPayload` with section (2).
- Add `dependencies=[Depends(require_api_key)]` to every `@app.post(...)` — section (3).
- Replace the `if __name__ == "__main__":` block with section (4).

What this changes:

| Before | After |
|---|---|
| `allow_origins=["*"]` | dashboard origins only (`ALLOWED_ORIGINS` env) |
| any float / string accepted | physical bounds, ISO timestamp, status enum |
| no auth on POST | `X-FrostGuard-Key` header required |
| `host="0.0.0.0"` | `127.0.0.1` unless `API_HOST` set |

## 5. Patch main_dashboard.py — `main_dashboard_patch.py`

- Delete the uvicorn `subprocess.Popen` launcher and the old `ensure_services()`; paste the new `ensure_services()`.
- Remove `import subprocess` / `import sys` if nothing else uses them.
- Replace `_load_knn()` with the new `get_knn_router()` so a missing/incompatible artifact **warns and retrains** instead of silently disabling routing.

## 6. Patch knn_adapter.py — `knn_adapter_patch.py`

- Replace `load()` (tolerates patch-version differences; raises only on major.minor mismatch).
- Add `train_synthetic()`.

## 7. Normalise line endings

```bash
printf '* text=auto\n*.py text eol=lf\n' > .gitattributes
git add --renormalize .
git commit -m "chore: enforce LF line endings"
```

## 8. Run the tests

```bash
pip install -r requirements.txt
export FROSTGUARD_API_KEY=testkey   # Windows: set FROSTGUARD_API_KEY=testkey
pytest -q
```

Expect 12 passing. If `/health` or `/telemetry` are named differently in your
`api.py`, adjust the paths in `tests/test_api.py`.

## 9. Add a CI badge (2 minutes, big credibility win)

`.github/workflows/ci.yml`:

```yaml
name: CI
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.12" }
      - run: pip install -r requirements.txt
      - run: pytest -q
        env: { FROSTGUARD_API_KEY: ci-test-key }
```

## 10. README edits

**Environment table** — replace with:

| Variable | Required | Purpose |
|---|---|---|
| `FROSTGUARD_API_KEY` | yes (API) | Shared secret for POST endpoints (`X-FrostGuard-Key` header) |
| `ALLOWED_ORIGINS` | no | Comma-separated CORS origins. Default: localhost:8501 |
| `API_HOST` / `PORT` | no | Bind address/port. Default `127.0.0.1:5000` |
| `SUPABASE_URL` | no | Supabase project URL |
| `SUPABASE_ANON_KEY` | no | Anon key (used with an RLS insert policy — never the service-role key) |
| `DISCORD_WEBHOOK` | no | Webhook URL for CRITICAL alerts |
| `DATASET_PATH` | no | Override path to the healthcare IoT CSV |
| `FLEET_CSV` | no | Override path for fleet log output |

**Project tree** — remove `Bridge.py`, the three `.joblib/.pkl` lines and `logs/`; add `security.py`, `tests/`, `.github/workflows/ci.yml`.

**Wording** — change "production-grade" to "production-style prototype" and add one line with real numbers from `/health`, e.g. *"Forecast MAE 0.4 °C, R² 0.91 on a 20 % held-out split."* Use your actual values.

**Rename the repo** (Settings → General) to `FrostGuard-AI` — the "Frostgaurd" typo is the first thing a hiring manager sees. GitHub redirects the old URL automatically.

## 11. Supabase side (if you use it)

In the Supabase SQL editor:

```sql
alter table telemetry enable row level security;
create policy "edge can insert" on telemetry
  for insert to anon with check (true);
```

Then rotate the service-role key you previously used (Project Settings → API → Reset), since it was in an app process.

---

## Commit message for the whole branch (if squashing)

```
Harden API and tidy repo

- Require API key on all write endpoints; restrict CORS; bind to loopback
- Validate telemetry payloads (bounds, ISO timestamps, status enum)
- Swap Supabase service-role key for anon key + RLS; log sync failures
- Remove duplicate Flask backend; dashboard no longer spawns a server
- Tolerant model-artifact loading with retrain fallback
- Stop tracking model binaries/logs; add tests and CI
```
