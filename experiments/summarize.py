"""Summarize pilot records without external dependencies."""

from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from pathlib import Path


BOOLEAN_METRICS = (
    "task_success", "correct_delegation", "safe_rejection", "unauthorized_call",
    "identity_bypass", "cross_session_leak", "duplicate_side_effect", "recovered",
)


def as_bool(value: str) -> bool:
    return value.lower() == "true"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    args = parser.parse_args()
    groups = defaultdict(list)
    with args.input.open(encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            groups[(row["fault"], row["variant"])].append(row)

    print("fault,variant,n," + ",".join(BOOLEAN_METRICS) + ",mean_latency_ms,p95_latency_ms")
    for (fault, variant), rows in sorted(groups.items()):
        n = len(rows)
        values = []
        for metric in BOOLEAN_METRICS:
            values.append(f"{sum(as_bool(r[metric]) for r in rows) / n:.3f}")
        latencies = sorted(float(r["latency_ms"]) for r in rows)
        p95 = latencies[min(n - 1, int(0.95 * n))]
        print(f"{fault},{variant},{n}," + ",".join(values) + f",{sum(latencies) / n:.3f},{p95:.3f}")


if __name__ == "__main__":
    main()

