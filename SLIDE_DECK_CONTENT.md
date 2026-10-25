# Final slide-deck content

## Slide 1 — VELQIRIS

The Agent That Can Explain Why. Evidence-first market consensus for execution reviewers.

## Slide 2 — The problem

Multi-source decisions become difficult to audit when the query, filter, memory context and final rationale are disconnected.

## Slide 3 — Verified workflow

Zetaris live SQL -> MAD consensus -> official Meterless H-MEM -> hybrid retrieval trace -> persistent ledger -> redaction-safe receipts.

## Slide 4 — Zetaris evidence

- Official bundle 2.4.3.
- 9/9 verifier checks.
- `SELECT 7` returned one row.
- `market_ticks` joined with `venue_telemetry`; four declared synthetic scenario rows returned live.
- No independent-source federation, production-feed, or latency-performance claim.

## Slide 5 — Meterless evidence

- Official H-MEM reference, upstream commit disclosed.
- Two memories stored and retrieved.
- Four append-only ledger events persisted.
- Official conformance suite: 13/13.

## Slide 6 — VELQIRIS result

- Consensus VWAP: 67,450.6642.
- Verified spread: 0.09 bps.
- Included: BINANCE, COINBASE, OKX.
- Rejected: ANOMALY_DEX by MAD ceiling.

## Slide 7 — Release evidence

- Python tests: 30/30.
- Standalone Audit Viewer: `artifacts/index.html`.
- Public event-specific repository.
- MP4 demo and PPTX deck included.
- SHA-256 means integrity digest, not digital signature.
- Full pre-existing-code disclosure.
