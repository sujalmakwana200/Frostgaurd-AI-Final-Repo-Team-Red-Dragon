# FrostGuard AI 🧊
### Cold Chain Command Center — Real-Time Healthcare Logistics Intelligence

> A production-grade fleet monitoring system for cold-chain medical cargo, built for Gujarat's pharmaceutical and blood-bank logistics corridors.

[![Live Demo](https://img.shields.io/badge/Live_Demo-FrostGuard_AI-FF4B4B?style=for-the-badge&logo=streamlit&logoColor=white)](https://frostgaurd-ai-final-repo-team-red-dragon.onrender.com)

---

## Tech Stack

![Python](https://img.shields.io/badge/Python-3.12-3776AB?style=for-the-badge&logo=python&logoColor=white)
![Streamlit](https://img.shields.io/badge/Streamlit-1.37+-FF4B4B?style=for-the-badge&logo=streamlit&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-Optional-009688?style=for-the-badge&logo=fastapi&logoColor=white)
![Flask](https://img.shields.io/badge/Flask-Optional-000000?style=for-the-badge&logo=flask&logoColor=white)
![scikit-learn](https://img.shields.io/badge/scikit--learn-1.8-F7931E?style=for-the-badge&logo=scikit-learn&logoColor=white)
![Pandas](https://img.shields.io/badge/Pandas-2.2-150458?style=for-the-badge&logo=pandas&logoColor=white)
![NumPy](https://img.shields.io/badge/NumPy-1.26-013243?style=for-the-badge&logo=numpy&logoColor=white)
![Supabase](https://img.shields.io/badge/Supabase-Optional-3ECF8E?style=for-the-badge&logo=supabase&logoColor=white)
![Google Gemini](https://img.shields.io/badge/Google_Gemini-Optional-4285F4?style=for-the-badge&logo=google&logoColor=white)
![PyDeck](https://img.shields.io/badge/PyDeck-Maps-FF6B35?style=for-the-badge&logo=mapbox&logoColor=white)

---

## Team

![Sharang](https://img.shields.io/badge/Sharang-Product_Owner-6C3483?style=for-the-badge&logo=producthunt&logoColor=white)
![Alan](https://img.shields.io/badge/Alan-Business_SPOC-1A5276?style=for-the-badge&logo=handshake&logoColor=white)
![Sujal](https://img.shields.io/badge/Sujal-Tech_Lead-E74C3C?style=for-the-badge&logo=lightning&logoColor=white)
![Ritik](https://img.shields.io/badge/Ritik-Developer-2ECC71?style=for-the-badge&logo=github&logoColor=white)
![Rohit](https://img.shields.io/badge/Rohit-Developer-2ECC71?style=for-the-badge&logo=github&logoColor=white)
![Danish](https://img.shields.io/badge/Danish-QA-F39C12?style=for-the-badge&logo=checkmarx&logoColor=white)
![Dheeraj](https://img.shields.io/badge/Dheeraj-Intern-95A5A6?style=for-the-badge&logo=graduationcap&logoColor=white)

---

## The Problem

India's cold chain for healthcare — vaccines, insulin, blood bags, organ transport — is critically under-monitored. A single temperature breach can destroy an entire shipment worth lakhs of rupees and, more importantly, put patient lives at risk. Existing solutions offer basic GPS tracking but no predictive intelligence.

**FrostGuard AI solves this.**

---

## What It Does

FrostGuard AI is a live Streamlit dashboard that monitors a fleet of 13 medical cargo trucks. It doesn't just show you what's happening — it forecasts what's *about to* happen and recommends the nearest safe cold storage before a breach occurs.

| Capability | How |
|---|---|
| Live fleet monitoring | 13 simulated trucks on real OSRM road routes, refreshed every 3–6 s by Streamlit fragments |
| Breach prediction | HistGradientBoosting forecaster predicts the temperature change out to a 30 s horizon |
| Anomaly detection | Isolation Forest flags irregular thermal behavior |
| Smart rerouting | KNN (scikit-learn `NearestNeighbors`) picks the nearest of 16 cold-storage nodes when a truck is at risk |
| Voice alerts | Browser Web Speech API, fires once per breach episode |
| Failure injection | **Inject Failure** button simulates a compressor fault so you can watch the pipeline react |

> **Data note:** the fleet is simulated and the models are trained on a synthetic thermal simulator (`frost_ml.simulate_trace`). They have not been validated on real sensor data.

---

## Demo

```bash
git clone https://github.com/sujalmakwana200/Frostgaurd-AI-Final-Repo-Team-Red-Dragon.git
cd Frostgaurd-AI-Final-Repo-Team-Red-Dragon
python -m venv .venv && .venv\Scripts\activate   # Windows
pip install -r requirements.txt
streamlit run main_dashboard.py
```

Open `http://localhost:8501`. The dashboard is self-contained: it loads the pre-trained model (`frostguard_ml.joblib`) and runs inference in-process. No separate backend needs to be started.

**Demo flow:**
1. Use the truck selector to browse all 13 active trucks
2. Scroll below the map to view live fleet detail cards
3. Hit **Inject Failure** on any truck to simulate a breach event
4. Watch the KNN reroute kick in and the voice alert fire
5. Check the Event Log panel for a timestamped breach history

---

## System Architecture

```
streamlit run main_dashboard.py      (single process)
        │
        ├── get_ml_engine()   loads frostguard_ml.joblib  (no training at boot)
        ├── get_knn_router()  fits NearestNeighbors on the 16 cold-storage nodes
        ├── routes_cache.json precomputed OSRM road geometries
        ├── demo_fleet()      simulates 13 trucks each refresh
        │        └── FrostGuardML.analyze() → risk, forecast, anomaly, breach probability
        └── Streamlit fragments render: map · metrics · alerts · fleet cards · event log
```

### Optional standalone services (not required by the dashboard)

`Bridge.py` (Flask) and `api.py` (FastAPI) are REST backends for telemetry ingestion. Run one manually on port 5000 if you want to feed real/replayed telemetry; the dashboard merges live data over its simulation when it finds one.

| Service | Run with | Notes |
|---|---|---|
| `Bridge.py` | `python Bridge.py` | Fuller API (`/truck/<id>`, `/ml_insight`, `/predictions`, `/summary`, `/command`, `/register_sim`), Discord webhook on CRITICAL (opt-in via `DISCORD_WEBHOOK`), optional Supabase sync, KNN breach-risk classifier from `frostguard_knn.joblib`. Trains its own ML model at startup, so it is heavier. |
| `api.py` | `python api.py` | Minimal API (`/telemetry`, `/fleet`, `/latest`, `/health`, `/reset`). Its reroute logic is a placeholder stub, not the trained KNN. |
| `trip_replay.py` | `python trip_replay.py` | Replays a bag from `data/healthcare_iot_target_dataset.csv` (not committed) to `:5000/telemetry`. |

---

## ML Pipeline

The ML engine (`frost_ml.py`) runs two models in tandem, each on its own feature set:

- **Forecaster features (12):** `temperature`, `temp_delta`, `temp_delta_2`, `temp_delta_3`, `temp_delta_6`, `temp_rolling_mean_6`, `temp_rolling_std_6`, `temp_range_6`, `door_open`, `ambient_temp_c`, `headroom_c`, `minutes_above_safe`
- **Detector features (8):** `temperature`, `temp_delta`, `temp_delta_2`, `temp_delta_3`, `temp_rolling_std_6`, `temp_range_6`, `door_open`, `ambient_temp_c`

### Models

**1. Isolation Forest — Anomaly Detector**
- Detects abnormal thermal patterns (e.g. sudden spike, sensor drift, door left open)
- Trained on 48,000 rows from the built-in thermal simulator (200 traces × 300 steps, with injected faults)
- Outputs: `anomaly: bool`, `anomaly_score: 0–100`

**2. HistGradientBoostingRegressor — Temperature Forecaster**
- Direct multi-horizon forecasting: separate models predict the temperature *change* at 20%, 50% and 100% of the 30 s window, then interpolate (avoids compounding error)
- Targets are `truth[t+h] − measured[t]`, so the model can't score well by just echoing the current reading
- Outputs: `predicted_temp_30s`, `forecast_series`, `time_to_critical_sec`

**3. KNN — Facility Router (in `main_dashboard.py`)**
- `NearestNeighbors` over the lat/lon of the 16 cold-storage nodes, queried with the truck's GPS position
- Separately, `Bridge.py` uses `frostguard_knn.joblib` (a `KNeighborsClassifier` over a 15-feature telemetry vector, from `knn_adapter.py`) to estimate breach risk, then scores facilities by risk + distance
- 16 storage nodes across Gujarat, Mumbai, Nashik, Indore, Jaipur, Delhi, Vellore, Bangalore, Chennai

**Composite breach probability** fuses forecast headroom + anomaly score into a single 0–100 risk index per truck.

### Model Performance
Metrics are computed on held-out simulated traces (split by trace) and compared against a "nothing changes" persistence baseline. They are printed at training time and stored in the model artifact:
```
r2_score · mae_celsius · rmse_celsius · skill_vs_persistence
```

---

## Fleet Coverage

**Regional — Gujarat Corridor**
```
Vadodara  →  Ahmedabad · Anand · Sanand · Gandhinagar
Nadiad    →  Gandhinagar · Ahmedabad
Anand     →  Ahmedabad · Gandhinagar
```

**Long-Haul — National**
```
Mumbai    →  Delhi · Jaipur
Chennai   →  Bangalore
Ahmedabad →  Chennai
```

---

## Cold Storage Network

16 mapped facilities including:
- GAIMFP PPC Cold Store, Vadodara
- Sanand Pharma Cold Chain
- Kheda Vaccine Vault
- Ahmedabad MedCold Depot
- Gujarat Cold Storage Association, Gandhinagar
- Hubs in Mumbai, Nashik, Indore, Jaipur, Delhi, Vellore, Bangalore, Chennai

---

## Project Structure

```
Frostgaurd-AI-Final-Repo-Team-Red-Dragon/
├── main_dashboard.py          # Streamlit entry point — run this
├── frost_ml.py                # Core ML engine (simulator, training, inference)
├── config.py                  # Thresholds, COLD_STORAGES (single source of truth), paths
├── frostguard_ml.joblib       # Pre-trained forecaster + detector (loaded at boot)
├── routes_cache.json          # Precomputed OSRM road routes
├── frostguard_knn.joblib      # Pre-trained KNN breach-risk classifier (used by Bridge.py)
├── knn_adapter.py             # KNN adapter + synthetic training data
├── train_model.py             # Retrain frostguard_ml.joblib
├── train_knn.py               # Retrain frostguard_knn.joblib
├── precompute_routes.py       # Regenerate routes_cache.json (needs internet)
├── Bridge.py / api.py         # Optional standalone REST backends
├── trip_replay.py             # Replay dataset telemetry to a backend
├── index.html                 # Static landing page for search engines (host separately)
├── Dockerfile                 # python:3.12-slim, honours $PORT
├── render.yaml                # Render deployment config
└── requirements.txt
```

Generated at runtime / not committed: `fleet_logs.csv`, `logs/`, and the optional `data/healthcare_iot_target_dataset.csv` and `config/frostguard_config.json`.

### Retraining artifacts

```bash
python train_model.py        # rewrites frostguard_ml.joblib
python train_knn.py          # rewrites frostguard_knn.joblib
python precompute_routes.py  # rewrites routes_cache.json (needs internet)
```

`scikit-learn` is pinned (`==1.8.0`) because each artifact records the version it was trained with and is rejected if it doesn't match. If you change the pin, rerun the training scripts and commit the new artifacts.

## Deployment

The `Dockerfile` binds to `$PORT` (set by Render), falling back to 8501 locally. `render.yaml` configures the Render service and its `/_stcore/health` health check.

---

## Limitations & Future Improvements

While FrostGuard AI demonstrates a robust cold-chain monitoring system, there are areas for further enhancement:

**Current Limitations:**
- Relies on simulated telemetry instead of real IoT hardware integration
- Network latency and packet loss handling can be improved for rural deployments
- ML models are trained on a synthetic thermal simulator, not real sensor data, and need real-world validation
- Static cold storage nodes — dynamic availability is not yet considered

**Future Improvements:**
- Integration with real IoT sensors for live deployment
- Advanced deep learning models for improved prediction accuracy
- Dynamic cold storage discovery based on real-time availability
- Mobile app for drivers with real-time alerts and instructions
- Offline-first capabilities for low-connectivity regions

---

## Environment Variables

All optional. The app runs fully offline without any of these.

| Variable | Purpose |
|---|---|
| `SUPABASE_URL` | Supabase project URL for cloud telemetry sync |
| `SUPABASE_SERVICE_ROLE_KEY` (or `SUPABASE_KEY`) | Supabase key — used by `Bridge.py` only |
| `DISCORD_WEBHOOK` | Discord webhook URL for CRITICAL alerts — used by `Bridge.py` only |
| `DATASET_PATH` | Override path to the healthcare IoT CSV |
| `FLEET_CSV` | Override path for fleet log output |

---

## Verification

```bash
# Compile check — all modules
python -m py_compile main_dashboard.py Bridge.py api.py frost_ml.py knn_adapter.py config.py trip_replay.py train_model.py train_knn.py

# Bridge smoke test — expected output: 13 TRK-RD-001
python -c "import Bridge; fleet=Bridge._simulate_fleet(); print(len(fleet), fleet[0]['truck_id'])"
```

---

*FrostGuard AI · IIIT Vadodara · 2025*  
*Built for real-world cold chain intelligence across India's healthcare logistics network.*
