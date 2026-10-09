"""Create publication-friendly aggregate tables from simulator records."""

from __future__ import annotations

import argparse
import csv
import math
from collections import defaultdict
from pathlib import Path


METRICS = (
    "task_success", "correct_delegation", "safe_rejection", "unauthorized_call",
    "identity_bypass", "cross_session_leak", "duplicate_side_effect", "recovered",
    "clarification_requested",
)


def as_bool(value: str) -> bool:
    return value.lower() == "true"


def wilson(successes: int, total: int, z: float = 1.959963984540054) -> tuple[float, float, float]:
    if total == 0:
        return 0.0, 0.0, 0.0
    p = successes / total
    denominator = 1.0 + z * z / total
    center = (p + z * z / (2 * total)) / denominator
    half = z * math.sqrt((p * (1 - p) + z * z / (4 * total)) / total) / denominator
    return p, max(0.0, center - half), min(1.0, center + half)


def percentile(values: list[float], fraction: float) -> float:
    values = sorted(values)
    if not values:
        return 0.0
    index = min(len(values) - 1, max(0, math.ceil(fraction * len(values)) - 1))
    return values[index]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    groups = defaultdict(list)
    with args.input.open(encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            groups[(row["fault"], row["variant"])].append(row)

    fields = ["fault", "variant", "n"]
    for metric in METRICS:
        fields.extend([f"{metric}_rate", f"{metric}_lo95", f"{metric}_hi95"])
    fields.extend(["mean_latency_ms", "p50_latency_ms", "p95_latency_ms", "mean_message_bytes"])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for (fault, variant), rows in sorted(groups.items()):
            values = {"fault": fault, "variant": variant, "n": len(rows)}
            for metric in METRICS:
                successes = sum(as_bool(row[metric]) for row in rows)
                rate, lo, hi = wilson(successes, len(rows))
                values[f"{metric}_rate"] = f"{rate:.6f}"
                values[f"{metric}_lo95"] = f"{lo:.6f}"
                values[f"{metric}_hi95"] = f"{hi:.6f}"
            latencies = [float(row["latency_ms"]) for row in rows]
            values["mean_latency_ms"] = f"{sum(latencies) / len(latencies):.3f}"
            values["p50_latency_ms"] = f"{percentile(latencies, 0.50):.3f}"
            values["p95_latency_ms"] = f"{percentile(latencies, 0.95):.3f}"
            values["mean_message_bytes"] = f"{sum(int(row['message_bytes']) for row in rows) / len(rows):.3f}"
            writer.writerow(values)
    print(f"wrote {len(groups)} aggregate rows to {args.output}")


if __name__ == "__main__":
    main()
