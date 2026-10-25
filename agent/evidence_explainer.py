"""VELQIRIS evidence explainer for sponsor-grounded market investigations."""

import hashlib
import json
import time
from typing import Dict, Any, List, Optional
from .config import AgentConfig
from .zetaris_client import ZetarisClient
from .meterless_governor import MeterlessGovernor
from .meterless_hmem import MeterlessHMem
from .llm import NemotronLLM

class EvidenceExplainer:
    """Combines mathematical data consensus with Nemotron qualitative reasoning."""

    def __init__(
        self,
        config: Optional[AgentConfig] = None,
        zetaris_client: Optional[ZetarisClient] = None,
        governor: Optional[MeterlessGovernor] = None,
        hmem: Optional[MeterlessHMem] = None,
        llm: Optional[NemotronLLM] = None,
    ):
        self.config = config or AgentConfig()
        self.zetaris = zetaris_client or ZetarisClient(self.config)
        self.governor = governor or MeterlessGovernor(self.config)
        self.hmem = hmem or MeterlessHMem(self.config.meterless_store_path)
        self.llm = llm or NemotronLLM(self.config, self.zetaris, self.governor)

    def compute_mad_consensus(self, venue_rows: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Calculates volume-weighted median and Median Absolute Deviation (MAD) outlier filtering.

        Args:
            venue_rows: List of dicts with 'venue', 'bid', 'ask', 'volume', 'latency_ms'.

        Returns:
            Dict containing consensus price, included venues, rejected outliers, and risk regime.
        """
        if not venue_rows:
            return {
                "consensus_price": 0.0,
                "included_venues": [],
                "rejected_outliers": [],
                "risk_regime": "NO_DATA",
                "spread_bps": 0.0,
            }

        # Calculate mid prices
        prices = []
        for r in venue_rows:
            bid = float(r.get("bid", 0.0))
            ask = float(r.get("ask", 0.0))
            mid = (bid + ask) / 2.0
            prices.append((r["venue"], mid, float(r.get("volume", 1.0)), float(r.get("latency_ms", 10))))

        # Median calculation
        sorted_mids = sorted([p[1] for p in prices])
        n = len(sorted_mids)
        median_price = (
            sorted_mids[n // 2]
            if n % 2 != 0
            else (sorted_mids[(n - 1) // 2] + sorted_mids[n // 2]) / 2.0
        )

        # Calculate Median Absolute Deviation (MAD)
        abs_deviations = sorted([abs(p[1] - median_price) for p in prices])
        mad = (
            abs_deviations[n // 2]
            if n % 2 != 0
            else (abs_deviations[(n - 1) // 2] + abs_deviations[n // 2]) / 2.0
        )
        # Avoid division by zero for identical prices
        mad_threshold = max(mad * 3.0, median_price * 0.001)

        included = []
        rejected = []
        for venue, mid, vol, lat in prices:
            dev = abs(mid - median_price)
            if dev <= mad_threshold:
                included.append({"venue": venue, "mid": mid, "volume": vol, "latency_ms": lat, "deviation": dev})
            else:
                rejected.append({
                    "venue": venue,
                    "mid": mid,
                    "volume": vol,
                    "latency_ms": lat,
                    "deviation": dev,
                    "rejection_reason": f"Price deviation (+{dev:.2f}) exceeds 3.0x MAD ceiling ({mad_threshold:.2f})"
                })

        # Calculate Volume-Weighted Average Price (VWAP) across verified included venues
        total_vol = sum(v["volume"] for v in included)
        vwap = (
            sum(v["mid"] * v["volume"] for v in included) / total_vol
            if total_vol > 0
            else median_price
        )

        # Determine risk regime using only the post-filter consensus set. An
        # already rejected outlier must not inflate the reported verified spread.
        max_lat = max([v["latency_ms"] for v in included], default=0)
        included_mids = sorted(v["mid"] for v in included)
        spread_bps = (
            (abs(included_mids[-1] - included_mids[0]) / median_price) * 10000.0
            if median_price > 0 and included_mids
            else 0.0
        )

        if spread_bps < 10.0 and max_lat < 50.0:
            regime = "CALM"
        elif spread_bps < 50.0 or max_lat < 150.0:
            regime = "VOLATILE"
        else:
            regime = "DISLOCATED"

        return {
            "median_price": round(median_price, 4),
            "consensus_vwap": round(vwap, 4),
            "mad": round(mad, 4),
            "mad_threshold": round(mad_threshold, 4),
            "included_venues": included,
            "rejected_outliers": rejected,
            "spread_bps": round(spread_bps, 2),
            "risk_regime": regime,
        }

    def generate_evidence_investigation(
        self,
        query: str = "SELECT * FROM market_feeds",
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        """Runs the complete investigative loop:
        1. Query data from Zetaris.
        2. Perform mathematical consensus & MAD outlier detection.
        3. Prompt Nemotron to explain WHY the findings hold.
        4. Produce an evidence record with a SHA-256 integrity digest.
        """
        # Step 1: Query Zetaris
        sql_res = self.zetaris.run_sql(query, dry_run=dry_run)
        if not sql_res.get("success"):
            return {
                "success": False,
                "stage": "zetaris_query",
                "error": sql_res.get("error", "Zetaris query failed."),
                "execution_mode": sql_res.get("mode"),
            }
        venue_rows = sql_res.get("rows", [])

        # Step 2: Compute mathematical consensus
        consensus = self.compute_mad_consensus(venue_rows)

        # Step 3: Capture and retrieve governed context through Meterless H-MEM.
        source = f"zetaris:{sql_res.get('request_id')}"
        observation = self.hmem.add_memory(
            (
                f"Zetaris query returned {len(venue_rows)} market rows for SQL: {query}. "
                f"Execution mode: {sql_res.get('mode')}."
            ),
            source=source,
            layer="working",
            tags=["zetaris", "market-data", "query-evidence"],
            entities=[{"name": "Zetaris", "type": "data-platform"}],
        )
        finding = self.hmem.add_memory(
            (
                f"MAD consensus VWAP is {consensus['consensus_vwap']}; regime is "
                f"{consensus['risk_regime']}; {len(consensus['rejected_outliers'])} outlier(s) "
                "were rejected from the post-filter consensus set."
            ),
            source=f"velqiris:consensus:{sql_res.get('request_id')}",
            layer="long_term",
            tags=["consensus", "mad", "risk-regime"],
            entities=[
                {"name": "VELQIRIS", "type": "agent"},
                {"name": "Zetaris", "type": "data-platform"},
            ],
            related_to=[observation.id],
            derived_from=[observation.id],
        )
        retrieval = self.hmem.retrieve(
            "Zetaris market consensus MAD outliers risk regime",
            domain="market_integrity",
            tags=["zetaris", "consensus", "mad"],
            entities=["Zetaris", "VELQIRIS"],
        )
        meterless_receipt = self.hmem.receipt(
            stored_ids=[observation.id, finding.id],
            retrieval=retrieval,
        )

        # Step 4: Prepare the grounded explanation prompt.
        sys_prompt = self.governor.get_prompt("market_truth_explain_why")
        user_message = (
            f"METERLESS H-MEM RETRIEVED CONTEXT:\n{retrieval['context']}\n\n"
            f"ZETARIS TELEMETRY SNAPSHOT:\n"
            f"- SQL Executed: {query}\n"
            f"- Zetaris Request ID: {sql_res.get('request_id')}\n"
            f"- Mathematical Consensus VWAP: ${consensus['consensus_vwap']:,.2f}\n"
            f"- Median Absolute Deviation (MAD): {consensus['mad']}\n"
            f"- Risk Regime: {consensus['risk_regime']}\n"
            f"- Included Venues ({len(consensus['included_venues'])}): {json.dumps(consensus['included_venues'])}\n"
            f"- Rejected Venues ({len(consensus['rejected_outliers'])}): {json.dumps(consensus['rejected_outliers'])}\n\n"
            f"Explain to institutional risk managers WHY this consensus is solid, WHY the rejected venues were excluded, "
            f"and what actions algorithmic routers should execute."
        )

        messages = [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": user_message},
        ]

        # Step 5: Execute the configured model adapter.
        llm_res = self.llm.chat_completion(messages, dry_run=dry_run)
        if not llm_res.get("success"):
            return {
                "success": False,
                "stage": "model_inference",
                "error": llm_res.get("error", "Model inference failed."),
                "execution_mode": llm_res.get("mode"),
                "consensus": consensus,
            }

        # Step 6: Seal the evidence record with a SHA-256 integrity digest.
        proof_payload = {
            "schema_version": "2.0",
            "timestamp": time.time(),
            "execution_mode": "OFFLINE_SIMULATION" if dry_run else "LIVE",
            "data_source_mode": sql_res.get("mode"),
            "model_response_mode": llm_res.get("mode"),
            "zetaris_request_id": sql_res.get("request_id"),
            "consensus": consensus,
            "model_output": llm_res.get("content"),
            "model": llm_res.get("model"),
            "meterless_hmem": meterless_receipt,
            "meterless_telemetry": self.governor.get_telemetry(),
        }
        proof_bytes = json.dumps(proof_payload, sort_keys=True).encode("utf-8")
        evidence_hash = hashlib.sha256(proof_bytes).hexdigest()
        proof_payload["integrity_hash_sha256"] = evidence_hash

        return {
            "success": True,
            "execution_mode": proof_payload["execution_mode"],
            "evidence_hash": evidence_hash,
            "consensus": consensus,
            "model_output": llm_res.get("content"),
            "meterless_cost": self.governor.total_cost_usd,
            "proof_record": proof_payload,
        }
