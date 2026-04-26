# FrostGuard AI 🧊
### Cold Chain Command Center — Real-Time Healthcare Logistics Intelligence

> A production-grade fleet monitoring system for cold-chain medical cargo, built for Gujarat's pharmaceutical and blood-bank logistics corridors.

[![Live Demo](https://img.shields.io/badge/Live_Demo-FrostGuard_AI-FF4B4B?style=for-the-badge&logo=streamlit&logoColor=white)](https://frostgaurd-ai-final-repo-team-red-dragon-hfjhbqjcrmwtpaagvyql4.streamlit.app/)

---

## Tech Stack

![Python](https://img.shields.io/badge/Python-3.11-3776AB?style=for-the-badge&logo=python&logoColor=white)
![Streamlit](https://img.shields.io/badge/Streamlit-1.35+-FF4B4B?style=for-the-badge&logo=streamlit&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.111-009688?style=for-the-badge&logo=fastapi&logoColor=white)
![Flask](https://img.shields.io/badge/Flask-3.0-000000?style=for-the-badge&logo=flask&logoColor=white)
![scikit-learn](https://img.shields.io/badge/scikit--learn-1.5-F7931E?style=for-the-badge&logo=scikit-learn&logoColor=white)
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

FrostGuard AI is a live Streamlit dashboard that monitors a fleet of 13 medical cargo trucks in real time. It doesn't just show you what's happening — it tells you what's *about to* happen and automatically reroutes trucks to the nearest safe cold storage before a breach occurs.

| Capability | How |
|---|---|
| Live temperature monitoring | IoT telemetry ingested via REST API every 6 seconds |
| Breach prediction | HistGradientBoosting model forecasts next 30s temperature trajectory |
| Anomaly detection | Isolation Forest flags irregular thermal behavior |
| Smart rerouting | KNN model routes truck to nearest of 16 cold storage nodes |
| Voice alerts | Browser-native alert, fires once per breach episode |
| Fleet overview | 13 trucks across Gujarat + national long-haul routes |

---

## Demo

```bash
git clone <repo-url>
cd frostgaurd_final_v2
python -m venv .venv && .venv\Scripts\activate   # Windows
pip install -r requirements.txt
streamlit run main_dashboard.py
```

Open `http://localhost:8501` — the bridge starts automatically, no extra steps.

**Demo flow:**
1. Use the truck selector to browse all 13 active trucks
2. Scroll below the map to view live fleet detail cards
3. Hit **Inject Failure** on any truck to simulate a breach event
4. Watch the KNN reroute kick in and the voice alert fire
5. Check the Event Log panel for a timestamped breach history

---

## System Architecture

```
streamlit run main_dashboard.py
        │
        ├── Auto-starts Bridge (Flask) if offline
        ├── Polls /fleet and /latest every 6s via Streamlit fragments
        └── Renders: map · metrics · alerts · fleet cards · event log
                │
                ▼
        Bridge.py + api.py  (Flask + FastAPI dual-layer)
                │
                ├── POST /telemetry   — ingest truck sensor data
                ├── GET  /fleet       — return simulated fleet state
                ├── GET  /latest      — last known telemetry record
                ├── GET  /ml_insight  — anomaly + forecast output
                └── POST /command     — send reroute / cooling commands
                        │
                        ▼
        frost_ml.py  ·  knn_adapter.py  ·  model artifacts
                        │
                        ▼
        Local CSV log  +  Optional Supabase cloud sync
```

---

## ML Pipeline

The ML engine (`frost_ml.py`) runs two models in tandem on a **32-feature telemetry vector**.

**Features include:** live temperature, rolling stats (mean, std, lags 1–6), humidity, door open count, acceleration RMS, handling stress, health index, ambient weather, speed, and GPS-derived distance step.

### Models

**1. Isolation Forest — Anomaly Detector**
- Detects abnormal thermal patterns (e.g. sudden spike, sensor drift, door left open)
- Trained on the healthcare IoT dataset (up to 80,000 rows)
- Outputs: `anomaly: bool`, `anomaly_score: 0–100`

**2. HistGradientBoostingRegressor — Temperature Forecaster**
- Predicts next-step temperature in an autoregressive loop (10 steps × 3s = 30s horizon)
- Falls back to Ridge regression if GBM training fails
- Outputs: `predicted_temp_30s`, `forecast_series`, `time_to_critical_sec`

**3. KNN — Facility Router (`frostguard_knn.joblib`)**
- Maps truck GPS coordinates to nearest viable cold storage node
- 16 storage nodes across Gujarat, Mumbai, Delhi, Chennai, Bangalore

**Composite breach probability** fuses forecast headroom + anomaly score into a single 0–100 risk index per truck.

### Model Performance
Metrics are logged live at runtime and accessible via the `/health` endpoint:
```
r2_score · mae_celsius · mse · rmse_celsius
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
frostgaurd_final_v2/
├── main_dashboard.py          # Streamlit entry point — run this
├── Bridge.py                  # Flask bridge — auto-started by dashboard
├── api.py                     # FastAPI async backend (v2)
├── frost_ml.py                # Core ML engine
├── knn_adapter.py             # KNN model compatibility shim
├── config.py                  # Temperature thresholds + route config
├── requirements.txt
├── README.md
├── frostguard_knn.joblib      # Trained KNN routing artifact
├── frostguard_ml.joblib       # Trained ML pipeline artifact
├── frostguard_ml.pkl          # Pickle fallback
├── config/
│   └── frostguard_config.json # 13-truck fleet definitions
├── data/
│   └── healthcare_iot_target_dataset.csv
└── logs/
    ├── bridge_stdout.log
    └── bridge_stderr.log
```

---

## Limitations & Future Improvements

While FrostGuard AI demonstrates a robust cold-chain monitoring system, there are areas for further enhancement:

**Current Limitations:**
- Relies on simulated telemetry instead of real IoT hardware integration
- Network latency and packet loss handling can be improved for rural deployments
- ML models are trained on limited datasets and may require further real-world validation
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
| `SUPABASE_SERVICE_ROLE_KEY` | Supabase service role key |
| `DATASET_PATH` | Override path to the healthcare IoT CSV |
| `FLEET_CSV` | Override path for fleet log output |

---

## Verification

```bash
# Compile check — all modules
python -m py_compile main_dashboard.py Bridge.py frost_ml.py knn_adapter.py config.py

# Bridge smoke test — expected output: 13 TRK-RD-001
python -c "import Bridge; fleet=Bridge._simulate_fleet(); print(len(fleet), fleet[0]['truck_id'])"
```

---

*FrostGuard AI · IIIT Vadodara · 2025*  
*Built for real-world cold chain intelligence across India's healthcare logistics network.*
