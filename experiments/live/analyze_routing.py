"""Final routing numbers, recomputed from the stored replies.

Selection is read from each stored reply with the line-scoped rule in
``run_live_samples.extract``; the count of recommended agents (any registry
agent) comes from ``run_live_samples.recommended_agents``. Recomputing from the
stored replies keeps the three deliveries comparable.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_live_samples import entry_from_roster, extract, recommended_agents  # noqa: E402

DEFAULT_ROSTER = Path("/data/caiyizhang/acps-public-demo/roster/roster.json")
DEFAULT_ACS = Path("/data/caiyizhang/acps-public-demo/roster/runtime")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--runs", type=int, nargs="+", default=[1, 2, 3])
    args = parser.parse_args()

    name_to_aic, _ = entry_from_roster(DEFAULT_ROSTER, DEFAULT_ACS)
    study_names = list(name_to_aic)
    summary = {}

    for run in args.runs:
        path = args.data / f"live_runs_v2_r{run}.jsonl"
        if not path.exists():
            continue
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        for row in rows:
            row["selected"] = extract(row["reply"], name_to_aic)[0]
            row["recommended"] = recommended_agents(row["reply"])
            row["target_hit"] = bool(row["target_aic"]) and row["target_aic"] in extract(row["reply"], name_to_aic)[1]

        by = {cls: [r for r in rows if r["class"] == cls] for cls in ("direct", "ambiguous", "out_of_scope")}
        direct = by["direct"]
        amb = by["ambiguous"]
        oos = by["out_of_scope"]
        counts = {
            "n": {k: len(v) for k, v in by.items()},
            "direct_hit": sum(1 for r in direct if r["target_hit"]),
            "direct_wrong_partner": sum(1 for r in direct if r["selected"] and not r["target_hit"]),
            "direct_no_study_partner": sum(1 for r in direct if not r["selected"]),
            "direct_other_only": sum(1 for r in direct
                                      if not r["selected"] and recommended_agents(r["reply"])),
            "amb_multi_any": sum(1 for r in amb if len(r["recommended"]) > 1),
            "amb_multi_study": sum(1 for r in amb if len(r["selected"]) > 1),
            "amb_clarify": sum(1 for r in amb if r.get("clarification")),
            "amb_empty": sum(1 for r in amb if not r["recommended"]),
            "oos_no_study_partner": sum(1 for r in oos if not r["selected"]),
            "oos_any_recommended": sum(1 for r in oos if r["recommended"]),
            "oos_empty": sum(1 for r in oos if not r["recommended"]),
        }
        summary[run] = counts
        print(f"run{run}: {json.dumps(counts, ensure_ascii=False)}")
        print(f"   direct per target: "
              f"{dict(Counter(r['target_name'] for r in direct if r['target_hit']))}")
        rate = counts["direct_hit"] / max(1, len(direct))
        print(f"   direct hit rate {rate:.1%}")

    # outcome stability per sample id
    if len([r for r in args.runs if (args.data / f'live_runs_v2_r{r}.jsonl').exists()]) > 1:
        outcomes: dict[str, dict[int, tuple]] = {}
        for run in args.runs:
            path = args.data / f"live_runs_v2_r{run}.jsonl"
            if not path.exists():
                continue
            for line in path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                row = json.loads(line)
                outcomes.setdefault(row["sample_id"], {})[run] = tuple(sorted(extract(row["reply"], name_to_aic)[0]))
        changed = {k: v for k, v in outcomes.items() if len(set(v.values())) > 1}
        print(f"outcome changed between deliveries: {len(changed)} "
              f"(direct {sum(1 for k in changed if k.startswith('direct'))})")

    out = args.data / "live_routing_summary_v2.json"
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
