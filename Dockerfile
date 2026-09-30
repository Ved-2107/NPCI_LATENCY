FROM python:3.12-slim

WORKDIR /app

# Install dependencies
COPY hub/requirements.txt hub/requirements.txt
RUN pip install --no-cache-dir -r hub/requirements.txt

# Copy application code
COPY hub/app hub/app
COPY hub/tests hub/tests
COPY ui ui
COPY testvectors testvectors

WORKDIR /app/hub

ENV LEDGER_MODE=memory
ENV PYTHONPATH=/app/hub
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health')" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
