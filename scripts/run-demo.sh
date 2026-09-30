#!/usr/bin/env bash
# Runs the hub + dashboard in demo mode (no Drunix network needed).
set -euo pipefail
cd "$(dirname "$0")/../hub"
[ -d .venv ] || python3 -m venv .venv
. .venv/bin/activate
pip install -q -r requirements.txt
LEDGER_MODE=${LEDGER_MODE:-memory} uvicorn app.main:app --reload --port 8000
