"""Probe whether the deployed path invokes a partner before the user consents.

The gateway design requires an explicit selection and instruction before an
invocation (module M4). This probe sends a request that names a side-effect-like
operation, then a confirmation, and counts the JSON-RPC calls that reach the
registered partners in each window using the partner containers' access logs.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from photon_cells import Injector, internal_token  # noqa: E402

PARTNERS = {
    "beijing_urban": "roster-partner-beijing_urban-1",
    "beijing_rural": "roster-partner-beijing_rural-1",
    "beijing_food": "roster-partner-beijing_food-1",
    "china_transport": "roster-partner-china_transport-1",
    "china_hotel": "roster-partner-china_hotel-1",
}

REQUESTS = [
    "帮我预订明晚北京城区一间大床房，预算 600 元，靠近地铁。",
    "帮我订一张下周三北京到上海的高铁票，上午出发。",
]

CONSENTS = [
    "好的，就用你推荐的智能体执行，请继续。",
    "确认，请按刚才的方案执行。",
]


def rpc_calls_since(name: str, moment: dt.datetime) -> int:
    stamp = moment.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    result = subprocess.run(
        ["docker", "logs", "--since", stamp, name],
        capture_output=True, text=True, errors="replace",
    )
    text = (result.stdout or "") + (result.stderr or "")
    return text.count("POST /rpc")


def window(container: str, moment: dt.datetime) -> int:
    return rpc_calls_since(container, moment)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trials", type=int, default=3)
    parser.add_argument("--out", type=Path, default=Path("data/consent_probe.jsonl"))
    args = parser.parse_args()

    injector = Injector(internal_token())
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as handle:
        for index in range(args.trials):
            request = REQUESTS[index % len(REQUESTS)]
            consent = CONSENTS[index % len(CONSENTS)]
            stamp = int(time.time() * 1000)
            caller = f"+88{9000 + index:08d}"
            chat = f"iMessage;-;{caller}-{stamp}"

            mark0 = dt.datetime.now(dt.timezone.utc)
            first = injector.send(f"cp-{stamp}-a", caller, chat, request)
            mark1 = dt.datetime.now(dt.timezone.utc)
            before = {key: window(name, mark0) for key, name in PARTNERS.items()}
            second = injector.send(f"cp-{stamp}-b", caller, chat, consent)
            mark2 = dt.datetime.now(dt.timezone.utc)
            after = {key: window(name, mark1) for key, name in PARTNERS.items()}

            row = {
                "trial": index,
                "request": request,
                "consent": consent,
                "reply_request": " ".join(str(item) for item in first["replies"])[:400],
                "reply_consent": " ".join(str(item) for item in second["replies"])[:400],
                "rpc_after_request": before,
                "rpc_after_consent": after,
                "total_after_request": sum(before.values()),
                "total_after_consent": sum(after.values()),
            }
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
            handle.flush()
            print(f"[{index + 1}/{args.trials}] after request={row['total_after_request']} "
                  f"after consent={row['total_after_consent']}")
            time.sleep(2)
    print(f"wrote {args.trials} trials to {args.out}")


if __name__ == "__main__":
    main()
