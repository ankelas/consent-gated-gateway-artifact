"""Synthetic-ingress cells on the real gateway: I4 idempotency, I5 isolation.

The adapter's inbound endpoint is driven directly with an internal token, so
the whole gateway pipeline executes (authentication, caller derivation, session
partition, discovery, Partner routing, reply generation) while the reply comes
back as JSON instead of being sent. Nothing leaves the host.

Only non-side-effecting request text is used, so no cell can reach the
forwarding Partner and the iMessage sender.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


ADAPTER = "http://127.0.0.1:9410/v1/photon/inbound"
CALLER_A = "+11111111111"
CALLER_B = "+22222222222"
DB = "/data/imessage/state/imessage.sqlite3"
REQUESTS = [
    "推荐北京故宫附近、靠近地铁、每晚 600 到 1000 元的酒店",
    "帮我找上海外滩周边的住宿，预算每晚 400-1000 元",
    "成都宽窄巷子附近有什么酒店推荐",
]
FOLLOW_UP = "选择第一个方案并执行"

# A second caller with no state may still run its own discovery and recommend a
# generic capability; that is not a leak. The objective signal is whether the
# second caller's reply carries the *first* caller's unique marker, which only
# a cross-context read can produce. Two earlier lexical rules were rejected
# after inspection: they fired on independent discovery.


def internal_token(container: str = "imessage-agent-1") -> str:
    out = subprocess.run(
        ["docker", "inspect", container, "--format", "{{range .Config.Env}}{{println .}}{{end}}"],
        capture_output=True, text=True,
    ).stdout
    for line in out.splitlines():
        if line.startswith("INTERNAL_TOKEN="):
            return line.split("=", 1)[1].strip()
    raise SystemExit("INTERNAL_TOKEN not found in the adapter container")


def stored_event_rows(caller: str, message_id: str) -> int:
    """Ground truth for event idempotency: rows for one (caller, message id).

    The adapter normalizes the caller to ``photon:<sender id>`` before writing,
    so the lookup has to use the normalized key.
    """
    import sqlite3
    normalized = caller if caller.startswith("photon:") else f"photon:{caller}"
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    count = con.execute(
        "select count(*) from inbound_events_v2 where caller_id=? and message_id=?",
        (normalized, message_id),
    ).fetchone()[0]
    con.close()
    return count


class Injector:
    def __init__(self, token: str, timeout: float = 90.0) -> None:
        self.token = token
        self.timeout = timeout

    def send(self, message_id: str, caller: str, chat: str, text: str) -> dict[str, Any]:
        payload = {
            "message_id": message_id, "chat_guid": chat, "text": text,
            "photon_sender_id": caller, "photon_sender_name": "live-test",
        }
        request = urllib.request.Request(
            ADAPTER, data=json.dumps(payload).encode("utf-8"),
            headers={"content-type": "application/json", "x-internal-token": self.token},
            method="POST",
        )
        clock = time.monotonic()
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                body = json.loads(response.read().decode("utf-8"))
            return {"status": response.status, "t_ms": (time.monotonic() - clock) * 1000,
                    "replies": body.get("messages") or [], "error": None}
        except urllib.error.HTTPError as error:
            return {"status": error.code, "t_ms": (time.monotonic() - clock) * 1000,
                    "replies": [], "error": error.read().decode("utf-8", "replace")[:160]}
        except Exception as error:  # noqa: BLE001
            return {"status": None, "t_ms": (time.monotonic() - clock) * 1000,
                    "replies": [], "error": f"{type(error).__name__}: {error}"[:160]}


def run_idempotency(injector: Injector, n: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index in range(n):
        stamp = int(time.time() * 1000)
        # A fresh caller and conversation per item: the adapter caches a reply
        # per conversation, so reusing one would mask event-level behaviour.
        caller = f"+11{index:08d}"
        chat = f"iMessage;-;{caller}"
        text = f"{REQUESTS[index % len(REQUESTS)]}（测试编号 {stamp}-{index}）"
        # Control pair: two different event ids must both be processed.
        fresh_1 = injector.send(f"I4-{stamp}-a1", caller, chat, text)
        fresh_2 = injector.send(f"I4-{stamp}-a2", caller, chat, f"{text} 二")
        # Fault pair: the same event id delivered twice.
        replay_id = f"I4-{stamp}-r"
        first = injector.send(replay_id, caller, chat, text)
        second = injector.send(replay_id, caller, chat, text)
        identical = (first["replies"] == second["replies"]) and bool(first["replies"])
        stored = stored_event_rows(caller, replay_id)
        rows.append({
            "cell": "I4", "item": f"I4-{index:03d}",
            "fresh_t_ms": fresh_2["t_ms"], "replay_first_t_ms": first["t_ms"],
            "replay_second_t_ms": second["t_ms"], "identical_reply": identical,
            "stored_rows_for_key": stored,
            "duplicate_execution": stored != 1,
            "fresh_distinct": fresh_1["replies"] != fresh_2["replies"],
        })
        print(f"[{index + 1}/{n}] fresh={fresh_2['t_ms']:.0f}ms "
              f"replay={first['t_ms']:.0f}ms->{second['t_ms']:.0f}ms stored_rows={stored}")
    return rows


def run_isolation(injector: Injector, n: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index in range(n):
        stamp = int(time.time() * 1000)
        caller_a = f"+11{index:08d}"
        caller_b = f"+22{index:08d}"
        chat_a, chat_b = f"iMessage;-;{caller_a}", f"iMessage;-;{caller_b}"
        marker = f"ZQXMARK{stamp}X{index}"
        text = f"{REQUESTS[index % len(REQUESTS)]}（{marker}）"
        injector.send(f"I5-{stamp}-setup", caller_a, chat_a, text)
        # Control: the same caller continues its own session.
        control = injector.send(f"I5-{stamp}-ctl", caller_a, chat_a, FOLLOW_UP)
        # Fault: a different caller references the first caller's pending state.
        fault = injector.send(f"I5-{stamp}-b", caller_b, chat_b, FOLLOW_UP)
        control_text = " ".join(str(r) for r in control["replies"])
        fault_text = " ".join(str(r) for r in fault["replies"])
        leaked = marker in fault_text
        fault_blocked = not leaked
        rows.append({
            "cell": "I5", "item": f"I5-{index:03d}",
            "control_has_context": marker in control_text,
            "fault_blocked": fault_blocked, "cross_context_access": leaked,
            "fault_reply_hash": __import__("hashlib").sha256(fault_text.encode()).hexdigest()[:16],
            "fault_reply_head": fault_text[:120],
            "fault_t_ms": fault["t_ms"],
        })
        print(f"[{index + 1}/{n}] control_context={rows[-1]['control_has_context']} "
              f"fault_blocked={fault_blocked}")
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cell", choices=("I4", "I5"), required=True)
    parser.add_argument("--n", type=int, default=30)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    injector = Injector(internal_token())
    rows = run_idempotency(injector, args.n) if args.cell == "I4" else run_isolation(injector, args.n)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"wrote {len(rows)} rows to {args.out}")


if __name__ == "__main__":
    main()
