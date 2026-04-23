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
        "knn_artifact": "knn_adapter.pkl",
        "window_size": 120,
        "training_sample_rows": 80000,
        "forecast_steps": 10,
        "seconds_per_step": 3
    },
    "bridge": {
        "csv_file": "fleet_logs.csv"
    }
}
