"""Summarize live telemetry: rates with Wilson intervals and latency percentiles."""

from __future__ import annotations

import argparse
import csv
import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any


def wilson(successes: int, total: int, z: float = 1.959963984540054) -> tuple[float, float, float]:
    if total == 0:
        return 0.0, 0.0, 0.0
    p = successes / total
    denominator = 1.0 + z * z / total
    center = (p + z * z / (2 * total)) / denominator
    half = z * math.sqrt((p * (1 - p) + z * z / (4 * total)) / total) / denominator
    return p, max(0.0, center - half), min(1.0, center + half)


def upper_bound_zero(total: int) -> float:
    """One-sided 95% upper bound for a zero-event count, approximately 3/N."""
    return 3.0 / total if total else float("nan")


def percentile(values: list[float], fraction: float) -> float:
    if not values:
        return float("nan")
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, max(0, math.ceil(fraction * len(ordered)) - 1))]


def summarize(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[(row.get("path", "?"), row.get("family", "?"))].append(row)
    out: list[dict[str, Any]] = []
    for (path, family), items in sorted(groups.items()):
        total = len(items)
        completed = sum(1 for r in items if r.get("terminal_state") == "COMPLETED")
        errored = sum(1 for r in items if r.get("error"))
        with_output = sum(1 for r in items if r.get("product_count"))
        latencies = [float(r["t_terminal_ms"]) for r in items if r.get("t_terminal_ms")]
        rate, lo, hi = wilson(completed, total)
        out.append({
            "path": path,
            "family": family,
            "n": total,
            "completed": completed,
            "completion_rate": round(rate, 4),
            "completion_lo95": round(lo, 4),
            "completion_hi95": round(hi, 4),
            "with_output": with_output,
            "errors": errored,
            "zero_error_upper_bound": round(upper_bound_zero(total - errored), 4),
            "p50_ms": round(percentile(latencies, 0.50), 1),
            "p95_ms": round(percentile(latencies, 0.95), 1),
        })
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()
    rows = [json.loads(line) for line in args.input.read_text(encoding="utf-8").splitlines() if line.strip()]
    summary = summarize(rows)
    fields = list(summary[0]) if summary else []
    if args.out and summary:
        with args.out.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(summary)
    print(f"rows={len(rows)}")
    for row in summary:
        print("  " + "  ".join(f"{k}={v}" for k, v in row.items()))


if __name__ == "__main__":
    main()
