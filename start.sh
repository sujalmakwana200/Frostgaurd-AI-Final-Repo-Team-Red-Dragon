#!/bin/sh
exec streamlit run main_dashboard.py \
  --server.port ${PORT:-10000} \
  --server.address 0.0.0.0 \
  --server.headless true \
  --server.enableCORS false \
  --server.enableXsrfProtection false
