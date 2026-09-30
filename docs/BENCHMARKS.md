# Performance Benchmarks

Results from load testing RemitChain Hub in demo mode (MemoryLedger, single process).

## Test Configuration
- **Tool:** Locust 2.x
- **Host:** localhost:8000 (uvicorn, single worker)
- **Duration:** 60 seconds
- **Users:** 50 concurrent, spawn rate 10/s

## Results

| Endpoint | Requests | Median (ms) | p95 (ms) | p99 (ms) | RPS |
|----------|----------|-------------|----------|----------|-----|
| POST /api/remittances | 312 | 12 | 28 | 45 | 5.2 |
| POST /api/remittances/{id}/run | 298 | 45 | 98 | 150 | 4.9 |
| GET /api/quote | 185 | 5 | 12 | 18 | 3.1 |
| GET /api/remittances | 180 | 8 | 22 | 35 | 3.0 |
| GET /api/stats | 95 | 6 | 15 | 22 | 1.6 |
| GET /api/compare | 92 | 7 | 16 | 25 | 1.5 |
| GET /api/health | 88 | 2 | 5 | 8 | 1.5 |
| **Total** | **1250** | **15** | **45** | **98** | **20.8** |

## Key Takeaways

1. **Throughput:** ~20 requests/second on a single process, ~5 end-to-end remittances/second.
2. **Latency:** Median 15ms, p95 45ms. The `/run` endpoint is slowest because it executes 6-8 sequential ledger operations.
3. **Scaling path:** The hub is stateless (except the in-memory ledger in demo mode). With a real Drunix network and multiple uvicorn workers behind a load balancer, horizontal scaling is straightforward.
4. **No errors** under sustained load in demo mode.

## Comparison: RemitChain vs Traditional SWIFT

| Metric | RemitChain (demo) | Traditional SWIFT |
|--------|-------------------|-------------------|
| End-to-end latency | < 1 second | 1-5 business days |
| All-in cost | 0.4% - 2.4% | 5% - 7% |
| Price transparency | Full, locked before payment | Unclear until settlement |
| Refund on failure | Automatic, by rule | Manual, days to weeks |
| Double-payout risk | Zero (idempotent by construction) | Non-zero |

> **Note:** Demo-mode benchmarks reflect in-process Python performance, not Drunix network consensus latency. On a real 2-org Drunix network, expect 2-3 seconds per endorsement round-trip.
