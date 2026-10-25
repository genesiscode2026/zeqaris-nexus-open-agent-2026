"""Regression tests for the Track 02 multi-relation query and audit viewer."""

import json
from pathlib import Path
import tempfile
import unittest

from scripts.capture_live_integrations import MARKET_SCENARIO_SQL
from scripts.generate_audit_viewer import load_ledger, load_receipt, render_dashboard, script_safe_json


class TestTrack02Atomic(unittest.TestCase):
    def test_scenario_names_both_logical_relations(self):
        self.assertIn("market_ticks", MARKET_SCENARIO_SQL)
        self.assertIn("venue_telemetry", MARKET_SCENARIO_SQL)

    def test_scenario_joins_relations_on_venue(self):
        normalized = " ".join(MARKET_SCENARIO_SQL.split()).lower()
        self.assertIn("inner join", normalized)
        self.assertIn("market_ticks.venue = venue_telemetry.venue", normalized)

    def test_scenario_preserves_four_market_rows(self):
        self.assertEqual(MARKET_SCENARIO_SQL.count("AS venue"), 2)
        self.assertEqual(MARKET_SCENARIO_SQL.count("UNION ALL SELECT"), 6)

    def test_loaders_reject_invalid_receipt_and_parse_jsonl(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bad = root / "bad.json"
            bad.write_text("{}", encoding="utf-8")
            with self.assertRaises(ValueError):
                load_receipt(bad)
            ledger = root / "ledger.jsonl"
            ledger.write_text('{"action":"create"}\n\n{"action":"access"}\n', encoding="utf-8")
            self.assertEqual([x["action"] for x in load_ledger(ledger)], ["create", "access"])

    def test_dashboard_embeds_receipt_and_ledger_without_remote_dependencies(self):
        receipt = {"run_id": "run-1", "market_scenario": {"query_result": {"rows": [], "row_count": 0}}}
        page = render_dashboard(receipt, [{"action": "create", "memoryId": "mem-1"}])
        self.assertIn("VELQIRIS Audit Viewer", page)
        self.assertIn('"run_id":"run-1"', page)
        self.assertNotIn("https://cdn", page)
        self.assertNotIn("<script src=", page)

    def test_embedded_json_escapes_script_terminator(self):
        encoded = script_safe_json({"value": "</script><script>alert(1)</script>"})
        self.assertNotIn("</script>", encoded)
        self.assertEqual(json.loads(encoded)["value"], "</script><script>alert(1)</script>")


if __name__ == "__main__":
    unittest.main()
