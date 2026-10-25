# ZEQARIS NEXUS — Reasoning Architecture

Cryptographically verifiable agent coordination with governed Zetaris evidence, Meterless H-MEM memory, ICP checkpoint verification and policy-gated Base settlement.

This Open Agent Hackathon 2026 release targets **Reasoning Architecture**. It combines the live-verified VELQIRIS Market Truth workflow with the ZEQARIS evidence and settlement architecture.

## What it proves

Autonomous agents can produce useful explanations while still relying on corrupted or stale data. ZEQARIS separates authority across deterministic and cryptographic boundaries:

1. **Zetaris** executes the governed SQL scenario.
2. Deterministic median/MAD code decides which venues belong to consensus.
3. **Meterless H-MEM** stores the observation and finding with inspectable retrieval and an append-only ledger.
4. ZEQARIS canonicalizes the event, verifies the actor signature and checks hash-chain continuity in an ICP canister.
5. A Base escrow accepts only threshold-authorized settlement vouchers and enforces cumulative Merkle claims.

The model may explain evidence. It cannot rewrite consensus, certify its own event or release funds.

## Live sponsor evidence

- Zetaris official local bundle 2.4.3 verifier: **9/9**.
- Live Zetaris connectivity query: one row in an observed **1.679 seconds**.
- Live two-relation SQL JOIN: four expected rows in an observed **8.395 seconds**.
- Both relations are declared synthetic inputs. The timing values are single-run observations, not benchmarks.
- Official Meterless H-MEM conformance: **13/13**.
- Official H-MEM runtime stored and retrieved two memories and wrote four append-only ledger events.

See `evidence/zetaris-platform-verification.json`, `evidence/zetaris-live-receipt.json`, `evidence/meterless-hmem-conformance.json` and `evidence/meterless-hmem-live-receipt.json`.

## ZEQARIS verification evidence

- Python evidence gates: **10/10**.
- Cross-runtime golden vectors: **40/40**.
- Rust canister tests: **9/9**, with formatting and clippy checks passing.
- Solidity unit tests: **9/9**.
- Foundry invariant campaign: **500 runs, 128,000 calls, zero reverts**.
- Slither: five contracts, 102 detectors, no critical exploit finding.

The ICP and Base modules are locally verified release candidates. This repository does not represent them as production deployments and includes no fabricated transaction hash or canister ID.

## Adversarial demo

The tamper harness changes one payload byte after actor signing. The recomputed event hash no longer recovers the registered actor, so the checkpoint returns `ERR_ACTOR_SIGNATURE_MISMATCH`. The evidence ladder stops at `ORDERED`, PC5 stays locked, the settlement nonce remains unchanged and zero USDC leaves escrow.

## Reproduce

```bash
# Live-integrated agent regression suite
python3 tests/run_all_tests.py

# ZEQARIS Python and golden vectors
cd zeqaris_nexus
python3 tests/run_all_tests.py
python3 vectors/verify_golden_vectors.py

# ICP canister
cd canister
cargo test --locked --offline
cargo fmt --check
cargo clippy --locked --offline --all-targets -- -D warnings

# Base escrow
cd ../contracts
forge test --match-path 'test/unit/*.sol' -vv
FOUNDRY_PROFILE=ci forge test --match-contract EscrowInvariantTest -vv
```

## Repository map

```text
├── agent/                 Zetaris and Meterless H-MEM reasoning workflow
├── evidence/              Redaction-safe sponsor receipts
├── vendor/                Official Meterless reference and conformance harness
├── tests/                 30 agent regression tests
├── zeqaris_nexus/
│   ├── canister/          ICP checkpoint and threshold-ECDSA authorization
│   ├── contracts/         Base escrow, unit tests and invariant harness
│   ├── core/              Canonical hashes and evidence ladder
│   └── vectors/           Cross-runtime golden vectors
└── artifacts/             Demo video, deck and audit viewer
```

## Claim boundaries

- SHA-256 values are integrity digests, not digital signatures.
- The live Zetaris relations are synthetic SQL inputs, not production exchange feeds.
- The agent's external model adapter is optional and is not used as evidence for the verified sponsor workflow.
- The 5% royalty and Base settlement rail are demonstrated and invariant-tested locally, not claimed as mainnet deployment.
- Pre-existing and build-window work remain disclosed in `PREEXISTING_TECHNOLOGY.md`.

## License

Project code: Apache License 2.0. Vendored Meterless H-MEM files retain their upstream Apache-2.0 provenance.

