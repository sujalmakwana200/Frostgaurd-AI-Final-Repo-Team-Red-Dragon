#!/bin/sh
uvicorn api:app --host 127.0.0.1 --port 5000 &
sleep 3
exec streamlit run main_dashboard.py --server.port ${PORT:-10000} --server.address 0.0.0.0
