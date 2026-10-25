"""
Evidence Ladder & Adversarial Tamper Harness
Part of ZEQARIS NEXUS — Autonomous Swarm Coordination & Escrow Settlement OS

Implements the 5-Stage Verification Protocol:
State 0: UNTRUSTED   (AI Intent proposed)
State 1: ORDERED     (Durable Object sequence & SQLite Outbox)
State 2: ANCHORED    (ICP Canister verification & Certified Data Root)
State 3: FINALIZED   (Base Escrow Challenge Window expiration)
State 4: PAID        (Cumulative Merkle Claim & 500 bps Royalty Payout)

Also implements the Tamper Harness demonstrating zero-loss under coordinator corruption.
"""

from enum import Enum
from dataclasses import dataclass
from typing import Dict, Any, Optional
import hashlib
import json

from .canonical_serializer import compute_event_hash, compute_payload_hash
from .secp256k1 import (
    sign_prehash_recoverable,
    private_key_to_address,
    private_key_to_compressed_pubkey,
    point_mul,
    G,
    N,
)
from .keccak256 import keccak256


EXECUTION_MODE = "CRYPTOGRAPHIC_VERIFIED_ECDSA (secp256k1 + Low-S + RFC 6979)"

# Canonical Test Signer Private Key (0x4c0883a69102937d6231471b5dbb6204fe5129617082792ae468d01a3f362318)
CANONICAL_ACTOR_PRIVKEY = "4c0883a69102937d6231471b5dbb6204fe5129617082792ae468d01a3f362318"
CANONICAL_ACTOR_ADDRESS = private_key_to_address(CANONICAL_ACTOR_PRIVKEY)


class LadderStage(str, Enum):
    UNTRUSTED = "UNTRUSTED"   # AI Proposal
    ORDERED = "ORDERED"       # Cloudflare DO SQLite
    ANCHORED = "ANCHORED"     # ICP Canister Certified Data
    FINALIZED = "FINALIZED"   # Base Challenge Window Elapsed
    PAID = "PAID"             # USDC Disbursed


@dataclass
class EvidenceStep:
    stage: LadderStage
    actor_id: str
    sequence: int
    event_hash: str
    signature: str
    verdict: str
    latency_ms: float
    pc_gate_passed: str


