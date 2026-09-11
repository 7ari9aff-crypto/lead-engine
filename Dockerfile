# Lead Engine — single image serves API + workers (same contracts)
FROM python:3.13-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY lead_engine/ lead_engine/
COPY api/ api/
COPY config/ config/
ENV PYTHONUNBUFFERED=1
# default: API; workers override the command in k8s/workers.yaml
CMD ["python", "-m", "lead_engine", "serve", "--host", "0.0.0.0", "--port", "8000"]
