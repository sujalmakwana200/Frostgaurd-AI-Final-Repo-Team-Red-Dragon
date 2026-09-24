FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
EXPOSE 8501
# Render (and most PaaS hosts) assign the port dynamically via $PORT —
# hardcoding 8501 means Render's health check never finds the app and the
# deploy hangs indefinitely. Shell form (not exec-array form) is required
# here so $PORT actually gets substituted at container start.
CMD streamlit run main_dashboard.py --server.port=${PORT:-8501} --server.address=0.0.0.0 --server.headless=true
