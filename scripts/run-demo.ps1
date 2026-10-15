# Runs the hub + dashboard in demo mode on Windows (no Drunix network needed).
$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location "$ScriptDir\..\hub"

if (-not (Test-Path ".venv")) {
    python -m venv .venv
}

& ".\.venv\Scripts\Activate.ps1"
pip install -q -r requirements.txt
$env:LEDGER_MODE = if ($env:LEDGER_MODE) { $env:LEDGER_MODE } else { "memory" }
uvicorn app.main:app --reload --port 8000