def verify_signature_cryptographic(event_hash_hex: str, signature_hex: str, expected_address: str) -> bool:
    """
    Simulates the ICP Canister's strict secp256k1 verification in Python.
    Recovers public key and verifies that recovered address matches expected actor.
    """
    clean_sig = signature_hex[2:] if signature_hex.startswith("0x") else signature_hex
    if len(clean_sig) != 130:
        return False

    sig_bytes = bytes.fromhex(clean_sig)
    r = int.from_bytes(sig_bytes[0:32], "big")
    s = int.from_bytes(sig_bytes[32:64], "big")
    v = sig_bytes[64]

    # Low-S check
    if s > N // 2:
        return False

    recid = v - 27 if v in (27, 28) else v
    if recid not in (0, 1):
        return False

    msg_hash = bytes.fromhex(event_hash_hex[2:] if event_hash_hex.startswith("0x") else event_hash_hex)
    z = int.from_bytes(msg_hash, "big")

    # Recover point R
    # In secp256k1: y^2 = x^3 + 7 (mod P)
    P = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEFFFFFC2F
    x = r
    alpha = (pow(x, 3, P) + 7) % P
    beta = pow(alpha, (P + 1) // 4, P)
    if pow(beta, 2, P) != alpha:
        return False

    y = beta if (beta % 2 == recid) else P - beta
    R = (x, y)

    # Recover public key: Q = r^-1 * (s * R - z * G)
    r_inv = pow(r, -1, N)
    sR = point_mul(s, R)
    zG = point_mul(z, G)
    neg_zG = (zG[0], P - zG[1]) if zG else None
    diff = None
    if sR and neg_zG:
        from .secp256k1 import point_add
        diff = point_add(sR, neg_zG)

    Q = point_mul(r_inv, diff) if diff else None
    if Q is None:
        return False

    pub_bytes = Q[0].to_bytes(32, "big") + Q[1].to_bytes(32, "big")
    recovered_addr = "0x" + keccak256(pub_bytes)[12:32].hex()

    return recovered_addr.lower() == expected_address.lower()


class CoordinationCockpit:
    def __init__(self, swarm_budget_micro_usdc: int = 100_000_000): # $100 USDC
        self.swarm_budget = swarm_budget_micro_usdc
        self.spent_budget = 0
        self.last_accepted_sequence = 0
        self.last_accepted_event_hash = "0x" + "00" * 32
        self.settlement_nonce = 0
        self.escrow_balance_micro_usdc = 100_000_000
        self.royalty_balance_micro_usdc = 0

    def simulate_tamper_attack(
        self,
        envelope: Dict[str, Any],
        raw_payload: bytes,
        actor_private_key: str = CANONICAL_ACTOR_PRIVKEY
    ) -> Dict[str, Any]:
        """
        Executes Attack Scenario 1: Tamper Byte.
        Demonstrates that if a rogue relay / compromised DO mutates 1 byte in the payload,
        the actor's cryptographic signature fails verification in the ICP Canister,
        locking PC5 and ensuring 0 USDC transfer.
        """
        initial_nonce = self.settlement_nonce
        initial_escrow = self.escrow_balance_micro_usdc
        initial_royalty = self.royalty_balance_micro_usdc

        # 1. Honest Actor computes honest payload hash and signs honest event
        actor_address = private_key_to_address(actor_private_key)
        envelope["actorKeyId"] = actor_address
        honest_payload_hash = compute_payload_hash(raw_payload)
        envelope["canonicalPayloadHash"] = honest_payload_hash
        envelope["sequence"] = str(self.last_accepted_sequence + 1)
        envelope["previousEventHash"] = self.last_accepted_event_hash
        honest_event_hash = compute_event_hash(envelope)

        # Real secp256k1 recoverable signature over honest_event_hash
        event_hash_bytes = bytes.fromhex(honest_event_hash[2:])
        sig_bytes, recid = sign_prehash_recoverable(actor_private_key, event_hash_bytes)
        actor_signature = "0x" + sig_bytes.hex()
        envelope["signature"] = actor_signature

        # Verify that honest signature validates
        assert verify_signature_cryptographic(honest_event_hash, actor_signature, actor_address), "Honest sig failed!"

        # 2. Tamper Harness (Adversarial DO / MitM) mutates payload byte
        tampered_payload = bytearray(raw_payload)
        tampered_payload[0] ^= 0xFF # Flip 1 byte
        tampered_payload_hash = compute_payload_hash(bytes(tampered_payload))
        
        # Malicious DO updates payload hash in envelope to match tampered payload
        tampered_envelope = dict(envelope)
        tampered_envelope["canonicalPayloadHash"] = tampered_payload_hash
        
        # When Canister receives tampered envelope, it recomputes event_hash:
        recomputed_event_hash = compute_event_hash(tampered_envelope)

        # Verification check in ICP Canister:
        is_signature_valid = verify_signature_cryptographic(recomputed_event_hash, actor_signature, actor_address)

        # 3. ICP Canister Verification Result
        if not is_signature_valid:
            rejection_code = "ERR_ACTOR_SIGNATURE_MISMATCH"
            ladder_status = LadderStage.ORDERED # Halted at ORDERED
            pc5_status = "LOCKED"
            # State remains unchanged!
        else:
            rejection_code = "NONE"
            ladder_status = LadderStage.PAID
            pc5_status = "UNLOCKED"
            self.settlement_nonce += 1

        return {
            "attack": "Tamper Byte in Relay",
            "tampered_byte_index": 0,
            "signature_verified": is_signature_valid,
            "rejection_code": rejection_code,
            "ladder_halt_stage": ladder_status.value,
            "pc5_status": pc5_status,
            "settlement_nonce_before": initial_nonce,
            "settlement_nonce_after": self.settlement_nonce,
            "escrow_balance_before": initial_escrow,
            "escrow_balance_after": self.escrow_balance_micro_usdc,
            "royalty_balance_before": initial_royalty,
            "royalty_balance_after": self.royalty_balance_micro_usdc,
            "funds_lost": 0
        }

    def simulate_overspend_attack(self, requested_payout_micro_usdc: int) -> Dict[str, Any]:
        """
        Executes Attack Scenario 3: Overspend Intent.
        AI hallucinates or requests funds exceeding swarm budget quota.
        PC1 fails closed before state transition or signing.
        """
        if self.spent_budget + requested_payout_micro_usdc > self.swarm_budget:
            return {
                "attack": "Overspend Intent",
                "requested": requested_payout_micro_usdc,
                "available_budget": self.swarm_budget - self.spent_budget,
                "pc_gate": "PC1_BUDGET_EXCEEDED",
                "status": "REJECTED_FAIL_CLOSED",
                "funds_lost": 0
            }
        self.spent_budget += requested_payout_micro_usdc
        return {"status": "APPROVED", "spent": requested_payout_micro_usdc}
