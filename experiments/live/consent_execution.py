"""Consent -> execution test on the live adapter.

Each trial sends a request that the assistant answers with a candidate list,
counts the JSON-RPC calls that reach the registered partners, then sends the
adapter's explicit consent form ("use candidate 1: <instruction>") and counts
again. The first count tests that nothing is invoked without consent; the
second tests that consent produces an invocation.

Only the partner containers' access logs are read; no outbound message is
produced because the adapter returns its reply as JSON.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import photon_cells  # noqa: E402
from photon_cells import Injector, internal_token  # noqa: E402

CONTAINERS = {
    "beijing_urban": "roster-partner-beijing_urban-1",
    "beijing_rural": "roster-partner-beijing_rural-1",
    "beijing_food": "roster-partner-beijing_food-1",
    "china_transport": "roster-partner-china_transport-1",
    "china_hotel": "roster-partner-china_hotel-1",
}
AIC_PREFIX = "1.2.156.3088.1.BUPT.M7JQDT."
INSTRUCTIONS = [
    "请根据以上需求给出两天的具体行程安排。",
    "请按刚才的需求直接给出结果。",
]


def wait_for_rpc(mark: dt.datetime, timeout: float, poll: float = 2.0) -> dict[str, int]:
    """Poll the partner logs until an RPC appears or the timeout expires."""
    deadline = time.monotonic() + timeout
    counts = rpc_since(mark)
    while sum(counts.values()) == 0 and time.monotonic() < deadline:
        time.sleep(poll)
        counts = rpc_since(mark)
    return counts


def rpc_since(moment: dt.datetime) -> dict[str, int]:
    stamp = moment.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    out = {}
    for key, name in CONTAINERS.items():
        result = subprocess.run(["docker", "logs", "--since", stamp, name],
                                capture_output=True, text=True, errors="replace")
        text = (result.stdout or "") + (result.stderr or "")
        out[key] = text.count("POST /rpc")
    return out


def effect_since(moment: dt.datetime, path: str) -> dict[str, int]:
    """Count partner-side action records newer than the mark."""
    total = 0
    try:
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            record = json.loads(line)
            if record.get("at", 0) >= moment.timestamp():
                total += 1
    except FileNotFoundError:
        return {"effect": 0}
    return {"effect": total}


def count_since(moment: dt.datetime, effect_log: str | None) -> dict[str, int]:
    return effect_since(moment, effect_log) if effect_log else rpc_since(moment)


def wait_for_count(mark: dt.datetime, timeout: float, effect_log: str | None,
                   poll: float = 2.0) -> dict[str, int]:
    deadline = time.monotonic() + timeout
    counts = count_since(mark, effect_log)
    while sum(counts.values()) == 0 and time.monotonic() < deadline:
        time.sleep(poll)
        counts = count_since(mark, effect_log)
    return counts


def first_aic(reply: str) -> str | None:
    match = re.search(r"AIC[：:]\s*([0-9A-Za-z.]+)", reply)
    return match.group(1) if match else None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trials", type=int, default=30)
    parser.add_argument("--wait", type=float, default=25.0, help="seconds to wait after consent")
    parser.add_argument("--adapter", default=None, help="adapter inbound URL (defaults to the live adapter)")
    parser.add_argument("--token", default=None, help="internal token (defaults to the live adapter's)")
    parser.add_argument("--effect-log", default=None,
                        help="count lines in this file (partner side effect) instead of partner RPCs")
    parser.add_argument("--samples", type=Path, default=Path("data/live_direct_samples.jsonl"))
    parser.add_argument("--out", type=Path, default=Path("data/live_consent_execution.jsonl"))
    args = parser.parse_args()

    samples = [json.loads(line) for line in args.samples.read_text(encoding="utf-8").splitlines() if line.strip()]
    injector = Injector(args.token or internal_token())
    if args.adapter:
        photon_cells.ADAPTER = args.adapter
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as handle:
        for index in range(args.trials):
            sample = samples[index % len(samples)]
            stamp = int(time.time() * 1000)
            caller = f"+88{7000 + index:08d}"
            chat = f"iMessage;-;{caller}-{stamp}"

            mark0 = dt.datetime.now(dt.timezone.utc)
            first = injector.send(f"ce-{stamp}-a", caller, chat, sample["text"])
            reply1 = " ".join(str(item) for item in first["replies"])
            mark1 = dt.datetime.now(dt.timezone.utc)
            before = count_since(mark0, args.effect_log)

            candidate_aic = first_aic(reply1)
            mine = bool(candidate_aic and candidate_aic.startswith(AIC_PREFIX))
            # Give the partner the request itself, so the instruction carries
            # the context the downstream agent needs to answer.
            consent_text = f"使用 1：{sample['text']}"
            second = injector.send(f"ce-{stamp}-b", caller, chat, consent_text)
            reply2 = " ".join(str(item) for item in second["replies"])
            mark2 = dt.datetime.now(dt.timezone.utc)
            after = wait_for_count(mark1, args.wait, args.effect_log)

            row = {
                "trial": index,
                "sample": sample["sample_id"],
                "request": sample["text"],
                "consent": consent_text,
                "first_candidate_is_registered_partner": mine,
                "rpc_after_request": before,
                "rpc_after_consent": after,
                "total_after_request": sum(before.values()),
                "total_after_consent": sum(after.values()),
                "reply_request": reply1[:300],
                "reply_consent": reply2[:300],
            }
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
            handle.flush()
            print(f"[{index + 1}/{args.trials}] mine={mine} rpc_before={row['total_after_request']} "
                  f"rpc_after={row['total_after_consent']}")
    print(f"wrote {args.trials} trials to {args.out}")


if __name__ == "__main__":
    main()
