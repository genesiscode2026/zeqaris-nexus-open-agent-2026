"""Unit tests for ZetarisClient."""

import unittest
from unittest.mock import patch
import json
from agent.config import AgentConfig
from agent.zetaris_client import ZetarisClient


class FakeResponse:
    def __init__(self, payload, status=200):
        self.payload = json.dumps(payload).encode("utf-8")
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def getcode(self):
        return self.status

    def read(self):
        return self.payload

class TestZetarisClient(unittest.TestCase):

    def setUp(self):
        self.config = AgentConfig({
            "ZETARIS_REST_URL": "http://localhost:3000",
            "ZETARIS_ORG_ID": "test-org",
            "ZETARIS_API_KEY": "", # Offline mode
        })
        self.client = ZetarisClient(self.config)

    def test_live_mode_fails_closed_without_credentials(self):
        """Missing live credentials must never return fixture data as success."""
        res = self.client.run_sql("SELECT 1 AS one")
        self.assertFalse(res["success"])
        self.assertEqual(res["mode"], "LIVE_UNCONFIGURED")
        self.assertEqual(res["rows"], [])
        self.assertFalse(self.client.verify_connection())

    def test_explicit_dry_run_returns_fixture(self):
        """Fixture data is available only through an explicit dry run."""
        res = self.client.run_sql("SELECT 1 AS one", dry_run=True)
        self.assertTrue(res["success"])
        self.assertEqual(res["row_count"], 1)
        self.assertEqual(res["rows"][0]["one"], 1)
        self.assertEqual(res["mode"], "OFFLINE_SIMULATION")
        self.assertEqual(res["source"], "BUILT_IN_FIXTURE")
        self.assertTrue(bool(res["request_id"]))

    def test_market_feed_query_simulation(self):
        """Verifies querying market feeds returns multi-venue rows including the anomaly."""
        res = self.client.run_sql("SELECT * FROM market_feeds", dry_run=True)
        self.assertTrue(res["success"])
        self.assertGreaterEqual(res["row_count"], 4)
        venues = [r["venue"] for r in res["rows"]]
        self.assertIn("BINANCE", venues)
        self.assertIn("COINBASE", venues)
        self.assertIn("OKX", venues)
        self.assertIn("ANOMALY_DEX", venues)

    def test_unique_uuid_per_request(self):
        """Verifies each query gets a unique UUID X-Request-ID as required by Zetaris."""
        r1 = self.client.run_sql("SELECT 1", dry_run=True)
        r2 = self.client.run_sql("SELECT 1", dry_run=True)
        self.assertNotEqual(r1["request_id"], r2["request_id"])

    def test_local_bundle_credentials_make_data_layer_ready(self):
        config = AgentConfig({
            "ZETARIS_REST_URL": "http://localhost:3000",
            "ZETARIS_ADMIN_EMAIL": "admin@example.invalid",
            "ZETARIS_ADMIN_PASSWORD": "test-only-password",
        })
        status = config.validate_data_layer()
        self.assertTrue(status["ready"])
        self.assertTrue(status["details"]["local_session_configured"])
        self.assertFalse(status["details"]["api_key_configured"])

    def test_extract_rows_handles_nested_query_envelope(self):
        rows = ZetarisClient._extract_rows({"result": {"data": [{"one": "1"}]}})
        self.assertEqual(rows, [{"one": "1"}])

    @patch("agent.zetaris_client.urllib.request.urlopen")
    def test_local_session_executes_official_query_path(self, mock_urlopen):
        mock_urlopen.side_effect = [
            FakeResponse({"accessToken": "aaa.bbb.ccc", "orgId": 7}),
            FakeResponse({"result": {"data": [{"seven": "7"}]}}),
        ]
        config = AgentConfig({
            "ZETARIS_REST_URL": "http://localhost:3000",
            "ZETARIS_ADMIN_EMAIL": "admin@example.invalid",
            "ZETARIS_ADMIN_PASSWORD": "test-only-password",
        })
        result = ZetarisClient(config).run_sql("SELECT 7 AS seven")

        self.assertTrue(result["success"])
        self.assertEqual(result["mode"], "LIVE_ZETARIS")
        self.assertEqual(result["auth_mode"], "LOCAL_SESSION")
        self.assertEqual(result["rows"], [{"seven": "7"}])
        query_request = mock_urlopen.call_args_list[1].args[0]
        self.assertEqual(query_request.full_url, "http://localhost:3000/api/proxy/query/sql/start")
        self.assertEqual(query_request.headers["X-org-id"], "7")

if __name__ == "__main__":
    unittest.main()
