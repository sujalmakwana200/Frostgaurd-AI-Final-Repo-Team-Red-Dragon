#!/bin/sh
uvicorn api:app --host 127.0.0.1 --port 5000 &
until python -c "import urllib.request as u; u.urlopen('http://127.0.0.1:5000/health')" 2>/dev/null; do sleep 2; done
exec streamlit run main_dashboard.py --server.port ${PORT:-10000} --server.address 0.0.0.0
