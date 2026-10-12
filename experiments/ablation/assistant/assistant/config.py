from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

from forwarder.config import normalize_phone

load_dotenv()


def _bool(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    """Everything one personal assistant instance needs.

    `owner_phone` is the single number this assistant serves: it is where the
    assistant delivers, and it is the identity it claims when sending.
    """

    owner_phone: str
    agent_aic: str
    internal_token: str
    sender_url: str
    sender_timeout_seconds: int
    peer_timeout_seconds: int
    discovery_agent_url: str
    discovery_agent_aic: str
    directory: dict[str, dict[str, str]] = field(default_factory=dict)
    agent_cert_path: str = ""
    agent_key_path: str = ""
    platform_ca_bundle_path: str = ""
    identity_binding_enabled: bool = False
    log_path: Path = Path("./state/assistant-log.jsonl")
    display_name: str = ""
    discovery_api_url: str = ""

    @property
    def owner_label(self) -> str:
        return self.display_name or self.owner_phone

    @classmethod
    def from_env(cls, prefix: str = "ASSISTANT") -> "Settings":
        owner = normalize_phone(os.getenv(f"{prefix}_OWNER_PHONE", ""))
        if not owner:
            raise ValueError(f"{prefix}_OWNER_PHONE must be a usable phone number")
        raw_directory = os.getenv(f"{prefix}_DIRECTORY_JSON", "").strip()
        directory: dict[str, dict[str, str]] = {}
        if raw_directory:
            parsed = json.loads(raw_directory)
            if not isinstance(parsed, dict):
                raise ValueError(f"{prefix}_DIRECTORY_JSON must be an object of phone -> {{endpoint, aic}}")
            for key, value in parsed.items():
                phone = normalize_phone(key)
                if not phone or not isinstance(value, dict):
                    continue
                directory[phone] = {
                    "endpoint": str(value.get("endpoint", "")).strip(),
                    "aic": str(value.get("aic", "")).strip(),
                }
        return cls(
            owner_phone=owner,
            agent_aic=os.getenv(f"{prefix}_AIC", ""),
            internal_token=os.getenv("INTERNAL_TOKEN", ""),
            sender_url=os.getenv("IMESSAGE_SENDER_URL", "http://127.0.0.1:9425").rstrip("/"),
            sender_timeout_seconds=int(os.getenv(f"{prefix}_SENDER_TIMEOUT_SECONDS", "30")),
            peer_timeout_seconds=int(os.getenv(f"{prefix}_PEER_TIMEOUT_SECONDS", "55")),
            discovery_agent_url=os.getenv("DISCOVERY_AGENT_URL", ""),
            discovery_agent_aic=os.getenv("DISCOVERY_AGENT_AIC", ""),
            directory=directory,
            # Only assistant-scoped names: AGENT_* belong to the iMessage adapter.
            agent_cert_path=os.getenv(f"{prefix}_CERT_PATH", ""),
            agent_key_path=os.getenv(f"{prefix}_KEY_PATH", ""),
            platform_ca_bundle_path=os.getenv(f"{prefix}_CA_BUNDLE_PATH", ""),
            identity_binding_enabled=_bool(f"{prefix}_IDENTITY_BINDING_ENABLED", False),
            log_path=Path(os.getenv(f"{prefix}_LOG_PATH", f"./state/assistant-{owner}.jsonl")),
            display_name=os.getenv(f"{prefix}_DISPLAY_NAME", ""),
            discovery_api_url=os.getenv(f"{prefix}_DISCOVERY_API_URL", ""),
        )
