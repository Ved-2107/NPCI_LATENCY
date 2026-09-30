# RemitChain — cross-border remittance to India on Drunix

Drunix Hackathon x Citi · Problem Statement 3: Cross-Border Remittances (also touches Financial Inclusion).

**Problem.** Sending money to India still costs about 6% all-in on average, is opaque (the receive amount is unclear until after payment), takes hours to days, and fails without clear ownership of the refund.

**Idea.** Put the remittance *lifecycle* on a permissioned Drunix ledger shared by the remitting bank and the NPCI payout rail. Each organisation can only sign the steps it owns. The full price (FX rate, spread, fees, exact rupees received) is fixed on-chain before funding. Payout is idempotent and can never be double-paid. Failures and expiries refund automatically by rule, not by phone call.

## What runs on Drunix (chaincode, Go)
`chaincode/remit` implements a state machine with org-level access control:

```
CREATED -> QUOTED -> SCREENED -> VERIFIED -> FUNDED -> PAYOUT_SUBMITTED -> SETTLED
              \-> BLOCKED / HELD (manual review)   \-> BENEFICIARY_REJECTED   \-> EXPIRED   \-> FAILED
                                   any failure state -> REFUNDED
```

| Step | Signed by | Enforced on-chain |
|---|---|---|
| CreateRemittance | Remitting bank (Org1MSP) | purpose allow-list, no duplicates, only salted hashes stored (no PII) |
| LockQuote | Remitting bank | deterministic integer pricing: fee, spread, exact paise received, all-in cost in bps, expiry from tx timestamp |
| RecordScreening | Remitting bank | risk >= 85 or sanctions hit blocks; >= 60 or daily cap breach holds |
| ReviewHold | Remitting bank | maker-checker for held transfers |
| VerifyBeneficiary | Payout rail (Org2MSP) | name-match score >= 70 required |
| ConfirmFunding | Remitting bank | quote must be unexpired; per-beneficiary daily cap |
| SubmitPayout / SettlePayout / FailPayout | Payout rail | idempotent, payoutRef can never be reused |
| Refund | Remitting bank | only from FAILED, EXPIRED, BLOCKED, BENEFICIARY_REJECTED |

Off-chain (supporting components, allowed by FAQ 10): FastAPI hub, explainable AI risk scoring, simulated FX and UPI adapters, dashboard.
The AI scores risk but **cannot override policy**: thresholds live in chaincode.

## Layout
```
chaincode/remit/   Go chaincode (remit.go, pricing.go, tests)
hub/               FastAPI hub: orchestrator, risk, FX + UPI simulators, ledger clients
ui/index.html      Dashboard (served by the hub)
testvectors/       Pricing vectors shared by Go and Python tests
scripts/           run-demo.sh, deploy-cc.sh
docs/              Architecture, pitch flow, Q&A prep
```

## Run the demo (no network needed)
```bash
./scripts/run-demo.sh        # http://localhost:8000
cd hub && pytest -q          # 10 tests
```
Demo mode uses `MemoryLedger`, a Python port of the chaincode rules. The dashboard labels this clearly.

## Run on a real Drunix network
1. `git clone https://github.com/npci/drunix.git drunix` (git-ignored) and follow its network README (Docker required).
2. `cd chaincode/remit && go mod tidy && go test ./...`
3. `./scripts/deploy-cc.sh`, create `org1.env` / `org2.env` (see `hub/env.example`), then `LEDGER_MODE=drunix uvicorn app.main:app --port 8000` from `hub/`.

## Honest scope notes
- FX rates and the UPI/NPCI adapter are simulated; swap adapters when sandbox access is granted.
- Pricing supports 2-decimal currencies only. Purpose categories should be mapped to RBI purpose codes.
- Compliance thresholds are demo policy, not regulatory advice.
- The Go chaincode was written against `fabric-contract-api-go` and has not yet been run on a live Drunix network; `go test` and network smoke tests are the first thing to run.
