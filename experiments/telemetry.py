"""Privacy-preserving SQLite telemetry for the iMessage/ACPs gateway."""

from __future__ import annotations

from contextlib import contextmanager
from time import perf_counter
from typing import Any, Callable, Iterator
import re
import uuid


SAFE_ATTRIBUTES = {
    "event_status", "reply_count", "candidate_count", "identity_result",
    "consent_state", "aip_state", "retry_count", "message_bytes",
    "idempotency_hit", "phase", "fault", "variant", "agent_population",
    "concurrency", "task_outcome", "endpoint_scheme", "endpoint_path_valid",
}


class Telemetry:
    def __init__(self, writer: Callable[[dict[str, Any]], None], enabled: bool = True):
        self._writer = writer
        self.enabled = enabled

    @contextmanager
    def span(
        self,
        operation: str,
        *,
        trace_id: str | None = None,
        task_id: str | None = None,
        attributes: dict[str, Any] | None = None,
    ) -> Iterator[dict[str, Any]]:
        record: dict[str, Any] = {
            "trace_id": trace_id or str(uuid.uuid4()),
            "span_id": str(uuid.uuid4()),
            "task_id": task_id,
            "operation": operation,
            "status": "ok",
            "failure_category": None,
            "attributes": self._safe(attributes or {}),
        }
        started = perf_counter()
        try:
            yield record
        except Exception as exc:
            record["status"] = "error"
            record["failure_category"] = type(exc).__name__[:80]
            raise
        finally:
            record["duration_ms"] = round((perf_counter() - started) * 1000, 3)
            if self.enabled:
                try:
                    self._writer(record)
                except Exception:
                    # Observability must never change message or task behavior.
                    pass

    @staticmethod
    def _safe(attributes: dict[str, Any]) -> dict[str, Any]:
        result = {}
        for key, value in attributes.items():
            if key not in SAFE_ATTRIBUTES:
                continue
            if isinstance(value, (str, int, float, bool)) or value is None:
                result[key] = value[:120] if isinstance(value, str) else value
        return result


def valid_trace_id(value: str | None) -> str:
    if value and re.fullmatch(r"[0-9a-fA-F-]{16,64}", value):
        return value.lower()
    return str(uuid.uuid4())
