"""Measure gateway-side handling cost separately from model generation.

Three gateway operations are timed on their own:

* ingress authentication, by posting with a wrong internal token (the request is
  rejected before any discovery or model call);
* the event-level deduplication lookup, by delivering the same message id twice
  and timing the second delivery (served from the store, no model call);
* the AIP identity check, by sending a task whose asserted sender does not match
  the client certificate (rejected by the partner before it generates anything).

For reference the same run records the first delivery of each pair, which
includes the assistant's own reply generation, and one normal AIP task, which
includes the partner's generation.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import photon_cells  # noqa: E402
from agents import AipClient, leader_aic, mtls_context, task_command  # noqa: E402
from photon_cells import Injector, internal_token  # noqa: E402

FORGED_AIC = "1.2.156.3088.1.BUPT.M7JQDT.FORGED.000000.0000"


def ingress_reject_latency(url: str, attempts: int) -> list[float]:
    times: list[float] = []
    payload = json.dumps({
        "message_id": "probe", "chat_guid": "probe", "text": "probe",
        "photon_sender_id": "+10000000000", "photon_sender_name": "probe",
    }).encode("utf-8")
    for _ in range(attempts):
        request = urllib.request.Request(
            url, data=payload,
            headers={"content-type": "application/json", "x-internal-token": "wrong-token"},
            method="POST",
        )
        clock = time.monotonic()
        try:
            with urllib.request.urlopen(request, timeout=30):
                pass
        except urllib.error.HTTPError:
            pass
        except Exception:  # noqa: BLE001
            pass
        times.append((time.monotonic() - clock) * 1000)
    return times


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--adapter", default="http://127.0.0.1:9420/v1/photon/inbound")
    parser.add_argument("--token", default="114514")
    parser.add_argument("--partner", default="https://127.0.0.1:9540/rpc")
    parser.add_argument("--pairs", type=int, default=20)
    parser.add_argument("--rejects", type=int, default=100)
    parser.add_argument("--identity", type=int, default=30)
    parser.add_argument("--samples", type=Path, default=Path("data/live_direct_samples.jsonl"))
    parser.add_argument("--out", type=Path, default=Path("data/live_gateway_overhead.json"))
    args = parser.parse_args()

    photon_cells.ADAPTER = args.adapter
    injector = Injector(args.token)
    samples = [json.loads(line) for line in args.samples.read_text(encoding="utf-8").splitlines() if line.strip()]

    results: dict[str, Any] = {}

    results["ingress_reject_ms"] = ingress_reject_latency(args.adapter, args.rejects)

    first: list[float] = []
    second: list[float] = []
    for index in range(args.pairs):
        sample = samples[index % len(samples)]
        stamp = int(time.time() * 1000)
        caller = f"+886000{index:05d}"
        chat = f"iMessage;-;{caller}-{stamp}"
        message_id = f"oh-{stamp}-{index}"
        clock = time.monotonic()
        injector.send(message_id, caller, chat, sample["text"])
        first.append((time.monotonic() - clock) * 1000)
        clock = time.monotonic()
        injector.send(message_id, caller, chat, sample["text"])
        second.append((time.monotonic() - clock) * 1000)
    results["first_delivery_ms"] = first
    results["dedup_hit_ms"] = second

    leader = leader_aic()
    client = AipClient(args.partner, leader, mtls_context(), timeout=60.0)
    rejects: list[float] = []
    accepted: list[float] = []
    for index in range(args.identity):
        text = samples[index % len(samples)]["text"]
        clock = time.monotonic()
        client.call(task_command(FORGED_AIC, "start", f"oh-bad-{uuid.uuid4()}", text))
        rejects.append((time.monotonic() - clock) * 1000)
        clock = time.monotonic()
        client.call(task_command(leader, "start", f"oh-ok-{uuid.uuid4()}", text))
        accepted.append((time.monotonic() - clock) * 1000)
    results["identity_reject_ms"] = rejects
    results["partner_task_ms"] = accepted

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")

    def p(values: list[float]) -> str:
        ordered = sorted(values)
        return (f"n={len(ordered)} p50={statistics.median(ordered):.2f} "
                f"p95={ordered[max(0, int(0.95 * len(ordered)) - 1)]:.2f}")

    for key in ("ingress_reject_ms", "dedup_hit_ms", "identity_reject_ms",
                "first_delivery_ms", "partner_task_ms"):
        print(f"{key:22s} {p(results[key])}")


if __name__ == "__main__":
    main()
