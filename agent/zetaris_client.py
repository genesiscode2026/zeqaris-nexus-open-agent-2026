"""Zetaris Data Layer Client.

Implements the official Zetaris REST API integration according to the Open Agent
Hackathon 2026 Participant Setup Guide:
- POST to ZETARIS_REST_URL + '/sql-editor/sqls/run'
- Header: Authorization: Bearer <ZETARIS_API_KEY>
- Header: X-Org-ID: <ZETARIS_ORG_ID>
- Header: X-Request-ID: <fresh UUID per request>
- Payload: {"sql": sql_statement}

Supports both live Docker execution and local dry-run / mock simulation for
test suites and offline environments.
"""

import json
import time
import uuid
import urllib.request
import urllib.error
import re
from typing import Dict, Any, List, Optional
from .config import AgentConfig

class ZetarisClient:
    """Client for executing Lightning SQL statements against the Zetaris platform."""

    def __init__(self, config: Optional[AgentConfig] = None):
        self.config = config or AgentConfig()
        self.execution_history: List[Dict[str, Any]] = []

    def run_sql(self, sql: str, dry_run: bool = False) -> Dict[str, Any]:
        """Executes a SQL query against Zetaris REST API.

        Args:
            sql: The SQL statement to execute.
            dry_run: If True, simulates execution without network calls.

        Returns:
            Dict containing status, request_id, rows, and execution metadata.
        """
        request_id = str(uuid.uuid4())
        record = {
            "request_id": request_id,
            "sql": sql,
            "org_id": self.config.zetaris_org_id,
        }

        # Simulation is available only when explicitly requested. Missing live
        # credentials must never silently fall back to fixture market data.
        if dry_run:
            return self._handle_offline_or_dry_run(sql, request_id)
        has_bearer = bool(self.config.zetaris_api_key and self.config.zetaris_org_id)
        has_local_session = bool(
            self.config.zetaris_admin_email and self.config.zetaris_admin_password
        )
        if not has_bearer and not has_local_session:
            record["status"] = "UNCONFIGURED"
            self.execution_history.append(record)
            return {
                "success": False,
                "request_id": request_id,
                "sql": sql,
                "rows": [],
                "row_count": 0,
                "mode": "LIVE_UNCONFIGURED",
                "error": (
                    "Live Zetaris execution requires either ZETARIS_API_KEY plus "
                    "ZETARIS_ORG_ID, or the official local bundle's "
                    "ZETARIS_ADMIN_EMAIL plus ZETARIS_ADMIN_PASSWORD."
                ),
            }

        try:
            if has_local_session:
                token, org_id = self._login_local()
                endpoint = f"{self.config.zetaris_rest_url}/api/proxy/query/sql/start"
                headers = {
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {token}",
                    "X-Org-ID": str(org_id),
                    "X-Request-ID": request_id,
                }
                payload_dict = {"select": sql, "pageLimit": 100}
                auth_mode = "LOCAL_SESSION"
            else:
                endpoint = f"{self.config.zetaris_rest_url}/sql-editor/sqls/run"
                headers = {
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.config.zetaris_api_key}",
                    "X-Org-ID": self.config.zetaris_org_id,
                    "X-Request-ID": request_id,
                }
                payload_dict = {"sql": sql}
                org_id = self.config.zetaris_org_id
                auth_mode = "BEARER_API_KEY"

            payload = json.dumps(payload_dict).encode("utf-8")
            req = urllib.request.Request(endpoint, data=payload, headers=headers, method="POST")
            started_at = time.perf_counter()
            with urllib.request.urlopen(req, timeout=180) as resp:
                elapsed_ms = (time.perf_counter() - started_at) * 1000.0
                status_code = resp.getcode()
                body = resp.read().decode("utf-8")
                data = json.loads(body)
                rows = self._extract_rows(data)
                record["status"] = "SUCCESS"
                record["status_code"] = status_code
                record["auth_mode"] = auth_mode
                record["org_id"] = str(org_id)
                self.execution_history.append(record)
                return {
                    "success": True,
                    "request_id": request_id,
                    "sql": sql,
                    "rows": rows,
                    "columns": data.get("columns", []) if isinstance(data, dict) else [],
                    "row_count": len(rows),
                    "mode": "LIVE_ZETARIS",
                    "auth_mode": auth_mode,
                    "elapsed_ms": round(elapsed_ms, 3),
                    "raw_response": data,
                }
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8") if e.fp else str(e)
            record["status"] = "HTTP_ERROR"
            record["error"] = err_body
            self.execution_history.append(record)
            if self.config.fail_closed:
                return {
                    "success": False,
                    "request_id": request_id,
                    "error": f"HTTP {e.code}: {err_body}",
                    "rows": [],
                }
            raise
        except Exception as e:
            record["status"] = "CONNECTION_ERROR"
            record["error"] = str(e)
            self.execution_history.append(record)
            return {
                "success": False,
                "request_id": request_id,
                "error": str(e),
                "rows": [],
            }

    def _login_local(self) -> tuple[str, str]:
        """Create the short-lived session used by the official local bundle."""
        endpoint = f"{self.config.zetaris_rest_url}/api/auth/login"
        payload = json.dumps({
            "username": self.config.zetaris_admin_email,
            "password": self.config.zetaris_admin_password,
        }).encode("utf-8")
        req = urllib.request.Request(
            endpoint,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            body = resp.read().decode("utf-8")
            data = json.loads(body)

        token = self._find_value(data, {"token", "accessToken", "access_token"})
        if not token:
            match = re.search(r"[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}", body)
            token = match.group(0) if match else None
        org_id = self._find_value(data, {"orgId", "org_id", "organizationId"})
        if not token or org_id is None:
            raise ValueError("Zetaris local login did not return both a session token and orgId.")
        return str(token), str(org_id)

    @classmethod
    def _find_value(cls, value: Any, keys: set[str]) -> Any:
        if isinstance(value, dict):
            for key, candidate in value.items():
                if key in keys and candidate not in (None, ""):
                    return candidate
            for candidate in value.values():
                found = cls._find_value(candidate, keys)
                if found not in (None, ""):
                    return found
        elif isinstance(value, list):
            for candidate in value:
                found = cls._find_value(candidate, keys)
                if found not in (None, ""):
                    return found
        return None

    @classmethod
    def _extract_rows(cls, value: Any) -> List[Dict[str, Any]]:
        """Normalize common Zetaris query envelopes without inventing rows."""
        if isinstance(value, dict):
            for key in ("rows", "data", "result", "results", "records"):
                candidate = value.get(key)
                if isinstance(candidate, list) and all(isinstance(item, dict) for item in candidate):
                    return candidate
                if isinstance(candidate, dict):
                    nested = cls._extract_rows(candidate)
                    if nested:
                        return nested
            for candidate in value.values():
                nested = cls._extract_rows(candidate)
                if nested:
                    return nested
        elif isinstance(value, list):
            if all(isinstance(item, dict) for item in value):
                return value
            for candidate in value:
                nested = cls._extract_rows(candidate)
                if nested:
                    return nested
        return []

    def _handle_offline_or_dry_run(self, sql: str, request_id: str) -> Dict[str, Any]:
        """Provides explicit fixture responses for tests and demonstrations."""
        clean_sql = sql.strip().upper()
        
        # Test query check
        if "SELECT 1" in clean_sql:
            return {
                "success": True,
                "request_id": request_id,
                "sql": sql,
                "rows": [{"one": 1}],
                "columns": ["one"],
                "row_count": 1,
                "mode": "OFFLINE_SIMULATION",
                "source": "BUILT_IN_FIXTURE",
            }
        
        # Market depth orderbook query simulation
        if "FROM MARKET_FEEDS" in clean_sql or "FROM ORDERBOOKS" in clean_sql:
            simulated_rows = [
                {"venue": "BINANCE", "pair": "BTC/USDC", "bid": 67450.20, "ask": 67451.10, "volume": 142.5, "latency_ms": 12},
                {"venue": "COINBASE", "pair": "BTC/USDC", "bid": 67449.80, "ask": 67450.90, "volume": 98.2, "latency_ms": 18},
                {"venue": "OKX", "pair": "BTC/USDC", "bid": 67450.50, "ask": 67451.40, "volume": 115.0, "latency_ms": 15},
                {"venue": "ANOMALY_DEX", "pair": "BTC/USDC", "bid": 69120.00, "ask": 69150.00, "volume": 2.1, "latency_ms": 120}, # Anomaly to be rejected
            ]
            return {
                "success": True,
                "request_id": request_id,
                "sql": sql,
                "rows": simulated_rows,
                "columns": ["venue", "pair", "bid", "ask", "volume", "latency_ms"],
                "row_count": len(simulated_rows),
                "mode": "OFFLINE_SIMULATION",
                "source": "BUILT_IN_FIXTURE",
            }

        # Default fallback
        return {
            "success": True,
            "request_id": request_id,
            "sql": sql,
            "rows": [],
            "columns": [],
            "row_count": 0,
            "mode": "OFFLINE_SIMULATION",
            "source": "BUILT_IN_FIXTURE",
        }

    def verify_connection(self) -> bool:
        """Executes SELECT 1 to verify Zetaris connectivity."""
        res = self.run_sql("SELECT 1 AS one")
        return (
            res.get("success", False)
            and res.get("mode") == "LIVE_ZETARIS"
            and res.get("row_count", 0) > 0
        )
