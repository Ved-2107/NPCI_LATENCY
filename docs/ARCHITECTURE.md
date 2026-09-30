# Architecture

```
Dashboard (ui/index.html)
      |  REST
FastAPI hub  -- risk.py (explainable AI score) -- fx.py (simulated rates) -- upi.py (simulated NPCI payout)
      |  peer CLI / gateway (org-scoped identity)
Drunix network:  Org1MSP Remitting bank (Citi)  <->  Org2MSP Payout rail (NPCI)
      chaincode `remit` (Go): state machine, pricing, policy, idempotency
```
Design rules: money-relevant math is integer-only and deterministic; time comes from the transaction timestamp; the hub can propose but the chaincode decides; Go and Python pricing are locked together by `testvectors/quote_vectors.json`.
