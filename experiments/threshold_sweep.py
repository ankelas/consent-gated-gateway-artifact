"""Sweep the typed-judgment threshold and report coverage against residual risk.

The routing profile in the simulator is a placeholder standing in for the
distribution that the labeled judgment-point suite must measure. This script
exists so the coverage-risk curve has a harness and a reproducible artifact
before any measured distribution is available.
"""

from __future__ import annotations

import argparse
import csv
import random
from dataclasses import replace
from pathlib import Path

from simulator import VARIANTS, simulate_task


THRESHOLDS = (0.50, 0.60, 0.70, 0.80, 0.90)
CATEGORIES = ("unique", "ambiguous", "sensitive", "no_match")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=20260921)
    parser.add_argument("--trials", type=int, default=200)
    parser.add_argument(
        "--output", type=Path, default=Path("data/typed_threshold_sweep.csv")
    )
    args = parser.parse_args()

    base = next(item for item in VARIANTS if item.name == "B5_typed_judgment")
    rows = []
    for threshold in THRESHOLDS:
        variant = replace(base, decision_threshold=threshold)
        rng = random.Random(args.seed)
        records = [
            simulate_task(
                rng, variant, f"sweep-{threshold:.2f}-{category}-{index}", category
            )
            for category in CATEGORIES
            for index in range(args.trials)
        ]
        covered = [row for row in records if not row["clarification_requested"]]
        correct = [row for row in covered if row["correct_delegation"]]
        rows.append(
            {
                "threshold": f"{threshold:.2f}",
                "n": len(records),
                "coverage": f"{len(covered) / len(records):.4f}",
                "abstention_rate": f"{1 - len(covered) / len(records):.4f}",
                "error_rate_among_covered": (
                    f"{1 - len(correct) / len(covered):.4f}" if covered else ""
                ),
                "correct_delegation_rate": f"{len(correct) / len(records):.4f}",
            }
        )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    for row in rows:
        print(row)


if __name__ == "__main__":
    main()
