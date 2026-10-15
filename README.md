# RemitChain: Institutional Cross-Border Remittance Network

[![CI](https://github.com/Ved-2107/NPCI_LATENCY/actions/workflows/ci.yml/badge.svg)](https://github.com/Ved-2107/NPCI_LATENCY/actions/workflows/ci.yml)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-009688.svg?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Python](https://img.shields.io/badge/Python-3.12-blue.svg?logo=python&logoColor=white)](https://python.org)
[![Go](https://img.shields.io/badge/Go-1.22+-00ADD8.svg?logo=go&logoColor=white)](https://golang.org)
[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)

RemitChain is an institutional-grade, multi-organization cross-border remittance orchestrator connecting global remitting banks (**Citi / Org1MSP**) directly to domestic instant payout rails (**NPCI UPI / Org2MSP**) via a distributed state machine and high-performance API hub.

---

## Key Features

- **Sub-Second Atomic Settlement**: Real-time cross-border settlement in **< 850 ms**—over **200,000x faster than legacy SWIFT GPI**.
- **Transparent Integer-Only Pricing**: Deterministic 64-bit integer money math with 100% byte-for-byte parity between Go chaincode and Python orchestrator across 2, 0, and 3-decimal currencies (USD, AED, JPY, KRW, BHD, KWD, EUR, GBP).
- **Dual-Org Distributed Ledger**: Endorsement policy ensures mutual attestation; remitting bank cannot settle without payout rail confirmation.
- **Privacy by Construction (GDPR Art. 17)**: Zero plaintext PII on-chain. Off-ledger encrypted vault with cryptographic shredding (`DELETE /api/pii/{rid}`).
- **Real-Time Telemetry & Swim-Lane**: Live WebSocket event feed animating state handoffs between Citi and NPCI with p50/p90/p95/p99 latency tracking.
- **Maker-Checker Compliance Desk**: Automated AML and risk scoring with strict Maker != Checker policy enforcement and 15-minute SLA breach timers.
- **Cryptographic Audit Hash Chain**: Every transition is linked in a SHA-256 hash chain (`/api/remittances/{rid}/verify`) ensuring verifiable immutability and anti-tampering.
- **Async 202 Background Worker**: Support for high-concurrency non-blocking job execution via HTTP 202 Accepted.
- **Prometheus Metrics**: Native `/metrics` endpoint for Prometheus/Grafana monitoring.

---

## System Architecture

```
Institutional Portal (ui/index.html & ui/app.js)
            │  REST / WebSockets
            ▼
FastAPI Hub Gateway (hub/app/)
    ├── Auth & RBAC (auth.py: JWT Bearer & Role Guards)
    ├── Integer Pricing Engine (pricing.py: Quote Vectors Parity)
    ├── AI AML & Risk Engine (risk.py: USD Normalization & Waterfall)
    ├── Off-Ledger Encrypted PII Vault (pii_vault.py: GDPR Art. 17 Shredding)
    ├── Async 202 Worker (jobs.py: Background Threadpool Executor)
    ├── Cryptographic Verifier (verifier.py: SHA-256 Hash Chain)
    └── Prometheus Exporter (metrics.py: /metrics Exposition)
            │  State Machine Proposals & Attestation
            ▼
Distributed Ledger Layer (chaincode/remit/ & hub/app/ledger.py)
    ├── Org1MSP: Remitter Bank (Citi) -> Initiate, Lock Quote, Screen, Fund Lock
    └── Org2MSP: Payout Rail (NPCI)  -> Verify VPA, UPILink Push, Immediate Settlement
```

---

## API Reference

### 1. Quotes & Pricing
- `POST /api/quotes`: Generate a guaranteed binding quote (60s lock window).
- `GET /api/quote?corridor=US-IN&amountMinor=100000`: Preview pricing for a corridor and amount.
- `GET /api/compare?corridor=US-IN&amountMinor=100000`: Compare RemitChain fees vs Western Union, Wise, and Bank Wire.

### 2. Remittance Lifecycle
- `POST /api/remittances`: Initiate a new remittance (Supports `Idempotency-Key` header).
- `POST /api/remittances/{rid}/step`: Execute next state machine transition.
- `POST /api/remittances/{rid}/run`: Sequentially execute all steps to settlement (synchronous).
- `POST /api/remittances/{rid}/async-run`: Execute in background worker (**HTTP 202 Accepted**).
- `GET /api/jobs/{jobId}`: Poll status of an asynchronous background job.
- `GET /api/remittances`: Paginated list of all remittances (`?offset=0&limit=50`).
- `GET /api/remittances/{rid}`: Fetch remittance record and audit trail.
- `GET /api/remittances/{rid}/verify`: **Cryptographically verify SHA-256 hash chain** of the trail.

### 3. Verification & Compliance
- `POST /api/upi/lookup`: Pre-send beneficiary UPI VPA verification and name matching.
- `GET /api/compliance/pending`: List all HELD remittances with elapsed SLA timers and risk waterfall.
- `POST /api/remittances/{rid}/review`: Maker-Checker compliance review (`X-Reviewer-Id != creatorId`).
- `GET /api/remittances/{rid}/risk`: Detailed feature contributions for risk scoring.
- `GET /api/audit`: Query historical audit trail with filters.
- `GET /api/audit/export`: Download complete regulatory audit trail as CSV.

### 4. Security & Off-Ledger PII
- `POST /api/auth/token`: Issue signed RFC 7519 JWT access token with role claims (`sender`, `compliance_officer`, `auditor`, `admin`).
- `GET /api/auth/me`: Current authenticated user identity.
- `GET /api/pii/{rid}`: Retrieve decrypted off-ledger PII (Protected).
- `DELETE /api/pii/{rid}`: **GDPR Right-to-be-Forgotten cryptographic shredding** (Returns 410 Gone on future retrieval).

### 5. Telemetry & Monitoring
- `GET /api/latency`: Detailed P50/P90/P95/P99 latency breakdown and comparison vs SWIFT.
- `GET /metrics`: Standard Prometheus metrics exposition.
- `WS /ws/events`: Live WebSocket event stream.

---

## Getting Started

### Local Setup (Python 3.12+)

```bash
# Clone the repository
git clone https://github.com/Ved-2107/NPCI_LATENCY.git
cd NPCI_LATENCY

# Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install runtime and development dependencies
pip install -r hub/requirements.txt
pip install -r hub/requirements-dev.txt

# Start the Hub server
cd hub
uvicorn app.main:app --reload --port 8000
```
Open your browser at: **http://localhost:8000**

### Running with Docker

```bash
# Build the container image
docker build -t remitchain-hub:latest .

# Run container
docker run -p 8000:8000 remitchain-hub:latest
```

---

## Running Automated Tests

```bash
# Run complete Python test suite with coverage
PYTHONPATH=hub pytest hub/tests/ -v

# Run Go chaincode pricing and state machine tests
cd chaincode/remit
go test -v ./...
```

---

## Running Load Tests (Locust)

```bash
pip install locust
locust -f benchmarks/locustfile.py --headless -u 50 -r 10 --run-time 60s --host http://localhost:8000
```

---

## License
Apache License 2.0. Built for institutional cross-border settlement research.
