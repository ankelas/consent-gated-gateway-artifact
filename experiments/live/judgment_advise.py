"""Drive the J5 semantic-replay experiment through the deployed ingress.

Each conversation sends three events with fresh message ids: the request, a
paraphrase of it, and a different request in the same capability domain. The
gateway consults the typed judgment plane (JUDGMENT_MODE=advise) and logs the
verdict; this script drives the traffic and scores the log against the roles.

Nothing here depends on the judgment output: the verdict is advisory, so the
gateway's own decisions are unchanged and the routing/consent results stay
comparable.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import photon_cells  # noqa: E402
from photon_cells import Injector, internal_token  # noqa: E402

ROLES = (("base", "a"), ("paraphrase", "b"), ("different", "c"))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--samples", type=Path, default=Path("data/judgment_advise_samples.jsonl"))
    parser.add_argument("--out", type=Path, default=Path("data/judgment_advise_runs.jsonl"))
    parser.add_argument("--log", type=Path,
                        default=Path("/data/imessage/state/judgment_log.jsonl"))
    parser.add_argument("--threshold", type=float, default=0.9)
    parser.add_argument("--score-only", action="store_true")
    args = parser.parse_args()

    if not args.score_only:
        rows = [json.loads(line) for line in args.samples.read_text(encoding="utf-8").splitlines() if line.strip()]
        injector = Injector(internal_token())
        args.out.parent.mkdir(parents=True, exist_ok=True)
        # A run stamp keeps caller and message ids unique across reruns: a
        # repeated id would hit the event-level cache and the judgment plane
        # would not be consulted at all.
        run_stamp = int(time.time())
        with args.out.open("w", encoding="utf-8") as handle:
            for index, row in enumerate(rows, 1):
                stamp = int(time.time() * 1000)
                caller = f"+88{run_stamp % 100000:05d}{index:04d}"
                chat = f"iMessage;-;{caller}-{stamp}"
                for role, suffix in ROLES:
                    message_id = f"j5-{run_stamp}-{row['conversation']}-{suffix}"
                    result = injector.send(message_id, caller, chat, row[role])
                    record = {
                        "conversation": row["conversation"],
                        "role": role,
                        "message_id": message_id,
                        "text": row[role],
                        "reply_head": " ".join(str(item) for item in result["replies"])[:120],
                        "ingress_ms": round(result["t_ms"], 1),
                        "error": result["error"],
                    }
                    handle.write(json.dumps(record, ensure_ascii=False) + "\n")
                    handle.flush()
                    print(f"[{index}/{len(rows)}] {role:10s} ingress={record['ingress_ms']:8.1f} ms "
                          f"err={record['error']}", flush=True)
        print(f"wrote {args.out}")

    # ---- score against the adapter's own log -------------------------------
    log_lines = [json.loads(line) for line in args.log.read_text(encoding="utf-8").splitlines() if line.strip()]
    verdicts = {entry["message_id"]: entry for entry in log_lines if entry.get("message_id")}
    runs = [json.loads(line) for line in args.out.read_text(encoding="utf-8").splitlines() if line.strip()]

    per_role: dict[str, list[float]] = {role: [] for role, _ in ROLES}
    latencies: list[float] = []
    missing = 0
    errors = 0
    for run in runs:
        verdict = verdicts.get(run["message_id"])
        if not verdict or verdict.get("p_replay") is None:
            missing += 1
            errors += 1 if verdict and verdict.get("label") == "error" else 0
            continue
        per_role[run["role"]].append(float(verdict["p_replay"]))
        latencies.append(float(verdict["latency_ms"]))

    def rate(values: list[float], predicate) -> str:
        if not values:
            return "n/a"
        hits = sum(1 for value in values if predicate(value))
        return f"{hits}/{len(values)} ({hits / len(values):.1%})"

    print(f"\njudged events: {sum(len(v) for v in per_role.values())}/{len(runs)} "
          f"(missing {missing}, errors {errors})")
    for role, values in per_role.items():
        if not values:
            continue
        print(f"  {role:10s} p_replay mean={statistics.mean(values):.3f} "
              f"median={statistics.median(values):.3f} range={min(values):.3f}--{max(values):.3f} "
              f"| at >= {args.threshold}: {rate(values, lambda v: v >= args.threshold)}")
    if latencies:
        print(f"  judgment latency ms: median={statistics.median(latencies):.0f} "
              f"min={min(latencies):.0f} max={max(latencies):.0f}")
    print("\nsummary: sensitivity (paraphrases above threshold) = "
          f"{rate(per_role['paraphrase'], lambda v: v >= args.threshold)}; "
          f"specificity (different requests below threshold) = "
          f"{rate(per_role['different'], lambda v: v < args.threshold)}")
    all_values = [v for values in per_role.values() for v in values]
    print(f"fallback share (events handed to the keyed-result branch) = "
          f"{rate(all_values, lambda v: v >= args.threshold)}")


if __name__ == "__main__":
    main()
