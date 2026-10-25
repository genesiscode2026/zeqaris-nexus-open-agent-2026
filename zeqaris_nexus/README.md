# ZEQARIS NEXUS

> **Cryptographically Verifiable Autonomous Swarm Coordination & Escrow Settlement OS**

A 3-tier distributed operating system bridging edge coordination, decentralized threshold verification, and immutable Base L2 settlement for autonomous multi-agent economies.

---

## Architectural Separation of Authority

1. **Edge Swarm Coordination (Cloudflare Durable Objects + SQLite):**
   - High-throughput sub-10ms event ordering, local ACID persistence (`ctx.storage.sql`), and WebSocket hibernation.
   - Note on cloud economics: *Hibernation-eligible idle duration incurs no duration charges; active CPU and storage I/O remain metered.*
2. **Canonical Registration & Threshold Verification (Internet Computer Rust Canister):**
   - Ingests signed batches, verifies actor cryptographic signatures against registered public keys.
   - Replays deterministic reducer to compute canonical state transitions.
   - Commits 32-byte state root into ICP Certified Data (BLS threshold consensus).
   - Generates Base transaction authorizations via native Chain Fusion Threshold ECDSA (`secp256k1`).
3. **Financial Finality & Immutable Royalty Escrow (Base EVM):**
   - `ZeqarisSettlementEscrow.sol` enforces cumulative Merkle claims and sponsored batch claims.
   - Immutable **500 bps (5.00%) royalty invariant** locked to `0xC6F86e170411182114FcCdb28793dC76B5e8D144` on Base native USDC (`0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913`).
   - Remainder Accumulator accounts for fractional micro-USDC units ($10^{-6}$), eliminating rounding drift across epochs.

---

## The 5-Stage Evidence Ladder

$$\text{UNTRUSTED (AI Intent)} \longrightarrow \text{ORDERED (Cloudflare DO)} \longrightarrow \text{ANCHORED (ICP Canister)} \longrightarrow \text{FINALIZED (Base Challenge Window)} \longrightarrow \text{PAID (USDC Escrow)}$$

---

## Running Verification

```bash
python3 competition_submissions/zeqaris_nexus/tests/run_all_tests.py
```
