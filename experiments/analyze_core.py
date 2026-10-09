"""Aggregate paired core-experiment outcomes and arm contrasts."""

from __future__ import annotations

import argparse
import csv
import math
from collections import defaultdict
from pathlib import Path


ARMS = ("B1_auto_discovery", "B2_no_identity", "B3_no_consent", "B4_no_isolation_dedup", "Full")
METRICS = (
    "task_success", "correct_delegation", "safe_rejection", "unauthorized_call",
    "identity_bypass", "cross_session_leak", "duplicate_side_effect", "recovered",
    "clarification_requested", "rejected",
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
    parser.add_argument("input", type=Path, default=Path("data/core_results.csv"), nargs="?")
    parser.add_argument("--summary", type=Path, default=Path("data/core_summary.csv"))
    parser.add_argument("--contrasts", type=Path, default=Path("data/core_contrasts.csv"))
    args = parser.parse_args()

    groups: dict[tuple[str, str, str], list[dict[str, str]]] = defaultdict(list)
    with args.input.open(encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            groups[(row["fault"], row["category"], row["variant"])].append(row)

    summary_fields = ["fault", "category", "variant", "n"]
    for metric in METRICS:
        summary_fields.extend([f"{metric}_rate", f"{metric}_lo95", f"{metric}_hi95"])
    summary_fields.extend(["mean_latency_ms", "p50_latency_ms", "p95_latency_ms"])
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    with args.summary.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=summary_fields)
        writer.writeheader()
        for (fault, category, variant), rows in sorted(groups.items()):
            values: dict[str, object] = {"fault": fault, "category": category, "variant": variant, "n": len(rows)}
            for metric in METRICS:
                rate, lo, hi = wilson(sum(as_bool(row[metric]) for row in rows), len(rows))
                values[f"{metric}_rate"] = f"{rate:.6f}"
                values[f"{metric}_lo95"] = f"{lo:.6f}"
                values[f"{metric}_hi95"] = f"{hi:.6f}"
            latencies = [float(row["latency_ms"]) for row in rows]
            values["mean_latency_ms"] = f"{sum(latencies) / len(latencies):.3f}"
            values["p50_latency_ms"] = f"{percentile(latencies, 0.50):.3f}"
            values["p95_latency_ms"] = f"{percentile(latencies, 0.95):.3f}"
            writer.writerow(values)

    by_pair: dict[str, dict[str, dict[str, str]]] = defaultdict(dict)
    with args.input.open(encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            by_pair[row["pair_id"]][row["variant"]] = row
    contrast_fields = ["fault", "category", "metric", "full_rate", "arm_rate", "rate_difference", "paired_full_failures", "paired_arm_failures", "n"]
    with args.contrasts.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=contrast_fields)
        writer.writeheader()
        for arm in ARMS[:-1]:
            for metric in METRICS:
                cells: dict[tuple[str, str], list[tuple[bool, bool]]] = defaultdict(list)
                for pair in by_pair.values():
                    if arm not in pair or "Full" not in pair:
                        continue
                    left, right = pair["Full"], pair[arm]
                    cells[(left["fault"], left["category"])].append((as_bool(left[metric]), as_bool(right[metric])))
                for (fault, category), pairs in sorted(cells.items()):
                    n = len(pairs)
                    full_rate = sum(left for left, _ in pairs) / n
                    arm_rate = sum(right for _, right in pairs) / n
                    writer.writerow({
                        "fault": fault, "category": category, "metric": f"{arm}:{metric}",
                        "full_rate": f"{full_rate:.6f}", "arm_rate": f"{arm_rate:.6f}",
                        "rate_difference": f"{arm_rate - full_rate:.6f}",
                        "paired_full_failures": sum(not left for left, _ in pairs),
                        "paired_arm_failures": sum(not right for _, right in pairs),
                        "n": n,
                    })
    print(f"wrote summary to {args.summary} and contrasts to {args.contrasts}")


if __name__ == "__main__":
    main()
