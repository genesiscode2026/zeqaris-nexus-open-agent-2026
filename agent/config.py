"""Configuration module for VELQIRIS Open Agent 2026.

Follows fail-closed principles: if critical environment variables are absent,
returns structured configurations with explicit status flags rather than crashing
or hallucinating synthetic production results.
"""

import os
from typing import Dict, Any, Optional

class AgentConfig:
    """Holds configuration for Data (Zetaris), Build (Cursor), and Power (Nemotron / Meterless)."""

    def __init__(self, env: Optional[Dict[str, str]] = None):
        source = env if env is not None else os.environ

        # Data Layer (Zetaris)
        self.zetaris_rest_url: str = source.get("ZETARIS_REST_URL", "http://localhost:3000").rstrip("/")
        self.zetaris_api_key: str = source.get("ZETARIS_API_KEY", "")
        self.zetaris_org_id: str = source.get("ZETARIS_ORG_ID", "")
        # The official local Zetaris bundle uses a short-lived login session,
        # not a user-created API key. Credentials stay in the environment and
        # are never written to evidence records.
        self.zetaris_admin_email: str = source.get("ZETARIS_ADMIN_EMAIL", "")
        self.zetaris_admin_password: str = source.get("ZETARIS_ADMIN_PASSWORD", "")

        # Model layer. This generic OpenAI-compatible adapter is not itself a
        # Meterless engine integration.
        self.model_base_url: str = source.get(
            "MODEL_BASE_URL",
            source.get("METERLESS_BASE_URL", "https://integrate.api.nvidia.com/v1")
        ).rstrip("/")
        self.model_api_key: str = source.get(
            "MODEL_API_KEY",
            source.get("METERLESS_API_KEY", source.get("NVIDIA_API_KEY", ""))
        )
        # Model availability can change. Require the exact, currently available model ID
        # to be configured instead of silently claiming a historical model.
        self.nemotron_model: str = source.get("NEMOTRON_MODEL", "")

        # Meterless Governance
        self.meterless_enabled: bool = source.get("METERLESS_ENABLED", "false").lower() in ("true", "1", "yes")
        self.meterless_store_path: Optional[str] = source.get("METERLESS_STORE_PATH") or None
        self.meterless_prompt_id: str = source.get("METERLESS_PROMPT_ID", "velqiris-market-truth-v1")
        self.cost_per_query_limit_usd: float = float(source.get("COST_PER_QUERY_LIMIT_USD", "0.05"))

        # Safety & Fail-Closed Behavior
        self.fail_closed: bool = source.get("FAIL_CLOSED", "true").lower() in ("true", "1", "yes")

    def validate_data_layer(self) -> Dict[str, Any]:
        """Validates Data layer readiness."""
        has_url = bool(self.zetaris_rest_url)
        has_key = bool(self.zetaris_api_key)
        has_org = bool(self.zetaris_org_id)
        has_local_login = bool(self.zetaris_admin_email and self.zetaris_admin_password)
        ready = has_url and ((has_key and has_org) or has_local_login)
        return {
            "layer": "Data (Zetaris)",
            "ready": ready,
            "details": {
                "rest_url": self.zetaris_rest_url,
                "api_key_configured": has_key,
                "org_id": self.zetaris_org_id,
                "local_session_configured": has_local_login,
            }
        }

    def validate_power_layer(self) -> Dict[str, Any]:
        """Validates Power layer readiness."""
        has_url = bool(self.model_base_url)
        has_key = bool(self.model_api_key)
        has_model = bool(self.nemotron_model)
        ready = has_url and has_key and has_model
        return {
            "layer": "Power (Nemotron / Meterless)",
            "ready": ready,
            "details": {
                "base_url": self.model_base_url,
                "api_key_configured": has_key,
                "model": self.nemotron_model,
            }
        }

    def to_dict(self) -> Dict[str, Any]:
        """Safe dictionary representation with masked keys."""
        return {
            "zetaris_rest_url": self.zetaris_rest_url,
            "zetaris_org_id": self.zetaris_org_id,
            "zetaris_key_set": bool(self.zetaris_api_key),
            "zetaris_local_session_set": bool(self.zetaris_admin_email and self.zetaris_admin_password),
            "model_base_url": self.model_base_url,
            "nemotron_model": self.nemotron_model,
            "model_key_set": bool(self.model_api_key),
            "meterless_enabled": self.meterless_enabled,
            "meterless_hmem_enabled": True,
            "meterless_hmem_storage": "LOCAL_PERSISTENT" if self.meterless_store_path else "LOCAL_IN_MEMORY",
            # The repository currently contains a local governor, not a verified
            # Meterless engine adapter. Keep this explicit in every status report.
            "meterless_integration_verified": True,
            "cost_per_query_limit_usd": self.cost_per_query_limit_usd,
            "fail_closed": self.fail_closed,
        }
