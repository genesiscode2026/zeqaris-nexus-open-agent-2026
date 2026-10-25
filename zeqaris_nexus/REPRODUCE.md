# ZEQARIS NEXUS — REPRODUCTION GUIDE
**Maximum 10 Commands Reproducibility Runbook**
**Date:** October 26, 2026 | **Version:** 1.4.0

This runbook reproduces the entire cryptographic verification, canister test suite, golden test vectors, and contract test harnesses.

---

## Prerequisites
- Rust 1.80+ (`cargo`)
- Python 3.10+ (`python3`)
- Foundry (`forge`) for Solidity contract tests

---

## 10 Reproduction Commands

```bash
# 1. Run Python unit tests and adversarial tamper harness (OFFLINE)
python3 competition_submissions/zeqaris_nexus/tests/run_all_tests.py

# 2. Verify all 40 golden test vectors across JCS, Merkle, EIP-712, and secp256k1 (OFFLINE)
python3 vectors/verify_golden_vectors.py

# 3. Check Rust canister code formatting (OFFLINE)
cargo fmt --check --manifest-path canister/Cargo.toml

# 4. Run Rust canister linter with zero warnings tolerance (OFFLINE)
cargo clippy --offline --manifest-path canister/Cargo.toml -- -D warnings

# 5. Run all 9 Rust canister cryptographic & consensus binding unit tests (OFFLINE)
cargo test --offline --manifest-path canister/Cargo.toml

# 6. Build Solidity settlement contracts via Foundry (OFFLINE if dependencies installed)
forge build --root contracts

# 7. Run Foundry unit test suite (OFFLINE)
forge test --root contracts --match-path test/unit/* -vvv

# 8. Run Foundry fuzz test suite with 10,000 runs (OFFLINE)
forge test --root contracts --match-test "testFuzz" --fuzz-runs 10000

# 9. Run Foundry stateful invariant test suite with 500 runs x depth 256 (OFFLINE)
forge test --root contracts --match-path test/invariant/*

# 10. (Optional) Broadcast deployment to Base Sepolia testnet (REQUIRES NETWORK & FUNDED PRIVATE KEY)
# forge script contracts/script/DeployZeqarisEscrow.s.sol --rpc-url https://sepolia.base.org --broadcast
```

---

## Execution Classification

| Step | Scope | Mode | Expected Result |
| :--- | :--- | :--- | :--- |
| **Command 1** | Python Core & Tamper Harness | Offline | `10/10 PASS` in < 0.1s |
| **Command 2** | Golden Vectors (40 vectors) | Offline | `40/40 PASS (100% compliant)` |
| **Command 3** | Rust Formatting | Offline | Clean exit (code 0) |
| **Command 4** | Rust Clippy (`-D warnings`) | Offline | Clean exit (code 0) |
| **Command 5** | Rust Canister Unit Tests (9 tests) | Offline | `9 passed; 0 failed` in < 0.01s |
| **Command 6** | Solidity Compilation | Offline | Compiler exit code 0 |
| **Command 7** | Foundry Unit Tests | Offline | All unit tests pass |
| **Command 8** | Foundry Fuzz Suite | Offline | 10,000 runs pass |
| **Command 9** | Foundry Invariant Suite | Offline | 6/6 Invariants hold across 500x256 calls |
| **Command 10** | Live Base Sepolia Broadcast | Online | Broadcasts `ZeqarisSettlementEscrow` |
