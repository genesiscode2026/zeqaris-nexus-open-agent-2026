"""
Unit Tests for Evidence Ladder & Proof-of-Coordination Replay
"""

import unittest
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.evidence_ladder import CoordinationCockpit, LadderStage


class TestProofOfCoordination(unittest.TestCase):

    def setUp(self):
        self.cockpit = CoordinationCockpit(swarm_budget_micro_usdc=100_000_000)
        self.base_envelope = {
            "protocolVersion": 1,
            "schemaVersion": 1,
            "environment": "base-sepolia",
            "swarmId": "0x7a3f00000000000000000000000000000000000000000000000000000000b891",
            "taskId": "task-001",
            "actorId": "agent-alpha",
            "actorKeyId": "0x1111111111111111111111111111111111111111",
            "sequence": "1",
            "previousEventHash": "0x0000000000000000000000000000000000000000000000000000000000000000",
            "eventType": "TASK_COMPLETED",
            "canonicalPayloadHash": "0x0000000000000000000000000000000000000000000000000000000000000000",
            "policyVersionHash": "0x9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08",
            "timestampLogical": "1729891200000",
            "nonce": "0"
        }

    def test_attack_scenario_1_tamper_byte(self):
        raw_payload = b'{"task_result":"consensus_achieved","agent_payout":50000}'
        res = self.cockpit.simulate_tamper_attack(dict(self.base_envelope), raw_payload)
        
        # Invariants under attack:
        self.assertFalse(res["signature_verified"])
        self.assertEqual(res["rejection_code"], "ERR_ACTOR_SIGNATURE_MISMATCH")
        self.assertEqual(res["ladder_halt_stage"], LadderStage.ORDERED.value)
        self.assertEqual(res["pc5_status"], "LOCKED")
        self.assertEqual(res["funds_lost"], 0)
        self.assertEqual(res["settlement_nonce_before"], res["settlement_nonce_after"])
        self.assertEqual(res["escrow_balance_before"], res["escrow_balance_after"])

    def test_attack_scenario_3_overspend_intent(self):
        # Budget is 100 USDC (100_000_000 micro-USDC)
        # Attempt to request 150 USDC
        res = self.cockpit.simulate_overspend_attack(150_000_000)
        self.assertEqual(res["status"], "REJECTED_FAIL_CLOSED")
        self.assertEqual(res["pc_gate"], "PC1_BUDGET_EXCEEDED")
        self.assertEqual(res["funds_lost"], 0)


if __name__ == "__main__":
    unittest.main()
