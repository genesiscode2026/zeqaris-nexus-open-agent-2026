"""
Unit Tests for ZEQARIS-JCS-1 Canonical Serialization Engine
"""

import unittest
import json
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.canonical_serializer import (
    canonicalize_jcs,
    compute_event_hash,
    compute_payload_hash,
    CanonicalizationError,
    validate_decimal_string
)


class TestCanonicalJCS(unittest.TestCase):

    def setUp(self):
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
            "eventType": "TASK_CREATED",
            "canonicalPayloadHash": "0xe3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            "policyVersionHash": "0x9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08",
            "timestampLogical": "1729891200000",
            "nonce": "0"
        }

    def test_canonical_key_sorting(self):
        # Keys in reverse order
        d = {"z": 1, "a": 2, "m": 3}
        canonical = canonicalize_jcs(d)
        self.assertEqual(canonical, b'{"a":2,"m":3,"z":1}')

    def test_deterministic_event_hash(self):
        h1 = compute_event_hash(self.base_envelope)
        h2 = compute_event_hash(dict(reversed(list(self.base_envelope.items()))))
        self.assertEqual(h1, h2)
        self.assertTrue(h1.startswith("0x"))
        self.assertEqual(len(h1), 66) # 0x + 64 hex chars

    def test_reject_float(self):
        with self.assertRaises(CanonicalizationError):
            canonicalize_jcs({"price": 10.5})

    def test_reject_leading_zeros(self):
        with self.assertRaises(CanonicalizationError):
            validate_decimal_string("0123", "sequence")
        # "0" alone is valid
        self.assertEqual(validate_decimal_string("0", "nonce"), "0")
        # Positive without leading zero is valid
        self.assertEqual(validate_decimal_string("1042", "sequence"), "1042")

    def test_reject_unknown_field(self):
        bad_envelope = dict(self.base_envelope)
        bad_envelope["maliciousInjection"] = "exploit"
        with self.assertRaises(CanonicalizationError):
            compute_event_hash(bad_envelope)

    def test_payload_hash_domain_separation(self):
        raw = b'{"prompt":"summarize","budget":100}'
        ph = compute_payload_hash(raw)
        self.assertTrue(ph.startswith("0x"))
        self.assertEqual(len(ph), 66)


if __name__ == "__main__":
    unittest.main()
