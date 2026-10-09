"""Drive one live task and record structured telemetry.

Two protocols are supported:

* ``leader-rest`` — the Leader Agent Platform REST flow
  (``POST /api/v1/submit`` then ``GET /api/v1/result/{session_id}``);
* ``aip`` — the AIP JSON-RPC task-command flow used by a Partner endpoint.

Example (local deterministic demo, no external side effects):

    python3 experiments/live/drive_task.py \
        --protocol leader-rest --endpoint https://127.0.0.1:9520/api/v1 \
        --path-label P1_demo --text "推荐北京故宫附近、靠近地铁的酒店" \
        --out /tmp/live_task.jsonl
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from agents import AipClient, leader_aic, mtls_context
from leader_rest import LeaderRestClient


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--protocol", choices=("leader-rest", "aip"), default="leader-rest")
    parser.add_argument("--endpoint", default="https://127.0.0.1:9520/api/v1",
                        help="base URL (leader-rest) or JSON-RPC URL (aip), over mTLS")
    parser.add_argument("--aic", default=None, help="sender AIC; defaults to /tmp/leader_aic.txt")
    parser.add_argument("--path-label", default="P1_demo")
    parser.add_argument("--text", required=True)
    parser.add_argument("--max-wait", type=float, default=180.0)
    parser.add_argument("--poll-interval", type=float, default=2.0)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()

    context = mtls_context()
    if args.protocol == "leader-rest":
        client = LeaderRestClient(args.endpoint, context)
        run = client.run_task(args.text, args.path_label,
                              poll_interval=args.poll_interval, max_wait=args.max_wait)
    else:
        client = AipClient(args.endpoint, args.aic or leader_aic(), context)
        run = client.run_task(args.text, args.path_label,
                              poll_interval=args.poll_interval, max_wait=args.max_wait)
    row = run.as_row()
    print(json.dumps(row, ensure_ascii=False, indent=2))
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        with args.out.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
