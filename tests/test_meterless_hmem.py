"""Contract tests for the Meterless H-MEM integration."""

import json
from pathlib import Path
import tempfile
import unittest

from agent.meterless_hmem import MeterlessHMem, SPEC_URL


class TestMeterlessHMem(unittest.TestCase):
    def test_rejects_memory_without_provenance(self):
        with self.assertRaises(ValueError):
            MeterlessHMem().add_memory("A finding", source="")

    def test_hierarchical_capture_and_hybrid_retrieval(self):
        hmem = MeterlessHMem()
        first = hmem.add_memory(
            "Zetaris returned governed market rows for BTC/USDC.",
            source="zetaris:req-123",
            layer="working",
            tags=["zetaris", "market-data"],
            entities=[{"name": "Zetaris", "type": "data-platform"}],
        )
        hmem.add_memory(
            "MAD filtering rejected one anomalous venue.",
            source="velqiris:consensus:req-123",
            layer="long_term",
            tags=["mad", "consensus"],
            derived_from=[first.id],
        )
        result = hmem.retrieve(
            "Zetaris MAD market consensus",
            domain="market_integrity",
            tags=["zetaris", "mad"],
            entities=["Zetaris"],
        )
        self.assertEqual(len(result["trace"]), 2)
        self.assertIn("source=", result["context"])
        self.assertTrue(all(item["retrievalReason"] for item in result["trace"]))

    def test_trust_ledger_is_hash_chained_and_tamper_evident(self):
        hmem = MeterlessHMem()
        hmem.add_memory("A governed fact", source="zetaris:req-1")
        hmem.retrieve("governed fact")
        self.assertTrue(hmem.verify_ledger())
        hmem.ledger[0]["details"]["source"] = "tampered"
        self.assertFalse(hmem.verify_ledger())

    def test_persistent_store_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            hmem = MeterlessHMem(tmp)
            record = hmem.add_memory("Persistent fact", source="zetaris:req-2")
            loaded = MeterlessHMem(tmp)
            self.assertIn(record.id, loaded.memories)
            self.assertTrue(loaded.verify_ledger())
            self.assertTrue((Path(tmp) / "trust-ledger.jsonl").exists())

    def test_receipt_names_engine_scope_and_official_spec(self):
        hmem = MeterlessHMem()
        record = hmem.add_memory("Receipt fact", source="zetaris:req-3")
        retrieval = hmem.retrieve("Receipt fact")
        receipt = hmem.receipt(stored_ids=[record.id], retrieval=retrieval)
        self.assertEqual(receipt["engine"], "Meterless H-MEM")
        self.assertEqual(receipt["specification"], SPEC_URL)
        self.assertEqual(len(receipt["trust_ledger_head_sha256"]), 64)


if __name__ == "__main__":
    unittest.main()
