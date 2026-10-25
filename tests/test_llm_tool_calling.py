"""Unit tests for NemotronLLM tool calling and completions."""

import unittest
from agent.config import AgentConfig
from agent.llm import NemotronLLM

class TestNemotronLLM(unittest.TestCase):

    def setUp(self):
        self.config = AgentConfig({
            "MODEL_BASE_URL": "https://integrate.api.nvidia.com/v1",
            "NEMOTRON_MODEL": "configured-model-id",
            "MODEL_API_KEY": "", # Offline mode
        })
        self.llm = NemotronLLM(self.config)

    def test_run_sql_tool_schema(self):
        """Verifies tool definition adheres to OpenAI function calling spec."""
        tools = self.llm.tools
        self.assertEqual(len(tools), 1)
        tool = tools[0]
        self.assertEqual(tool["type"], "function")
        self.assertEqual(tool["function"]["name"], "run_sql")
        self.assertIn("sql", tool["function"]["parameters"]["properties"])
        self.assertIn("Zetaris", tool["function"]["description"])

    def test_offline_deterministic_completion(self):
        """Offline output is explicitly identified as a simulation."""
        messages = [{"role": "user", "content": "Explain why the consensus holds."}]
        res = self.llm.chat_completion(messages, dry_run=True)
        self.assertTrue(res["success"])
        self.assertIn("OFFLINE SIMULATION", res["content"])
        self.assertIn("NO EXTERNAL MODEL WAS CALLED", res["content"])
        self.assertIsNone(res["model"])
        self.assertEqual(res["usage"]["total_tokens"], 0)

    def test_live_completion_fails_closed_without_key(self):
        messages = [{"role": "user", "content": "Explain why the consensus holds."}]
        res = self.llm.chat_completion(messages)
        self.assertFalse(res["success"])
        self.assertEqual(res["mode"], "LIVE_UNCONFIGURED")
        self.assertIsNone(res["content"])

if __name__ == "__main__":
    unittest.main()
