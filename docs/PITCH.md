# Demo flow (Problem -> User Journey -> Solution -> Architecture -> Drunix Flow -> Prototype -> Impact)

1. **Problem (30s).** Remittances to India cost around 6% all-in, the receive amount is unclear, and failed transfers are slow to refund.
2. **User journey (30s).** Asha in Dubai sends AED 2,500 to Meera's UPI address. She sees the exact rupees received and total cost before paying.
3. **Solution (30s).** One shared ledger between the remitting bank and NPCI; each side signs only its own steps.
4. **Architecture (45s).** Dashboard -> FastAPI hub (risk AI, FX, UPI adapter) -> Go chaincode on Drunix (2 orgs). PII stays off-ledger.
5. **Drunix flow (60s).** Show the swim-lane: CREATE, LOCK_QUOTE, SCREEN (bank) then VERIFY_BENEFICIARY (rail), FUND, SUBMIT_PAYOUT, SETTLE. Point at tx ids.
6. **Prototype (2 min).** Run four scenarios: normal settle; high-risk hold then approve; payout failure then refund; quote expiry.
7. **Impact (30s).** All-in cost of roughly 0.4% to 2.4% in the demo vs a 6.5% typical benchmark; zero double-payouts by construction; refunds by rule.

## Likely jury questions (FAQ 15)
- **Why Drunix, not a database?** Two institutions must share one state machine where neither can rewrite the other's steps; endorsement and MSP checks enforce it.
- **Where is PII?** Off-chain in the hub; the ledger holds salted hashes.
- **Security?** Org-scoped writes, deterministic on-chain policy, idempotent payouts, payoutRef uniqueness, maker-checker holds.
- **Scale?** Stateless hub, per-transfer keys avoid MVCC hot spots except the daily beneficiary counter (shard by hour if needed).
- **Integration?** Adapters for FX and UPI are interfaces; replace simulators with sandbox APIs.
- **Impact metrics?** All-in cost (bps), time to settle, refund rate, hold rate, all shown live in the dashboard.
