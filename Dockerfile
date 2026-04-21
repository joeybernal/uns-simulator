# ── Build stage — public.ecr.aws bypasses Docker Hub sign-in requirement ─────
FROM public.ecr.aws/docker/library/python:3.12-slim AS builder

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ── Runtime stage ─────────────────────────────────────────────────────────────
FROM public.ecr.aws/docker/library/python:3.12-slim

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Copy application files
COPY simulator.py  .
COPY uns_model.py  .
# Note: static/ is not needed — UI is served from S3/CloudFront separately

# Non-root user for security
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8080

ENV PYTHONUNBUFFERED=1 \
    SERVER_PORT=8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=5 \
  CMD python3 -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/health')" || exit 1

CMD ["python3", "-m", "uvicorn", "simulator:app", "--host", "0.0.0.0", "--port", "8080", "--log-level", "warning"]
