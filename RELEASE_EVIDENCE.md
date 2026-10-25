# Release evidence

Release date: 25 October 2026

## Verified results

- Zetaris official verifier: **9/9 PASS**.
- Zetaris live connectivity query: `SELECT 7 AS seven`, one returned row.
- Zetaris live scenario: `market_ticks` joined with `venue_telemetry` on `venue`; four declared synthetic rows executed by the live engine and four returned rows in **8.395 seconds** (single-run observation, not a benchmark).
- VELQIRIS result: consensus VWAP **67,450.6642**, post-filter spread **0.09 bps**, one MAD outlier rejected.
- Meterless H-MEM official reference: two memories stored and retrieved; four append-only ledger events persisted.
- Meterless official conformance suite: **13/13 PASS**.
- Python project suite: **30/30 PASS**.
- Standalone Audit Viewer: `artifacts/index.html`, generated from the Zetaris receipt and H-MEM ledger with an embedded offline snapshot.
- Credentials and session tokens: excluded from all repository evidence.
- Final PPTX SHA-256: `7ba5c77d4561fa495c3fbb5a849a4d9e21112d16045bf82a9688f0562510e314`.
- Final MP4 SHA-256: `58a83f4a11045e3bb760ce8b5f818e1ea3b419a72d76b35e49d3402661934755`.

## Primary evidence files

- `evidence/zetaris-platform-verification.json`
- `evidence/zetaris-live-receipt.json`
- `evidence/meterless-hmem-live-receipt.json`
- `evidence/meterless-hmem-conformance.json`
- `evidence/meterless-hmem-runtime/state.json`
- `evidence/meterless-hmem-runtime/ledger.jsonl`

## Claim boundaries

The live scenario proves Zetaris SQL execution of a JOIN across two declared logical relations and subsequent VELQIRIS processing. Both relations are deterministic synthetic inputs expressed directly in SQL; they are not independently onboarded external sources or production exchange feeds. Timings are client-side observations from one local run, not benchmarks. No external model was called. SHA-256 values are integrity digests, not digital signatures.
