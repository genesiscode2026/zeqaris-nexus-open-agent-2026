"""NVIDIA Nemotron LLM Interface with Tool-Calling.

Implements the Power layer integration specified in the Open Agent Hackathon 2026
Participant Setup Guide:
- Base URL: MODEL_BASE_URL (NVIDIA API or Meterless endpoint)
- API Key: MODEL_API_KEY (from .env)
- Model: NEMOTRON_MODEL (e.g. nvidia/nemotron-4-340b-instruct)
- Tool calling: run_sql tool attached to queries for retrieving data from Zetaris
"""

import json
import urllib.request
import urllib.error
from typing import Dict, Any, List, Optional
from .config import AgentConfig
from .zetaris_client import ZetarisClient
from .meterless_governor import MeterlessGovernor

class NemotronLLM:
    """Interface to NVIDIA Nemotron models with tool-calling capabilities."""

    def __init__(
        self,
        config: Optional[AgentConfig] = None,
        zetaris_client: Optional[ZetarisClient] = None,
        governor: Optional[MeterlessGovernor] = None,
    ):
        self.config = config or AgentConfig()
        self.zetaris = zetaris_client or ZetarisClient(self.config)
        self.governor = governor or MeterlessGovernor(self.config)

    @property
    def tools(self) -> List[Dict[str, Any]]:
        """The tool definition for run_sql as specified in the hackathon guide."""
        return [
            {
                "type": "function",
                "function": {
                    "name": "run_sql",
                    "description": "Executes a SQL statement against the Zetaris Unified Semantic Layer and returns governed data rows.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "sql": {
                                "type": "string",
                                "description": "The Lightning SQL statement to run (e.g., 'SELECT * FROM market_feeds')",
                            }
                        },
                        "required": ["sql"],
                    },
                },
            }
        ]

    def chat_completion(
        self,
        messages: List[Dict[str, str]],
        tools_enabled: bool = True,
        temperature: float = 0.2,
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        """Calls Nemotron model with tool definitions and Meterless metering."""
        if dry_run:
            return self._handle_offline_completion(messages)
        if not self.config.model_api_key or not self.config.nemotron_model:
            return {
                "success": False,
                "error": "Live model execution requires MODEL_API_KEY and an exact NEMOTRON_MODEL identifier.",
                "content": None,
                "mode": "LIVE_UNCONFIGURED",
            }

        endpoint = f"{self.config.model_base_url}/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.config.model_api_key}",
        }

        payload_dict: Dict[str, Any] = {
            "model": self.config.nemotron_model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": 1024,
        }
        if tools_enabled:
            payload_dict["tools"] = self.tools
            payload_dict["tool_choice"] = "auto"

        payload = json.dumps(payload_dict).encode("utf-8")

        try:
            req = urllib.request.Request(endpoint, data=payload, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = resp.read().decode("utf-8")
                res = json.loads(body)

                usage = res.get("usage", {})
                metering = self.governor.record_usage(
                    prompt_tokens=usage.get("prompt_tokens", 0),
                    completion_tokens=usage.get("completion_tokens", 0),
                    model_name=self.config.nemotron_model,
                )

                choice = res["choices"][0]
                message = choice["message"]

                # Handle tool calling if Nemotron requests run_sql
                tool_calls = message.get("tool_calls", [])
                if tool_calls:
                    return self._execute_tool_calls_and_recurse(messages, message, tool_calls)

                return {
                    "success": True,
                    "content": message.get("content", ""),
                    "model": self.config.nemotron_model,
                    "usage": usage,
                    "tool_calls_executed": len(tool_calls),
                    "mode": "LIVE_MODEL_API",
                    "local_cost_estimate": metering,
                }

        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8") if e.fp else str(e)
            if self.config.fail_closed:
                return {
                    "success": False,
                    "error": f"Nemotron API HTTP {e.code}: {err_body}",
                    "content": None,
                }
            raise
        except Exception as e:
            return {
                "success": False,
                "error": f"Nemotron Connection Error: {str(e)}",
                "content": None,
            }

    def _execute_tool_calls_and_recurse(
        self,
        history: List[Dict[str, str]],
        assistant_message: Dict[str, Any],
        tool_calls: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Executes tool calls (run_sql to Zetaris) and sends results back to Nemotron."""
        updated_messages = list(history)
        updated_messages.append(assistant_message)

        executed_tools = []
        for call in tool_calls:
            call_id = call.get("id", "call_0")
            func_name = call.get("function", {}).get("name")
            args_str = call.get("function", {}).get("arguments", "{}")
            try:
                args = json.loads(args_str)
            except (TypeError, json.JSONDecodeError) as exc:
                return {
                    "success": False,
                    "error": f"Invalid tool-call arguments: {exc}",
                    "content": None,
                    "tool_executions": executed_tools,
                    "mode": "LIVE_TOOL_FAILURE",
                }

            if func_name == "run_sql":
                sql = args.get("sql", "")
                sql_result = self.zetaris.run_sql(sql)
                executed_tools.append({"tool": "run_sql", "sql": sql, "result": sql_result})
                if not sql_result.get("success"):
                    return {
                        "success": False,
                        "error": "Nemotron requested Zetaris data, but the live query failed.",
                        "content": None,
                        "tool_executions": executed_tools,
                        "mode": "LIVE_TOOL_FAILURE",
                    }
                updated_messages.append({
                    "role": "tool",
                    "tool_call_id": call_id,
                    "name": "run_sql",
                    "content": json.dumps(sql_result.get("rows", [])),
                })

        # Recurse without tools to get the final grounded explanation
        final_response = self.chat_completion(updated_messages, tools_enabled=False)
        final_response["tool_executions"] = executed_tools
        return final_response

    def _handle_offline_completion(self, messages: List[Dict[str, str]]) -> Dict[str, Any]:
        """Provides an explicitly labelled placeholder for offline tests."""
        content = (
            "### OFFLINE SIMULATION — NO EXTERNAL MODEL WAS CALLED\n"
            "This deterministic placeholder validates orchestration only. It is not "
            "NVIDIA Nemotron output and is not evidence of a live Zetaris query. "
            "Meterless H-MEM execution is evidenced separately in the proof record."
        )
        return {
            "success": True,
            "content": content,
            "model": None,
            "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            "tool_calls_executed": 0,
            "mode": "OFFLINE_SIMULATION",
        }
