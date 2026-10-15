# RemitChain Architecture & Technical Specification

RemitChain is an institutional-grade, multi-org cross-border payment orchestration network connecting global remitting banks (e.g., Citi / Org1MSP) with domestic instant payout rails (e.g., NPCI UPI / Org2MSP) via a distributed ledger state machine and high-throughput API gateway.

---

## 1. High-Level System Architecture

```mermaid
graph TD
    Client["Institutional Portal & REST/WS Clients"]
    
    subgraph Hub["RemitChain Gateway Hub (FastAPI)"]
        Router["API Router & Auth Guard (JWT/RBAC)"]
        PricingEngine["Deterministic Integer Pricing Engine"]
        RiskEngine["AI Risk & AML Screening Engine"]
        Vault["Encrypted Off-Ledger PII Vault (GDPR Art. 17)"]
        JobWorker["Async 202 Threadpool Worker"]
        Broadcaster["WebSocket Live Broadcaster"]
        Telemetry["Telemetry & Prometheus Exporter"]
    end

    subgraph LedgerBridge["Distributed Ledger Layer (Drunix / Fabric)"]
        Org1["Org1MSP: Remitter Bank (Citi)"]
        Org2["Org2MSP: Payout Rail (NPCI)"]
        Chaincode["remit.go: Deterministic Chaincode State Machine"]
    end

    subgraph DomesticRail["Domestic Payment Rails"]
        UPISwitch["NPCI UPILink Switch (Instant Payout)"]
    end

    Client -->|REST & WebSockets| Router
    Router --> PricingEngine
    Router --> RiskEngine
    Router --> Vault
    Router --> JobWorker
    Router --> Telemetry
    Router --> Broadcaster
    
    JobWorker --> LedgerBridge
    Router --> LedgerBridge
    Org1 <-->|P2P Consensus & Mutual Attestation| Org2
    Org2 -->|Payout Push| UPISwitch
```

---

## 2. Cryptographic Separation of Concerns

### The Zero-Plaintext Rule
To comply with global data privacy regulations (GDPR, India DPDP, CCPA), **plaintext Personally Identifiable Information (PII) is NEVER committed to the shared blockchain ledger**.

| Data Type | Storage Location | Encryption / Representation |
|-----------|------------------|-----------------------------|
| **Transaction State & Audit Trail** | On-Chain Ledger (`remit.go`) | Plaintext JSON state with salted SHA-256 hashes |
| **Sender & Beneficiary Identity** | On-Chain Ledger (`remit.go`) | Salted SHA-256 hashes (`senderHash`, `beneficiaryHash`) |
| **Plaintext PII (Names, VPAs, KYC)** | Off-Ledger Vault (`pii_vault.py`) | Authenticated symmetric keystream encryption at rest |
| **GDPR Right-to-be-Forgotten** | Off-Ledger Vault (`DELETE /api/pii/{rid}`) | Cryptographic key erasure & payload shredding |

When `DELETE /api/pii/{rid}` is executed, the off-ledger ciphertext is permanently purged. The immutable distributed ledger retains the cryptographic hashes and state proofs, ensuring regulatory auditability without retaining personal data.

---

## 3. End-to-End Remittance Sequence

