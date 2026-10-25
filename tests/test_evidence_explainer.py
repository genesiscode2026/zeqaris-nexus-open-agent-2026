"""Unit tests for EvidenceExplainer engine."""

import hashlib
import json
import unittest
from agent.config import AgentConfig
from agent.evidence_explainer import EvidenceExplainer

class TestEvidenceExplainer(unittest.TestCase):

    def setUp(self):
        self.config = AgentConfig({"FAIL_CLOSED": "true"})
        self.explainer = EvidenceExplainer(self.config)

    def test_mad_consensus_identifies_anomaly(self):
        """Verifies MAD algorithm isolates the anomalous venue and preserves Tier-1 venues."""
        venue_rows = [
            {"venue": "BINANCE", "bid": 67450.0, "ask": 67451.0, "volume": 100.0, "latency_ms": 10},
            {"venue": "COINBASE", "bid": 67449.0, "ask": 67450.0, "volume": 100.0, "latency_ms": 12},
            {"venue": "OKX", "bid": 67450.5, "ask": 67451.5, "volume": 100.0, "latency_ms": 11},
            {"venue": "FLASH_LOAN_DEX", "bid": 69900.0, "ask": 70000.0, "volume": 1.0, "latency_ms": 250}, # Major anomaly
        ]
        res = self.explainer.compute_mad_consensus(venue_rows)
        self.assertAlmostEqual(res["median_price"], 67450.25, delta=1.0)
        self.assertEqual(len(res["included_venues"]), 3)
        self.assertEqual(len(res["rejected_outliers"]), 1)
        self.assertEqual(res["rejected_outliers"][0]["venue"], "FLASH_LOAN_DEX")
        self.assertIn("exceeds 3.0x MAD ceiling", res["rejected_outliers"][0]["rejection_reason"])

    def test_risk_regime_classification(self):
        """Verifies risk regime is CALM under tight spread and low latency."""
        calm_rows = [
            {"venue": "BINANCE", "bid": 67450.0, "ask": 67450.2, "volume": 100.0, "latency_ms": 8},
            {"venue": "COINBASE", "bid": 67449.9, "ask": 67450.1, "volume": 100.0, "latency_ms": 10},
        ]
        res = self.explainer.compute_mad_consensus(calm_rows)
        self.assertEqual(res["risk_regime"], "CALM")

    def test_rejected_outlier_does_not_inflate_verified_spread(self):
        rows = [
            {"venue": "A", "bid": 100.00, "ask": 100.02, "volume": 10.0, "latency_ms": 10},
            {"venue": "B", "bid": 100.01, "ask": 100.03, "volume": 10.0, "latency_ms": 11},
            {"venue": "C", "bid": 99.99, "ask": 100.01, "volume": 10.0, "latency_ms": 12},
            {"venue": "OUTLIER", "bid": 150.0, "ask": 151.0, "volume": 1.0, "latency_ms": 500},
        ]
        res = self.explainer.compute_mad_consensus(rows)
        self.assertEqual([r["venue"] for r in res["rejected_outliers"]], ["OUTLIER"])
        self.assertLess(res["spread_bps"], 50.0)
        self.assertEqual(res["risk_regime"], "CALM")

    def test_generate_offline_evidence_with_integrity_hash(self):
        """Explicit dry run produces a labelled simulation and SHA-256 integrity hash."""
        inv = self.explainer.generate_evidence_investigation(
            "SELECT * FROM market_feeds",
            dry_run=True,
        )
        self.assertTrue(inv["success"])
        self.assertEqual(len(inv["evidence_hash"]), 64) # SHA-256 hex length
        self.assertEqual(inv["execution_mode"], "OFFLINE_SIMULATION")
        self.assertIn("OFFLINE SIMULATION", inv["model_output"])
        self.assertIn("consensus", inv)
        self.assertIn("proof_record", inv)
        self.assertEqual(
            inv["proof_record"]["integrity_hash_sha256"],
            inv["evidence_hash"],
        )
        hmem = inv["proof_record"]["meterless_hmem"]
        self.assertEqual(hmem["engine"], "Meterless H-MEM")
        self.assertEqual(len(hmem["stored_memory_ids"]), 2)
        self.assertGreaterEqual(hmem["trust_ledger_entries"], 4)
        self.assertEqual(len(hmem["trust_ledger_head_sha256"]), 64)
        unhashed_record = dict(inv["proof_record"])
        unhashed_record.pop("integrity_hash_sha256")
        recomputed = hashlib.sha256(
            json.dumps(unhashed_record, sort_keys=True).encode("utf-8")
        ).hexdigest()
        self.assertEqual(recomputed, inv["evidence_hash"])

    def test_live_investigation_fails_closed_without_credentials(self):
        inv = self.explainer.generate_evidence_investigation("SELECT * FROM market_feeds")
        self.assertFalse(inv["success"])
        self.assertEqual(inv["stage"], "zetaris_query")
        self.assertEqual(inv["execution_mode"], "LIVE_UNCONFIGURED")

if __name__ == "__main__":
    unittest.main()
