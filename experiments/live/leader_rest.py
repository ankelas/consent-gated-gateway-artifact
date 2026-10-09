"""Driver for the Leader Agent Platform REST flow (the P1/P3 ingress path).

The leader exposes `POST /api/v1/submit` and `GET /api/v1/result/{session_id}`
(see its OpenAPI document). `clientRequestId` is the gateway's idempotency key,
which is what the replay cells will reuse to test deduplication.
"""

from __future__ import annotations

import json
import ssl
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from agents import TaskRun, mtls_context


class LeaderRestClient:
    def __init__(self, base_url: str, context: Optional[ssl.SSLContext] = None,
                 timeout: float = 60.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.context = context or mtls_context()
        self.timeout = timeout

    def _request(self, path: str, method: str = "GET", payload: Optional[dict] = None) -> dict[str, Any]:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
        request = urllib.request.Request(
            f"{self.base_url}{path}", data=data,
            headers={"Content-Type": "application/json"}, method=method,
        )
        with urllib.request.urlopen(request, context=self.context, timeout=self.timeout) as response:
            return json.loads(response.read().decode("utf-8"))

    def health(self) -> dict[str, Any]:
        return self._request("/health")

    def submit(self, query: str, client_request_id: str, session_id: Optional[str] = None,
               mode: str = "direct_rpc") -> dict[str, Any]:
        body: dict[str, Any] = {"query": query, "clientRequestId": client_request_id, "mode": mode}
        if session_id:
            body["sessionId"] = session_id
        return self._request("/submit", "POST", body)

    def result(self, session_id: str, task_id: Optional[str] = None) -> dict[str, Any]:
        suffix = f"?taskId={task_id}" if task_id else ""
        return self._request(f"/result/{session_id}{suffix}")

    def run_task(self, query: str, path_label: str, client_request_id: Optional[str] = None,
                 session_id: Optional[str] = None, poll_interval: float = 2.0,
                 max_wait: float = 180.0) -> TaskRun:
        key = client_request_id or f"creq-{uuid.uuid4()}"
        run = TaskRun(endpoint=self.base_url, path_label=path_label,
                      task_id=key, text=query)
        run.started_at = datetime.now(timezone.utc).isoformat()
        clock = time.monotonic()

        submitted = (self.submit(query, key, session_id).get("result") or {})
        run.t_start_ms = (time.monotonic() - clock) * 1000
        session = submitted.get("sessionId") or session_id
        if submitted.get("activeTaskId"):
            run.task_id = submitted["activeTaskId"]
        state = str(submitted.get("externalStatus") or "")
        run.states.append((run.t_start_ms, state or "submitted"))

        while session and (time.monotonic() - clock) < max_wait:
            if state in {"COMPLETED", "FAILED", "AWAITING_INPUT"}:
                break
            time.sleep(poll_interval)
            run.polls += 1
            polled = (self.result(session).get("result") or {})
            state = str((polled.get("activeTask") or {}).get("externalStatus") or polled.get("status") or "")
            output = polled.get("userResult")
            run.states.append(((time.monotonic() - clock) * 1000, state))
            if output:
                run.products = [output]
                state = state or "completed"
                break

        # The platform can publish a user result slightly before the external
        # status flips; if output exists, the task has converged regardless.
        if run.products and state in {"", "pending", "RUNNING"}:
            state = "COMPLETED"
        run.terminal_state = state
        run.t_terminal_ms = (time.monotonic() - clock) * 1000
        return run