```mermaid
sequenceDiagram
    autonumber
    actor Sender as Remitter
    participant Hub as RemitChain Hub
    participant Vault as Off-Ledger PII Vault
    participant Citi as Org1MSP (Citi)
    participant Bridge as Fabric / Drunix Ledger
    participant NPCI as Org2MSP (NPCI)
    actor Beneficiary as Recipient

    Sender->>Hub: POST /api/quotes (Lock Guaranteed Rate)
    Hub-->>Sender: 200 OK (Binding quoteId, 60s lock)
    
    Sender->>Hub: POST /api/remittances (Initiate Transfer)
    Hub->>Vault: Store Encrypted PII
    Hub->>Citi: Propose CreateRemittance
    Citi->>Bridge: Commit CREATED (Signed Org1MSP)
    
    Hub->>Citi: LockQuote
    Citi->>Bridge: Commit QUOTED
    
    Hub->>Citi: RecordScreening (AI AML Risk Score)
    Citi->>Bridge: Commit SCREENED (or HELD if risk >= 60)
    
    Hub->>NPCI: VerifyBeneficiary (UPI VPA Lookup)
    NPCI->>Bridge: Commit VERIFIED (Signed Org2MSP)
    
    Hub->>Citi: ConfirmFunding (Escrow Lock)
    Citi->>Bridge: Commit FUNDED (Signed Org1MSP)
    
    Hub->>NPCI: SubmitPayout (UPILink Switch)
    NPCI->>Bridge: Commit PAYOUT_SUBMITTED
    
    NPCI->>Beneficiary: Real-Time UPI Push Credit
    NPCI->>Bridge: Commit SETTLED (Signed Org2MSP)
    
    Bridge-->>Hub: Event Broadcast
    Hub-->>Sender: WebSocket state_change (SETTLED)
```

---

## 4. Integer-Only Pricing Math & Parity

To prevent floating-point non-determinism across platforms, operating systems, and architectures, all financial calculations are performed strictly using 64-bit integer arithmetic in minor currency units (cents, pence, paise).

### Formula
$$\text{FeeFlatMinor} = \text{FlatFee}$$
$$\text{FeeVariableMinor} = \lfloor \frac{\text{SendMinor} \times \text{FeeBps}}{10000} \rfloor$$
$$\text{NetMinor} = \text{SendMinor} - (\text{FeeFlatMinor} + \text{FeeVariableMinor})$$
$$\text{EffectiveRateMicro} = \text{MidRateMicro} \times \frac{10000 - \text{SpreadBps}}{10000}$$
$$\text{ReceivePaise} = \lfloor \frac{\text{NetMinor} \times \text{EffectiveRateMicro}}{10^{\text{decimals} + 4}} \rfloor$$

### Decimal Normalization Table
| Currency | Decimals | Denominator ($10^{\text{decimals} + 4}$) | Minor Unit |
|----------|----------|-----------------------------------------|------------|
| **USD, EUR, GBP, AED, SGD, MYR** | 2 | $10^6 = 1,000,000$ | Cents / Pence |
| **JPY, KRW** | 0 | $10^4 = 10,000$ | Yen / Won |
| **BHD, KWD** | 3 | $10^7 = 10,000,000$ | Fils |

*Go (`chaincode/remit/pricing.go`) and Python (`hub/app/pricing.py`) implementations are locked together by shared test vectors in `testvectors/quote_vectors.json`.*

---

## 5. Cryptographic Audit Trail Verification

Every state transition produces an immutable audit record on the ledger containing:
- `step`: Transition name (e.g., `SCREEN`, `VERIFY_BENEFICIARY`, `SETTLE_PAYOUT`)
- `status`: New state machine status
- `org`: Endorsing organization MSP ID
- `txId`: Ledger transaction identifier
- `ts`: Unix epoch seconds
- `tsMs`: High-resolution microsecond-level timestamp

The hash-chain is verified via:
$$H_0 = \text{SHA-256}(\text{"REMITCHAIN\_GENESIS"})$$
$$H_i = \text{SHA-256}(H_{i-1} \parallel \text{step} \parallel \text{status} \parallel \text{org} \parallel \text{txId} \parallel \text{ts})$$

Calling `GET /api/remittances/{rid}/verify` recomputes this hash chain across the ledger trail and confirms that no timestamps, steps, or transaction records have been altered.

---

## 6. Observability & Telemetry

- **Sub-Second Telemetry**: `GET /api/latency` reports P50, P90, P95, and P99 latencies alongside individual step durations.
- **Prometheus Metrics**: `GET /metrics` provides counter and gauge metrics for transfer throughput, active WebSockets, volume, and latency distributions.
- **WebSocket Feed**: `ws://<host>/ws/events` streams state transitions live to dashboards.
