# Lead Engine - single image serves API + workers (same contracts)
# Keep this runtime aligned with the development compose service and CI.
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY lead_engine/ lead_engine/
COPY api/ api/
COPY config/ config/
ENV PYTHONUNBUFFERED=1
# Non-root runtime: /app/data (default SQLite home) and /app/outputs stay
# writable; override with LEAD_ENGINE_DATA_DIR / LEAD_ENGINE_OUTPUTS_DIR.
RUN useradd --create-home --uid 10001 appuser \
    && mkdir -p /app/data /app/outputs \
    && chown -R appuser:appuser /app
USER appuser
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/ready', timeout=4).status == 200 else 1)"
# The API serves the checked-in frontend from lead_engine/static. Frontend
# compilation is intentionally handled by .github/workflows/sync-frontend.yml;
# this image does not claim to be a standalone frontend build.
# Default: API; workers override the command in k8s/workers.yaml.
CMD ["python", "-m", "lead_engine", "serve", "--host", "0.0.0.0", "--port", "8000"]