from __future__ import annotations

import hmac
import json
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def _bool(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    internal_token: str
    photon_caller_id: str
    caller_tokens: dict[str, str]
    state_db_path: Path
    adapter_aic: str
    agent_cert_path: str
    agent_key_path: str
    platform_ca_bundle_path: str
    discovery_agent_url: str
    discovery_agent_aic: str
    discovery_identity_binding_enabled: bool
    discovery_timeout_seconds: int
    selected_agent_execution_enabled: bool
    pending_selection_ttl_seconds: int
    local_task_timeout_seconds: int
    aip_server_identity_binding_enabled: bool
    llm_enabled: bool
    llm_base_url: str
    llm_api_key: str
    llm_model: str
    llm_timeout_seconds: int
    llm_max_history_messages: int
    discovery_api_url: str = "https://wt.ioa.pub/discovery"

    def caller_for_token(self, token: str) -> str | None:
        """Return the trusted bridge credential label for a valid internal token."""
        for caller_id, expected_token in self.caller_tokens.items():
            if expected_token and hmac.compare_digest(token, expected_token):
                return caller_id
        return None

    @staticmethod
    def caller_for_photon_sender(sender_id: str) -> str:
        """Make a stable per-Photon-user namespace after bridge verification."""
        normalized = sender_id.strip()
        if not normalized or len(normalized) > 255 or any(ord(char) < 32 for char in normalized):
            raise ValueError("invalid Photon sender identifier")
        return f"photon:{normalized}"

    @classmethod
    def from_env(cls) -> "Settings":
        raw_tokens = os.getenv("CALLER_TOKENS_JSON", "").strip()
        try:
            caller_tokens = json.loads(raw_tokens) if raw_tokens else {}
        except json.JSONDecodeError as exc:
            raise ValueError("CALLER_TOKENS_JSON must be a JSON object of caller_id to token") from exc
        if not isinstance(caller_tokens, dict) or not all(
            isinstance(key, str) and isinstance(value, str) for key, value in caller_tokens.items()
        ):
            raise ValueError("CALLER_TOKENS_JSON must map string caller IDs to string tokens")
        internal_token = os.getenv("INTERNAL_TOKEN", "")
        photon_caller_id = os.getenv("PHOTON_CALLER_ID", "photon:default")
        if internal_token and photon_caller_id not in caller_tokens:
            caller_tokens[photon_caller_id] = internal_token
        return cls(
            internal_token=internal_token,
            photon_caller_id=photon_caller_id,
            caller_tokens=caller_tokens,
            state_db_path=Path(os.getenv("STATE_DB_PATH", "./state/imessage.sqlite3")),
            adapter_aic=os.getenv("IMESSAGE_ADAPTER_AIC", ""),
            agent_cert_path=os.getenv("AGENT_CERT_PATH", ""),
            agent_key_path=os.getenv("AGENT_KEY_PATH", ""),
            platform_ca_bundle_path=os.getenv("PLATFORM_CA_BUNDLE_PATH", ""),
            discovery_agent_url=os.getenv("DISCOVERY_AGENT_URL", ""),
            discovery_agent_aic=os.getenv("DISCOVERY_AGENT_AIC", ""),
            discovery_identity_binding_enabled=_bool("DISCOVERY_IDENTITY_BINDING_ENABLED", True),
            discovery_timeout_seconds=int(os.getenv("DISCOVERY_TIMEOUT_SECONDS", "55")),
            selected_agent_execution_enabled=_bool("SELECTED_AGENT_EXECUTION_ENABLED", True),
            pending_selection_ttl_seconds=int(os.getenv("PENDING_SELECTION_TTL_SECONDS", "86400")),
            local_task_timeout_seconds=int(os.getenv("LOCAL_TASK_TIMEOUT_SECONDS", "75")),
            # Keep direct /rpc loopback-only unless a real mTLS-aware proxy is added.
            aip_server_identity_binding_enabled=_bool("AIP_SERVER_IDENTITY_BINDING_ENABLED", False),
            llm_enabled=_bool("LLM_ENABLED", False),
            llm_base_url=os.getenv("LLM_BASE_URL", "https://api.openai.com/v1"),
            llm_api_key=os.getenv("LLM_API_KEY", ""),
            llm_model=os.getenv("LLM_MODEL", ""),
            llm_timeout_seconds=int(os.getenv("LLM_TIMEOUT_SECONDS", "30")),
            llm_max_history_messages=int(os.getenv("LLM_MAX_HISTORY_MESSAGES", "12")),
            discovery_api_url=os.getenv("DISCOVERY_API_URL", "https://wt.ioa.pub/discovery"),
        )
