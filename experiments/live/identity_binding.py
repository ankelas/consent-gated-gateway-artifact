"""E1-I2: identity binding cell on the live AIP Partner path.

Fault model: the client certificate is the Leader's, and the declared
`senderId` is varied. The deployment binds `senderId` to the certificate
common name, so a mismatch must be rejected before any task is executed.

This cell needs no configuration change: the check is active even though
`identity_binding_enabled = false` in the demo configs, which is itself a
finding worth recording.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

from agents import AipClient, leader_aic, mtls_context, task_command


FORGED_AIC = "1.2.156.3088.1.BUPT.M7JQDT.FORGED.000000.0000"
OTHER_VALID_AIC = "1.2.156.3088.1.BUPT.M7JQDT.ARKM71.XYSD57.05HO"

FAULT_ARMS = {
    "other_valid_aic": OTHER_VALID_AIC,
    "forged_aic": FORGED_AIC,
    "empty_sender_id": "",
    "not_an_aic": "not-an-aic",
}

TEXTS = [
    "帮我推荐一家北京的酒店",
    "上海外滩附近有什么住宿推荐",
    "成都宽窄巷子附近的酒店",
]
AUTH_FAILURE_CODE = -32009


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--endpoint", default="https://127.0.0.1:9521/rpc")
    parser.add_argument("--n", type=int, default=30)
    parser.add_argument("--out", type=Path, default=Path("experiments/data/live_i2.jsonl"))
    args = parser.parse_args()

    leader = leader_aic()
    client = AipClient(args.endpoint, leader, mtls_context(), timeout=30.0)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []

    with args.out.open("w", encoding="utf-8") as handle:
        for index in range(args.n):
            item = f"I2-{index:03d}"
            text = TEXTS[index % len(TEXTS)]

            clock = time.monotonic()
            response = client.call(task_command(leader, "start", f"{item}-ctl", text))
            error = response.get("error") or {}
            rows.append({
                "cell": "I2", "item": item, "arm": "control",
                "sender_id": "certificate_cn", "accepted": not error,
                "error_code": error.get("code"), "error_message": error.get("message", "")[:60],
                "t_ms": (time.monotonic() - clock) * 1000,
            })

            for arm, sender in FAULT_ARMS.items():
                clock = time.monotonic()
                response = client.call(task_command(sender, "start", f"{item}-{arm}", text))
                error = response.get("error") or {}
                rows.append({
                    "cell": "I2", "item": item, "arm": arm,
                    "sender_id": sender[:40], "accepted": not error,
                    "error_code": error.get("code"), "error_message": error.get("message", "")[:60],
                    "t_ms": (time.monotonic() - clock) * 1000,
                })
            for row in rows[-5:]:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")
            handle.flush()
            accepted_faults = sum(1 for r in rows[-4:] if r["accepted"])
            print(f"[{index + 1}/{args.n}] control={'accept' if not rows[-5]['error_code'] else 'REJECT'} "
                  f"faults_accepted={accepted_faults}/4")

    print(f"wrote {len(rows)} rows to {args.out}")


if __name__ == "__main__":
    main()
