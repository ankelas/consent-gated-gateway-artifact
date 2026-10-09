"""mTLS AIP client and agent identity helpers for the live study.

The AIP JSON-RPC envelope follows the pattern already used by the deployment
(`acps-upgrade-20260924/mq-e2e-20260928/direct_rpc_check.py`):

    POST <endpoint>
    {"jsonrpc":"2.0","id":"rpc-<uuid>","method":"rpc",
     "params":{"command":{...task-command...}}}

All calls are plain HTTP requests over a mutually authenticated TLS context.
The module never logs or stores key material.
"""

from __future__ import annotations

import json
import ssl
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


DEFAULT_CLIENT_DIR = Path("/data/caiyizhang/acps-upgrade-20260924/mq-e2e-20260928/keyfiles")
DEFAULT_LEADER_AIC_FILE = Path("/tmp/leader_aic.txt")


def leader_aic(path: Path = DEFAULT_LEADER_AIC_FILE) -> str:
    if not path.exists():
        raise SystemExit(f"leader AIC file not found: {path}")
    return path.read_text(encoding="utf-8").strip()


def mtls_context(client_dir: Path = DEFAULT_CLIENT_DIR) -> ssl.SSLContext:
    context = ssl.create_default_context(cafile=str(client_dir / "trust-bundle.pem"))
    context.load_cert_chain(str(client_dir / "client.pem"), str(client_dir / "client.key"))
    # The gateway certificate carries an AIC common name and no IP SAN; the
    # identity that matters here is bound in the certificate, not in the host
    # name, which is what the deployment's own client does too.
    context.check_hostname = False
    return context


def task_command(sender_aic: str, kind: str, task_id: Optional[str] = None,
                 text: Optional[str] = None, sender_role: str = "leader") -> dict[str, Any]:
    command: dict[str, Any] = {
        "type": "task-command",
        "id": f"cmd-{uuid.uuid4()}",
        "sentAt": datetime.now(timezone.utc).isoformat(),
        "senderRole": sender_role,
        "senderId": sender_aic,
        "command": kind,
    }
    if task_id:
        command["taskId"] = task_id
    if text is not None:
        command["dataItems"] = [{"type": "text", "text": text}]
    return command


@dataclass
class TaskRun:
    """Everything one live task produced, in a shape the analyzer can consume."""

    endpoint: str
    path_label: str
    task_id: str
    text: str
    started_at: str = ""
    states: list[tuple[float, str]] = field(default_factory=list)
    products: list[Any] = field(default_factory=list)
    error: Optional[str] = None
    terminal_state: str = ""
    t_start_ms: float = 0.0
    t_terminal_ms: float = 0.0
    polls: int = 0

    def as_row(self) -> dict[str, Any]:
        return {
            "path": self.path_label,
            "endpoint": self.endpoint,
            "task_id": self.task_id,
            "text_hash": __import__("hashlib").sha256(self.text.encode()).hexdigest()[:16],
            "started_at": self.started_at,
            "terminal_state": self.terminal_state,
            "states": [{"t_ms": round(t, 1), "state": s} for t, s in self.states],
            "polls": self.polls,
            "product_count": len(self.products),
            "t_start_ms": round(self.t_start_ms, 1),
            "t_terminal_ms": round(self.t_terminal_ms, 1),
            "error": self.error,
        }


class AipClient:
    def __init__(self, endpoint: str, sender_aic: str, context: Optional[ssl.SSLContext] = None,
                 timeout: float = 60.0) -> None:
        self.endpoint = endpoint
        self.sender_aic = sender_aic
        self.context = context or mtls_context()
        self.timeout = timeout

    def call(self, command: dict[str, Any]) -> dict[str, Any]:
        body = json.dumps({
            "jsonrpc": "2.0",
            "id": f"rpc-{uuid.uuid4()}",
            "method": "rpc",
            "params": {"command": command},
        }, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            self.endpoint, data=body,
            headers={"Content-Type": "application/json"}, method="POST",
        )
        with urllib.request.urlopen(request, context=self.context, timeout=self.timeout) as response:
            return json.loads(response.read().decode("utf-8"))

    @staticmethod
    def state_of(response: dict[str, Any]) -> str:
        return ((response.get("result") or {}).get("status") or {}).get("state", "")

    @staticmethod
    def products_of(response: dict[str, Any]) -> list[Any]:
        return (response.get("result") or {}).get("products") or []

    def run_task(self, text: str, path_label: str, poll_interval: float = 2.0,
                 max_wait: float = 180.0, complete_on_finish: bool = True) -> TaskRun:
        task_id = f"task-{path_label}-{uuid.uuid4()}"
        run = TaskRun(endpoint=self.endpoint, path_label=path_label, task_id=task_id, text=text)
        run.started_at = datetime.now(timezone.utc).isoformat()
        clock = time.monotonic()

        started = self.call(task_command(self.sender_aic, "start", task_id, text))
        if started.get("error"):
            run.error = json.dumps(started["error"], ensure_ascii=False)[:300]
            return run
        run.t_start_ms = (time.monotonic() - clock) * 1000
        state = self.state_of(started)
        run.states.append(((time.monotonic() - clock) * 1000, state))

        while (time.monotonic() - clock) < max_wait:
            if state in {"awaiting-completion", "completed", "failed", "rejected", "canceled"}:
                break
            time.sleep(poll_interval)
            run.polls += 1
            polled = self.call(task_command(self.sender_aic, "get", task_id))
            if polled.get("error"):
                run.error = json.dumps(polled["error"], ensure_ascii=False)[:300]
                break
            state = self.state_of(polled)
            run.states.append(((time.monotonic() - clock) * 1000, state))
            products = self.products_of(polled)
            if products:
                run.products = products
                break

        run.terminal_state = state
        run.t_terminal_ms = (time.monotonic() - clock) * 1000

        if complete_on_finish and state == "awaiting-completion":
            try:
                self.call(task_command(self.sender_aic, "complete", task_id))
            except Exception as error:  # noqa: BLE001 - completion is best effort in a pilot
                run.error = f"complete failed: {type(error).__name__}: {error}"[:300]
        return run


def probe_http(endpoint: str, context: Optional[ssl.SSLContext] = None, timeout: float = 10.0) -> dict[str, Any]:
    """GET the endpoint and return status plus the parsed body when it is JSON."""
    request = urllib.request.Request(endpoint, method="GET")
    try:
        with urllib.request.urlopen(request, context=context or mtls_context(), timeout=timeout) as response:
            raw = response.read().decode("utf-8", "replace")
            try:
                return {"status": response.status, "body": json.loads(raw)}
            except json.JSONDecodeError:
                return {"status": response.status, "body": raw[:200]}
    except urllib.error.HTTPError as error:
        return {"status": error.code, "body": error.read().decode("utf-8", "replace")[:200]}
