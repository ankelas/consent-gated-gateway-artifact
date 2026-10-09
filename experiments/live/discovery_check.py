"""Structured discovery ranking for the generated request suite.

The adapter reads user-selectable candidates from the Discovery Agent's
structured Product. This script queries the same public discovery endpoint
directly with each generated request and records the ranking, so the reply
extraction can be cross-checked against the structured instrument.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from pathlib import Path

ENDPOINT = "https://wt.ioa.pub/discovery/acps-adp-v2/discover"


def discover(text: str, limit: int = 10) -> tuple[list[str], int]:
    body = json.dumps({"query": text, "limit": limit}).encode()
    request = urllib.request.Request(
        ENDPOINT, data=body, headers={"Content-Type": "application/json"}, method="POST"
    )
    payload = json.loads(urllib.request.urlopen(request, timeout=30).read().decode())
    result = payload.get("result") or {}
    ranked: list[str] = []
    for group in result.get("agents") or []:
        for skill in group.get("agentSkills") or []:
            ranked.append(skill.get("aic"))
        if ranked:
            break
    return ranked[:3], len(ranked)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--samples", type=Path, default=Path("data/live_samples_v2.jsonl"))
    parser.add_argument("--out", type=Path, default=Path("data/live_discovery_check_v2.jsonl"))
    args = parser.parse_args()

    samples = [json.loads(line) for line in args.samples.read_text(encoding="utf-8").splitlines() if line.strip()]
    rows = []
    for index, sample in enumerate(samples, 1):
        try:
            top3, n_returned = discover(sample["text"])
            row = {**sample, "top3": top3, "top1": top3[0] if top3 else None, "n_returned": n_returned}
        except Exception as error:  # noqa: BLE001 - record and continue
            row = {**sample, "top3": [], "top1": None, "n_returned": 0, "error": str(error)[:80]}
        rows.append(row)
        print(f"[{index}/{len(samples)}] {sample['class']:13s} top1_hit={row['top1'] == sample['target_aic']}")
        sys.stdout.flush()

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    direct = [r for r in rows if r["class"] == "direct"]
    hit1 = sum(1 for r in direct if r["top1"] == r["target_aic"])
    hit3 = sum(1 for r in direct if r["target_aic"] in r["top3"])
    oos = [r for r in rows if r["class"] == "out_of_scope"]
    print(f"direct n={len(direct)} top1={hit1} ({hit1 / max(1, len(direct)):.1%}) "
          f"top3={hit3} ({hit3 / max(1, len(direct)):.1%})")
    print(f"out_of_scope n={len(oos)} returned_candidate={sum(1 for r in oos if r['n_returned'])}")
    print(f"wrote {len(rows)} rows to {args.out}")


if __name__ == "__main__":
    main()
