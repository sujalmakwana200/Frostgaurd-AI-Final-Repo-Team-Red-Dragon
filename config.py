import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def resolve_path(relative_path: str) -> str:
    """Resolve a path from CONFIG relative to this file's directory."""
    return os.path.join(BASE_DIR, relative_path)


# Single source of truth for the 16 cold-storage facilities. Previously this
# list was copy-pasted independently in main_dashboard.py and Bridge.py —
# both files now import it from here instead.
COLD_STORAGES = [
    {"name": "GAIMFP PPC Cold Store", "city": "Vadodara", "lat": 22.3100, "lon": 73.1650},
    {"name": "Amar Cold Storage", "city": "Anand", "lat": 22.5907, "lon": 72.9316},
    {"name": "Nadiad BioCold Hub", "city": "Nadiad", "lat": 22.6939, "lon": 72.8616},
    {"name": "Kheda Vaccine Vault", "city": "Kheda", "lat": 22.7500, "lon": 72.6800},
    {"name": "Sanand Pharma Cold Chain", "city": "Sanand", "lat": 22.9922, "lon": 72.3818},
    {"name": "Ahmedabad MedCold Depot", "city": "Ahmedabad", "lat": 23.0258, "lon": 72.5873},
    {"name": "Gujarat Cold Storage Association", "city": "Ahmedabad", "lat": 23.0613, "lon": 72.5857},
    {"name": "Vrundavan Cold Storage", "city": "Gandhinagar", "lat": 23.1500, "lon": 72.6800},
    {"name": "Mumbai Hub", "city": "Mumbai", "lat": 19.0760, "lon": 72.8777},
    {"name": "Nashik Storage", "city": "Nashik", "lat": 19.9975, "lon": 73.7898},
    {"name": "Indore Cold", "city": "Indore", "lat": 22.7196, "lon": 75.8577},
    {"name": "Jaipur Storage", "city": "Jaipur", "lat": 26.9124, "lon": 75.7873},
    {"name": "Delhi Hub", "city": "Delhi", "lat": 28.6139, "lon": 77.2090},
    {"name": "Chennai Hub", "city": "Chennai", "lat": 13.0827, "lon": 80.2707},
    {"name": "Vellore Storage", "city": "Vellore", "lat": 12.9165, "lon": 79.1325},
    {"name": "Bangalore Hub", "city": "Bangalore", "lat": 12.9716, "lon": 77.5946},
]


CONFIG = {
    "thresholds": {
        "safe_max_c": 6.5,
        "critical_at_c": 8.0,
        "temp_ceil_c": 12.0,
        "temp_floor_c": 2.0,
    },
    "truck": {
        "base_speed_kmh": 68.0,
    },
    "weather_defaults": {
        "ambient_temp_c": 31.0,
        "ambient_humidity_pct": 58.0,
        "weather_risk_index": 0.35,
    },
    "route": {
        "start": {"lat": 22.3072, "lon": 73.1812},
        "dest": {"lat": 23.0225, "lon": 72.5714},
    },
    "datasets": {
        "primary": "data/healthcare_iot_target_dataset.csv",
        "fallback": "healthcare_iot_target_dataset.csv"
    },
    "ml": {
        "model_artifact": "frostguard_ml.joblib",
        "pickle_artifact": "frostguard_ml.pkl",
        "knn_artifact": "frostguard_knn.joblib",
        "window_size": 120,
        "training_sample_rows": 80000,
        "forecast_steps": 10,
        "seconds_per_step": 3
    },
    "bridge": {
        "csv_file": "fleet_logs.csv"
    }
}
