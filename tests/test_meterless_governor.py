"""Unit tests for MeterlessGovernor."""

import unittest
from agent.config import AgentConfig
from agent.meterless_governor import MeterlessGovernor

class TestMeterlessGovernor(unittest.TestCase):

    def setUp(self):
        self.config = AgentConfig({
            "METERLESS_ENABLED": "true",
            "COST_PER_QUERY_LIMIT_USD": "0.01",
        })
        self.gov = MeterlessGovernor(self.config)

    def test_prompt_retrieval(self):
        """Verifies retrieving standard prompts from prompt library."""
        prompt = self.gov.get_prompt("market_truth_explain_why")
        self.assertIn("VELQIRIS Quantitative Market Truth Agent", prompt)
        self.assertIn("Zetaris", prompt)
        self.assertIn("WHY", prompt)

    def test_usage_tracking_and_cost_estimation(self):
        """Verifies token recording and cumulative cost calculation."""
        rec = self.gov.record_usage(prompt_tokens=1000, completion_tokens=500, model_name="nemotron")
        self.assertEqual(rec["total_tokens"], 1500)
        self.assertAlmostEqual(rec["query_cost_usd"], 0.003, places=5)
        self.assertFalse(rec["exceeds_limit"])
        self.assertEqual(rec["cost_source"], "LOCAL_ESTIMATE_NOT_PROVIDER_BILLING")

    def test_cost_limit_alerting(self):
        """Verifies limit flag is raised if token cost exceeds ceiling."""
        rec = self.gov.record_usage(prompt_tokens=5000, completion_tokens=2000, model_name="nemotron")
        self.assertTrue(rec["exceeds_limit"])

    def test_telemetry_separates_hmem_from_local_cost_estimate(self):
        telemetry = self.gov.get_telemetry()
        self.assertTrue(telemetry["meterless_integration_verified"])
        self.assertIn("H-MEM", telemetry["meterless_component"])
        self.assertTrue(telemetry["cost_is_estimate"])

if __name__ == "__main__":
    unittest.main()
