# RemitChain Pitch & Executive Demo Script

## 1. Executive Summary & Pitch (3 Minutes)

### The Hook (30s): The Cross-Border Problem
Global remittances to India exceed $125 Billion annually, yet traditional correspondent banking (SWIFT) remains fundamentally broken:
- **Exorbitant Fees**: Average all-in cost of **6.50%** (hidden FX markups + flat intermediary wire fees).
- **Extreme Latency**: **48 to 72 hours** across 3–4 correspondent banking hops.
- **Opacity & Friction**: Beneficiaries never know the exact amount arriving until days later. Failures require weeks of manual investigations and clawbacks.

### The Solution (45s): Instant Atomic Settlement via Distributed Ledger
RemitChain replaces multi-hop correspondent chains with a shared, multi-organization distributed state machine connecting the remitting institution (**Citi / Org1MSP**) directly to the domestic payout rail (**NPCI / Org2MSP**):
- **Deterministic Integer Pricing**: 100% transparent fee lock, zero hidden margins, byte-for-byte parity between Go chaincode and Python orchestrator.
- **Dual-Org Attestation**: Neither party can overwrite or forge the other's state. Payouts occur directly into Indian bank accounts via instant UPI VPA rails.
- **Privacy by Construction**: Zero plaintext PII on-chain. Off-ledger encrypted PII vault with full GDPR Article 17 Right-to-be-Forgotten.

### The Live Prototype Walkthrough (90s)
1. **Send Flow**: Asha in New York locks a binding 60-second rate for $1,000 USD to Meera's UPI (`meera@okbank`).
2. **Pre-Send Verification**: Real-time UPI lookup validates account existence and beneficiary name match before money moves.
3. **Latency Lab & Swim-Lane**: Watch the transaction transition across Citi and NPCI in **< 850 ms**—over **200,000x faster than SWIFT GPI**.
4. **Compliance Desk**: High-risk transfers trigger instant Maker-Checker holds, enforcing strict separation of duties (creator cannot review own transfer) with SLA breach timers.
5. **Cost Comparison**: Instant transparency shows ₹5,000+ saved per transfer, projecting over ₹60,000 in annual savings for families.

### The Impact (15s)
- **Cost**: Slashed from **6.50%** to **0.40%** (saving billions for migrant workers).
- **Speed**: Slashed from **2 days** to **sub-second**.
- **Reliability**: Mathematical guarantee against double-payouts via immutable ledger proofs.

---

## 2. Institutional FAQ & Jury Defense

### Q1: Why use a distributed ledger instead of a centralized database?
**Answer**: Cross-border payments involve sovereign financial entities in different jurisdictions. A centralized database forces one bank to trust another bank's server. RemitChain's two-org model ensures:
- **Mutual Attestation**: Citi cannot mark a transfer "Settled"; only NPCI's payout rail can.
- **Non-Repudiation**: Every step is cryptographically signed with the organization's MSP credentials.
- **Tamper Evidence**: Built-in SHA-256 hash chains (`/api/remittances/{rid}/verify`) immediately detect any altered ledger entries.

### Q2: How is regulatory privacy (GDPR / DPDP) handled?
**Answer**:
1. **Salted Hash On-Chain**: The ledger stores only `senderHash` and `beneficiaryHash` using cryptographic salts.
2. **Encrypted Off-Ledger Vault**: Plaintext names and UPI addresses reside off-ledger, encrypted at rest.
3. **Right-to-be-Forgotten**: When a user exercises GDPR Article 17, `DELETE /api/pii/{rid}` permanently shreds the off-ledger ciphertext. The on-chain financial proof and transaction hashes remain valid without exposing personal identity.

### Q3: How are currency decimals handled for non-2-decimal currencies?
**Answer**:
RemitChain enforces integer-only arithmetic using normalized denominators:
$$\text{Denominator} = 10^{\text{decimals} + 4}$$
- 2 decimals (USD, EUR, GBP, AED, SGD, MYR): $\text{denom} = 10^6$
- 0 decimals (JPY, KRW): $\text{denom} = 10^4$
- 3 decimals (BHD, KWD): $\text{denom} = 10^7$
Tested and verified identical to the paise between Go and Python using `testvectors/quote_vectors.json`.

### Q4: How is Maker-Checker compliance enforced?
**Answer**:
Any remittance flagged for compliance hold (`HELD`) requires review by a dedicated compliance officer. RemitChain enforces that the `reviewerId` must strictly differ from the remittance `creatorId`, preventing unauthorized self-approval.
