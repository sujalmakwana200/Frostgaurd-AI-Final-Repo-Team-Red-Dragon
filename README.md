Rohit382538
# FrostGuard AI - Cold Chain Command Center

FrostGuard AI is a Streamlit dashboard for live cold-chain fleet monitoring. It tracks medical cargo trucks, forecasts temperature risk, shows KNN rerouting decisions, and speaks alert messages once per alert episode.

## Current Status

The project is stable for local demo and submission using:

```bash
streamlit run main_dashboard.py
```

`main_dashboard.py` remains the entry point. The dashboard auto-starts the local Flask bridge if it is offline, so users do not need to manually run `Bridge.py`.

## Main Features

- Black FrostGuard dashboard theme with blue-accent fleet detail cards.
- Live Streamlit fragments instead of a blocking refresh loop.
- 13 trucks loaded from `config/frostguard_config.json`.
- Multiple city routes, including local Gujarat and long-haul routes.
- Road-style fleet progress strip with a small truck marker.
- Real healthcare IoT dataset fields shown in each truck card:
  - bag ID
  - product type
  - blood type
  - hospital route
  - live temperature
  - temperature range
  - humidity
  - handling stress
  - health index
  - breach probability
  - predicted temperature
- KNN reroute support using `frostguard_knn.joblib`.
- ML insight support through `frost_ml.py`.
- Voice alerts prefer a female English browser voice when available.
- Voice alerts speak only once per truck/status alert episode.
- Optional Supabase sync through environment variables.

## Architecture

```text
streamlit run main_dashboard.py
        |
        v
main_dashboard.py
        |
        |-- auto-starts Bridge.py if /health is offline
        |-- reads live fleet from /fleet and /latest
        |-- renders Streamlit dashboard fragments
        |-- shows map, metrics, alerts, truck cards, charts
        |
        v
Bridge.py
        |
        |-- GET  /health
        |-- GET  /fleet
        |-- GET  /latest
        |-- POST /telemetry
        |-- GET  /ml_insight
        |-- GET  /predictions
        |-- GET  /summary
        |-- POST /command
        |-- POST /reset
        |
        v
frost_ml.py + knn_adapter.py + model artifacts
        |
        v
local CSV/data storage and optional Supabase sync
```

## Project Tree

```text
frostgaurd_final_v2/
|-- main_dashboard.py
|-- Bridge.py
|-- api.py
|-- frost_ml.py
|-- knn_adapter.py
|-- config.py
|-- requirements.txt
|-- README.md
|-- frostguard_knn.joblib
|-- frostguard_ml.joblib
|-- frostguard_ml.pkl
|-- config/
|   `-- frostguard_config.json
|-- data/
|   `-- healthcare_iot_target_dataset.csv
|-- logs/
|   |-- bridge_stdout.log
|   `-- bridge_stderr.log
`-- __pycache__/
```

## Local Setup

Create and activate a virtual environment:

```bash
python -m venv .venv
.venv\Scripts\activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Run the dashboard:

```bash
streamlit run main_dashboard.py
```

Open the URL printed by Streamlit, usually:

```text
http://localhost:8501
```

## Deployment Notes

For deployment, keep these files in the deployed project:

- `main_dashboard.py`
- `Bridge.py`
- `frost_ml.py`
- `knn_adapter.py`
- `requirements.txt`
- `config/frostguard_config.json`
- `data/healthcare_iot_target_dataset.csv`
- `frostguard_knn.joblib`
- `frostguard_ml.joblib` or `frostguard_ml.pkl`

The local OneDrive paths are only fallback paths. The project now also includes the config and healthcare dataset locally, so deployment should not depend on your computer path.

Recommended start command:

```bash
streamlit run main_dashboard.py
```

The dashboard will start the bridge automatically. If the bridge is unavailable, the dashboard should keep rendering with fallback data instead of crashing.

## Optional Cloud Environment Variables

Supabase is optional. The app works locally without it.

```text
SUPABASE_URL=your_supabase_project_url
SUPABASE_SERVICE_ROLE_KEY=your_service_role_key
```

Alternative key name:

```text
SUPABASE_KEY=your_supabase_key
```

Optional dataset override:

```text
DATASET_PATH=data/healthcare_iot_target_dataset.csv
```

Optional fleet log path:

```text
FLEET_CSV=fleet_logs.csv
```

## Verification

Compile check:

```bash
python -m py_compile main_dashboard.py Bridge.py frost_ml.py knn_adapter.py config.py
```

Bridge smoke test:

```bash
python -c "import Bridge; fleet=Bridge._simulate_fleet(); print(len(fleet), fleet[0]['truck_id'])"
```

Expected result:

```text
13 TRK-RD-001
```

## Submission Demo Flow

1. Run `streamlit run main_dashboard.py`.
2. Confirm the bridge connects automatically.
3. Use the truck selector to switch between trucks.
4. Scroll below the map to show the blue fleet detail cards.
5. Press `Inject Failure` to demonstrate warning or critical behavior.
6. Show KNN reroute text in the truck card.
7. Confirm voice alert speaks once, not every dashboard update.
