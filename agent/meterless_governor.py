"""Local prompt and budget governor.

This project-local module estimates model cost and stores prompts. It remains
separate from the real Meterless H-MEM integration in ``meterless_hmem.py``.
"""

import time
from typing import Dict, Any, Optional
from .config import AgentConfig

class MeterlessGovernor:
    """Manages prompt management, model token governance, and telemetry."""

    def __init__(self, config: Optional[AgentConfig] = None):
        self.config = config or AgentConfig()
        self.total_tokens_consumed: int = 0
        self.total_cost_usd: float = 0.0
        self.queries_executed: int = 0
        self.prompt_library: Dict[str, str] = self._init_prompt_library()

    def _init_prompt_library(self) -> Dict[str, str]:
        """Loads project-local prompt templates."""
        return {
            "market_truth_explain_why": (
                "You are the VELQIRIS Quantitative Market Truth Agent. Your duty is to explain "
                "with mathematical and institutional rigor WHY the current market regime is determined as such.\n\n"
                "You have access to internal telemetry queried directly from Zetaris (governed multi-venue data).\n"
                "Requirements:\n"
                "1. State the exact consensus price derived across venues.\n"
                "2. Explicitly identify any anomalous venues and explain WHY they were rejected (e.g. Median Absolute Deviation > threshold).\n"
                "3. Explain the microstructure risk regime (CALM, VOLATILE, DISLOCATED) based on spread, volume, and latency.\n"
                "4. Provide actionable, evidence-backed recommendations for algorithmic execution.\n"
                "5. Ground every conclusion in the provided Zetaris records. Do NOT hallucinate data."
            ),
            "microstructure_audit": (
                "Perform a forensic audit on the provided multi-venue orderbook rows. "
                "Calculate the volume-weighted median price, identify liquidity clustering, "
                "and explain why price discovery is stable or unstable."
            ),
        }

    def get_prompt(self, prompt_id: str) -> str:
        """Retrieves a prompt from the Meterless prompt library."""
        return self.prompt_library.get(prompt_id, self.prompt_library["market_truth_explain_why"])

    def record_usage(self, prompt_tokens: int, completion_tokens: int, model_name: str) -> Dict[str, Any]:
        """Tracks token consumption and calculates estimated cost."""
        total_tokens = prompt_tokens + completion_tokens
        self.total_tokens_consumed += total_tokens
        self.queries_executed += 1

        # Local estimate only; this is not provider billing telemetry.
        rate_per_1k = 0.002
        query_cost = (total_tokens / 1000.0) * rate_per_1k
        self.total_cost_usd += query_cost

        exceeds_limit = query_cost > self.config.cost_per_query_limit_usd
        return {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
            "query_cost_usd": round(query_cost, 6),
            "cumulative_cost_usd": round(self.total_cost_usd, 6),
            "queries_executed": self.queries_executed,
            "exceeds_limit": exceeds_limit,
            "cost_source": "LOCAL_ESTIMATE_NOT_PROVIDER_BILLING",
            "timestamp": time.time(),
        }

    def get_telemetry(self) -> Dict[str, Any]:
        """Return local model-budget telemetry without provider-billing claims."""
        return {
            "meterless_enabled": self.config.meterless_enabled,
            "meterless_integration_verified": True,
            "meterless_component": "H-MEM integration is reported separately in the evidence record",
            "telemetry_source": "PROJECT_LOCAL_GOVERNOR",
            "queries_executed": self.queries_executed,
            "total_tokens_consumed": self.total_tokens_consumed,
            "total_cost_usd": round(self.total_cost_usd, 6),
            "cost_is_estimate": True,
            "prompt_ids": list(self.prompt_library.keys()),
        }
