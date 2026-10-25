"""Capture redaction-safe Zetaris evidence and prepare Meterless H-MEM input.

The script reads only the two local-bundle login fields from a Zetaris `.env`
file. Secrets and session tokens are never printed or written to output files.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent.config import AgentConfig
from agent.evidence_explainer import EvidenceExplainer
from agent.zetaris_client import ZetarisClient


CONNECTIVITY_SQL = "SELECT 7 AS seven"
MARKET_SCENARIO_SQL = """
SELECT
    market_ticks.venue,
    market_ticks.pair,
    market_ticks.bid,
    market_ticks.ask,
    market_ticks.volume,
    venue_telemetry.latency_ms,
    venue_telemetry.status
FROM (
    SELECT 'BINANCE' AS venue, 'BTC/USDC' AS pair, 67450.20 AS bid, 67451.10 AS ask, 142.5 AS volume
    UNION ALL SELECT 'COINBASE', 'BTC/USDC', 67449.80, 67450.90, 98.2
    UNION ALL SELECT 'OKX', 'BTC/USDC', 67450.50, 67451.40, 115.0
    UNION ALL SELECT 'ANOMALY_DEX', 'BTC/USDC', 69120.00, 69150.00, 2.1
) market_ticks
INNER JOIN (
    SELECT 'BINANCE' AS venue, 12 AS latency_ms, 'HEALTHY' AS status
    UNION ALL SELECT 'COINBASE', 18, 'HEALTHY'
    UNION ALL SELECT 'OKX', 15, 'HEALTHY'
    UNION ALL SELECT 'ANOMALY_DEX', 120, 'DEGRADED'
) venue_telemetry
ON market_ticks.venue = venue_telemetry.venue
""".strip()


def read_required_env(path: Path) -> dict[str, str]:
    allowed = {"ZETARIS_ADMIN_EMAIL", "ZETARIS_ADMIN_PASSWORD"}
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key in allowed:
            values[key] = value
    missing = sorted(allowed - values.keys())
    if missing:
        raise ValueError(f"Missing required local Zetaris settings: {', '.join(missing)}")
    return values


def public_query_result(result: dict) -> dict:
    raw = result.get("raw_response", {})
    digest = hashlib.sha256(
        json.dumps(raw, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return {
        "success": result.get("success", False),
        "request_id": result.get("request_id"),
        "sql": result.get("sql"),
        "rows": result.get("rows", []),
        "row_count": result.get("row_count", 0),
        "mode": result.get("mode"),
        "auth_mode": result.get("auth_mode"),
        "elapsed_ms": result.get("elapsed_ms"),
        "response_sha256": digest,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--zetaris-env", required=True)
    parser.add_argument("--receipt", required=True)
    parser.add_argument("--meterless-input", required=True)
    args = parser.parse_args()

    settings = read_required_env(Path(args.zetaris_env))
    config = AgentConfig({
        "ZETARIS_REST_URL": "http://localhost:3000",
        **settings,
    })
    client = ZetarisClient(config)

    connectivity = client.run_sql(CONNECTIVITY_SQL)
    if not connectivity.get("success") or connectivity.get("row_count", 0) < 1:
        raise RuntimeError(f"Zetaris connectivity query failed: {connectivity.get('error', 'no rows')}")

    scenario = client.run_sql(MARKET_SCENARIO_SQL)
    if not scenario.get("success") or scenario.get("row_count", 0) != 4:
        raise RuntimeError(
            f"Zetaris market scenario query failed: {scenario.get('error', 'unexpected row count')}"
        )

    consensus = EvidenceExplainer(config).compute_mad_consensus(scenario["rows"])
    created_at = datetime.now(timezone.utc).isoformat()
    run_id = f"velqiris-live-{connectivity['request_id']}"
    receipt = {
        "schema_version": "1.0",
        "created_at_utc": created_at,
        "run_id": run_id,
        "status": "VERIFIED_LIVE_ZETARIS",
        "platform": "Zetaris local Docker bundle 2.4.3",
        "endpoint": "http://localhost:3000",
        "connectivity_query": public_query_result(connectivity),
        "market_scenario": {
            "data_classification": "DECLARED_SYNTHETIC_MULTI_RELATION_JOIN_EXECUTED_BY_LIVE_ZETARIS",
            "logical_relations": ["market_ticks", "venue_telemetry"],
            "join_key": "venue",
            "claim_boundary": (
                "This proves live Zetaris SQL execution of a join across two declared "
                "synthetic logical relations and subsequent VELQIRIS processing. It does "
                "not claim that the relations are independently onboarded external data "
                "sources or that they connect to production exchange feeds."
            ),
            "query_result": public_query_result(scenario),
            "velqiris_mad_consensus": consensus,
        },
        "model_execution": "NOT_INVOKED_IN_THIS_RECEIPT",
        "secret_handling": "Credentials and session tokens were neither printed nor persisted.",
    }

    receipt_path = Path(args.receipt)
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")

    meterless_input = {
        "runId": run_id,
        "query": "Zetaris market consensus MAD outlier risk regime",
        "memories": [
            {
                "content": (
                    f"Live Zetaris request {scenario['request_id']} executed a declared synthetic "
                    f"four-venue SQL scenario joining market_ticks with venue_telemetry "
                    f"and returned {scenario['row_count']} rows."
                ),
                "source": f"zetaris:{scenario['request_id']}",
                "type": "factual",
                "layer": "working",
                "confidence": 1.0,
                "tags": ["zetaris", "live-query", "market-integrity"],
            },
            {
                "content": (
                    f"VELQIRIS computed consensus VWAP {consensus['consensus_vwap']} and rejected "
                    f"{len(consensus['rejected_outliers'])} MAD outlier from the live Zetaris result."
                ),
                "source": f"velqiris:consensus:{scenario['request_id']}",
                "type": "factual",
                "layer": "long_term",
                "confidence": 1.0,
                "tags": ["meterless", "hmem", "mad", "consensus"],
            },
        ],
    }
    input_path = Path(args.meterless_input)
    input_path.parent.mkdir(parents=True, exist_ok=True)
    input_path.write_text(json.dumps(meterless_input, indent=2) + "\n", encoding="utf-8")

    print(f"Zetaris live receipt written: {receipt_path}")
    print(f"Meterless H-MEM input written: {input_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
