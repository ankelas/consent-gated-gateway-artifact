"""Run a live pilot or confirmatory block with hard safety guards.

Guards
------
* If the message set contains side-effecting cards and the destination is the
  iMessage path, the runner inspects the live `imessage-sender` container. It
  refuses to run unless the sender reports `SENDER_DRY_RUN=true`, or the caller
  passes `--allow-real-send` explicitly.
* A stop file aborts the run before the next task.
* Every attempt is written as one JSON line with the card label attached.

Example (local demo, no side effects):

    python3 experiments/live/run_live.py --path P1_leader \
        --endpoint https://127.0.0.1:9520/api/v1 \
        --suite experiments/data/live_suite.jsonl \
        --out experiments/data/live_telemetry.jsonl --dry-run
"""

from __future__ import annotations

import argparse
import json
import subprocess
import time
from pathlib import Path

from agents import AipClient, leader_aic, mtls_context
from leader_rest import LeaderRestClient


def sender_dry_run() -> str:
    out = subprocess.run(
        ["docker", "inspect", "imessage-sender", "--format",
         "{{range .Config.Env}}{{println .}}{{end}}"],
        capture_output=True, text=True,
    ).stdout
    for line in out.splitlines():
        if line.startswith("SENDER_DRY_RUN="):
            return line.split("=", 1)[1].strip().lower()
    return ""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--path", required=True,
                        choices=("P1_leader", "P3_imessage", "P4_group"))
    parser.add_argument("--endpoint", required=True)
    parser.add_argument("--protocol", choices=("leader-rest", "aip"), default="leader-rest")
    parser.add_argument("--suite", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--max-wait", type=float, default=180.0)
    parser.add_argument("--poll-interval", type=float, default=2.0)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--allow-real-send", action="store_true")
    parser.add_argument("--stop-file", type=Path, default=Path("/tmp/live_stop"))
    args = parser.parse_args()

    items = [json.loads(line) for line in args.suite.read_text(encoding="utf-8").splitlines() if line.strip()]
    if args.limit:
        items = items[:args.limit]
    side_effecting = [item for item in items if item.get("side_effect")]

    # Any path can route a side-effecting card to the forwarding Partner, so the
    # dry-run guard is path-independent rather than scoped to the iMessage path.
    if side_effecting:
        flag = sender_dry_run()
        if flag not in {"1", "true", "yes", "on"}:
            if not args.allow_real_send:
                raise SystemExit(
                    "refusing to run: imessage-sender is not in dry-run mode "
                    f"(SENDER_DRY_RUN={flag or 'unset'}) and {len(side_effecting)} messages "
                    "have side effects. Set the sender to dry-run, or pass --allow-real-send."
                )
            print("WARNING: real sends are enabled and explicitly authorised")

    context = mtls_context()
    client = (LeaderRestClient(args.endpoint, context) if args.protocol == "leader-rest"
              else AipClient(args.endpoint, args.aic if hasattr(args, "aic") else leader_aic(), context))

    args.out.parent.mkdir(parents=True, exist_ok=True)
    completed = 0
    with args.out.open("a", encoding="utf-8") as handle:
        for index, item in enumerate(items, 1):
            if args.stop_file.exists():
                print(f"stop file {args.stop_file} present; aborting after {completed} tasks")
                break
            try:
                run = client.run_task(item["text"], args.path,
                                      poll_interval=args.poll_interval, max_wait=args.max_wait)
                row = {**item, **run.as_row(),
                       "run_id": f"{args.path}-{int(time.time())}", "dry_run": bool(args.dry_run)}
            except Exception as error:  # noqa: BLE001 - one bad task must not kill the block
                row = {**item, "path": args.path, "error": f"{type(error).__name__}: {error}"[:300],
                       "run_id": f"{args.path}-{int(time.time())}", "dry_run": bool(args.dry_run)}
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
            handle.flush()
            completed += 1
            print(f"[{index}/{len(items)}] {item['card_id']} {item['family']:14s} "
                  f"state={row.get('terminal_state','-')} t={row.get('t_terminal_ms',0):.0f}ms "
                  f"products={row.get('product_count',0)}")
    print(f"wrote {completed} rows to {args.out}")


if __name__ == "__main__":
    main()
