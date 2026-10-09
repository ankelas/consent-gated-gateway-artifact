"""E1-I1: ingress integrity cell.

On the demo Leader (P1) there is no HMAC webhook check -- that lives in the
Photon bridge on the real ingress. So the faults that actually exist at this
entry point are transport and request-validation faults:

* no client certificate      -> rejected by the mTLS edge (nginx 400)
* malformed JSON body        -> rejected by request validation (422)
* missing required fields    -> rejected by request validation (422)
* unknown session reference  -> rejected by the application (404)

Each item runs one clean control and the four faults, and the runner records
whether a session was created on the fault side. Rejections must happen before
any session or task exists.
"""

from __future__ import annotations

import argparse
import json
import ssl
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Optional

from agents import mtls_context
from leader_rest import LeaderRestClient


FAULTS = {
    "no_client_cert": {"expect": {400}, "channel": "mtls_edge"},
    "bad_json": {"expect": {422}, "channel": "request_validation"},
    "missing_fields": {"expect": {422}, "channel": "request_validation"},
    "unknown_session": {"expect": {404}, "channel": "application"},
}

DEFAULT_TEXTS = [
    "推荐北京故宫附近、靠近地铁、每晚 600 到 1000 元的酒店",
    "帮我找上海外滩周边的住宿，预算每晚 400-1000 元",
    "计划去成都玩，住在宽窄巷子附近，800 到 1200 元一晚有什么推荐",
]


def raw_call(base: str, path: str, method: str = "POST", payload: Optional[bytes] = None,
             with_cert: bool = True, timeout: float = 20.0) -> tuple[Optional[int], str]:
    context = mtls_context() if with_cert else ssl._create_unverified_context()
    request = urllib.request.Request(
        f"{base}{path}", data=payload,
        headers={"Content-Type": "application/json"}, method=method,
    )
    try:
        with urllib.request.urlopen(request, context=context, timeout=timeout) as response:
            return response.status, response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode("utf-8", "replace")
    except Exception as error:  # noqa: BLE001 - recorded as an observation
        return None, f"{type(error).__name__}: {error}"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--endpoint", default="https://127.0.0.1:9520/api/v1")
    parser.add_argument("--n", type=int, default=30)
    parser.add_argument("--out", type=Path, default=Path("experiments/data/live_i1.jsonl"))
    args = parser.parse_args()

    client = LeaderRestClient(args.endpoint, mtls_context())
    rows: list[dict[str, Any]] = []
    args.out.parent.mkdir(parents=True, exist_ok=True)

    with args.out.open("w", encoding="utf-8") as handle:
        for index in range(args.n):
            text = DEFAULT_TEXTS[index % len(DEFAULT_TEXTS)]
            item = f"I1-{index:03d}"
            body = json.dumps({"query": text, "clientRequestId": f"{item}-ctl"}).encode()

            clock = time.monotonic()
            run = client.run_task(text, "P1_I1_control",
                                  client_request_id=f"{item}-ctl", poll_interval=1.0, max_wait=60.0)
            control = {
                "cell": "I1", "item": item, "arm": "control", "expected": [200],
                "status": 200 if run.products else None,
                "channel": "application" if run.products else "no_convergence",
                "session_created": bool(run.products),
                "terminal_state": run.terminal_state,
                "t_ms": run.t_terminal_ms,
            }
            rows.append(control)

            faults = {
                "no_client_cert": dict(path="/submit", payload=body, with_cert=False),
                "bad_json": dict(path="/submit", payload=b"{not json"),
                "missing_fields": dict(path="/submit", payload=b"{}"),
                "unknown_session": dict(path=f"/result/sess_missing_{item}", method="GET"),
            }
            for arm, spec in faults.items():
                started = time.monotonic()
                status, response = raw_call(
                    args.endpoint, spec["path"], spec.get("method", "POST"),
                    spec.get("payload"), spec.get("with_cert", True),
                )
                rows.append({
                    "cell": "I1", "item": item, "arm": arm,
                    "expected": sorted(FAULTS[arm]["expect"]),
                    "status": status, "channel": FAULTS[arm]["channel"],
                    "session_created": "sessionId" in response,
                    "terminal_state": "", "t_ms": (time.monotonic() - started) * 1000,
                    "response_head": response[:120],
                })
            for row in rows[-5:]:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")
            handle.flush()
            print(f"[{index + 1}/{args.n}] control={'ok' if control['session_created'] else 'FAIL'} "
                  + " ".join(f"{a}={r['status']}" for a, r in
                             zip(faults, rows[-4:])))

    print(f"wrote {len(rows)} rows to {args.out}")


if __name__ == "__main__":
    main()
