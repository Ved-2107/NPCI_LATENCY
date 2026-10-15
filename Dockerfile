FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    LEDGER_MODE=memory \
    PYTHONPATH=/app/hub

WORKDIR /app

# Create non-root user and group
RUN groupadd -r app && useradd -r -g app -d /app -s /sbin/nologin app

# Install dependencies
COPY hub/requirements.txt hub/requirements.txt
RUN pip install --no-cache-dir -r hub/requirements.txt

# Copy application code and assets
COPY hub/app hub/app
COPY ui ui
COPY testvectors testvectors

# Set ownership to non-root user
RUN chown -R app:app /app

WORKDIR /app/hub
USER app
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health')" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
