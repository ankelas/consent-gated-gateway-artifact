from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def _bool(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def normalize_phone(value: str) -> str | None:
    """Return an E.164 number, or None when the input cannot be one."""
    raw = (value or "").strip()
    if not raw or any(char.isalpha() for char in raw):
        return None
    if not all(char.isdigit() or char in "+ ()\t.-" for char in raw):
        return None
    digits = "".join(char for char in raw if char.isdigit())
    if len(digits) == 11 and digits.startswith("1"):
        digits = f"86{digits}"  # mainland mobile number without country code
    if len(digits) < 7 or len(digits) > 15:
        return None
    return f"+{digits}"


def edit_distance(left: str, right: str) -> int:
    """Levenshtein distance, used to spot a mistyped target number."""
    if left == right:
        return 0
    if not left:
        return len(right)
    if not right:
        return len(left)
    previous = list(range(len(right) + 1))
    for i, left_char in enumerate(left, start=1):
        current = [i]
        for j, right_char in enumerate(right, start=1):
            current.append(
                min(
                    previous[j] + 1,
                    current[j - 1] + 1,
                    previous[j - 1] + (left_char != right_char),
                )
            )
        previous = current
    return previous[-1]


@dataclass(frozen=True)
class Settings:
    agent_aic: str
    internal_token: str
    sender_url: str
    sender_timeout_seconds: int
    allowed_numbers: tuple[str, ...]
    log_path: Path
    identity_binding_enabled: bool

    def is_allowed(self, phone: str) -> bool:
        """An empty allow-list means "any number", which is convenient but open."""
        return not self.allowed_numbers or phone in self.allowed_numbers

    def closest_allowed(self, phone: str, tolerance: int = 2) -> str | None:
        """Nearest allow-listed number when the target looks like a typo of it."""
        if not self.allowed_numbers:
            return None
        target = phone.lstrip("+")
        best: str | None = None
        best_distance = tolerance + 1
        for candidate in self.allowed_numbers:
            distance = edit_distance(target, candidate.lstrip("+"))
            if distance < best_distance:
                best, best_distance = candidate, distance
        return best if best_distance <= tolerance else None

    @classmethod
    def from_env(cls) -> "Settings":
        raw_allowed = os.getenv("FORWARDER_ALLOWED_NUMBERS", "")
        allowed = tuple(
            number
            for number in (normalize_phone(part) for part in raw_allowed.split(","))
            if number
        )
        return cls(
            agent_aic=os.getenv("FORWARDER_AGENT_AIC", ""),
            internal_token=os.getenv("INTERNAL_TOKEN", ""),
            sender_url=os.getenv("IMESSAGE_SENDER_URL", "http://127.0.0.1:9425").rstrip("/"),
            sender_timeout_seconds=int(os.getenv("FORWARDER_SENDER_TIMEOUT_SECONDS", "30")),
            allowed_numbers=allowed,
            log_path=Path(os.getenv("FORWARDER_LOG_PATH", "./state/forwarder-log.jsonl")),
            identity_binding_enabled=_bool("FORWARDER_IDENTITY_BINDING_ENABLED", False),
        )
