# HackOS submission copy

## Track

Reasoning Architecture

## Description

ZEQARIS NEXUS is a verifiable reasoning and settlement architecture for autonomous agents. It combines VELQIRIS Market Truth with governed Zetaris execution, official Meterless H-MEM memory, ICP checkpoint verification and a policy-gated Base USDC escrow.

PROBLEM
An agent can produce a fluent explanation while relying on a stale or manipulated data source. If the same model also controls state transitions or funds, one hallucination can become an irreversible financial action.

ARCHITECTURE
Zetaris executes a live SQL JOIN across the declared `market_ticks` and `venue_telemetry` relations. Deterministic median/MAD code accepts the consensus venues and rejects the anomaly. The observation and finding enter the official Meterless H-MEM reference engine, which returns inspectable hybrid-ranking scores and persists an append-only ledger. ZEQARIS then canonicalizes the event, verifies its secp256k1 actor signature and hash-chain continuity in an ICP canister. The Base escrow accepts only threshold-authorized EIP-712 vouchers and enforces cumulative Merkle claims, challenge windows and value-conservation invariants.

ADVERSARIAL PROOF
The demo changes one byte after actor signing. The canister returns `ERR_ACTOR_SIGNATURE_MISMATCH`; the ladder stops at ORDERED; PC5 remains locked; nonce and escrow balance stay unchanged; zero USDC is lost.

VERIFIED EVIDENCE
Zetaris verifier 9/9; live four-row JOIN observed in 8.395 seconds. Meterless H-MEM conformance 13/13 with two stored/retrieved memories and four ledger events. Agent tests 30/30. ZEQARIS: Python 10/10, golden vectors 40/40, Rust 9/9, Solidity 9/9, Foundry invariants 500 runs and 128,000 calls with zero reverts.

BOUNDARIES
The joined relations are synthetic inputs and the timing is one observation, not a benchmark. ICP and Base modules are locally verified release candidates, not production deployments. SHA-256 values are integrity digests, not digital signatures.

