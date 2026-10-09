"""Aggregate repeated runs of the judgment measurement.

The hosted endpoint is not deterministic at temperature 0: repeating an
identical request changes the answer on a non-trivial share of items. Any
number reported from a single run therefore carries unquantified variance, so
this script reports the mean and the observed range across runs, plus the
pairwise answer-level agreement that sets the noise floor.
"""

from __future__ import annotations

import argparse
import csv
import statistics
from pathlib import Path
from typing import Dict, List


def read_rows(path: Path) -> List[Dict[str, str]]:
    with path.open(encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def metric(rows: List[Dict[str, str]], split: str, condition: str, field: str) -> float:
    for row in rows:
        if row["split"] == split and row["condition"] == condition and row["judgment_point"] == "ALL":
            return float(row[field])
    return float("nan")


def mean_range(values: List[float], percent: bool = False) -> str:
    values = [value for value in values if value == value]  # drop NaN
    if not values:
        return "n/a"
    mean = statistics.fmean(values)
    if percent:
        return f"{mean:.1%} ({min(values):.1%}--{max(values):.1%})"
    return f"{mean:.3f} ({min(values):.3f}--{max(values):.3f})"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--eval", nargs="+", required=True, type=Path)
    parser.add_argument("--predictions", nargs="+", default=None, type=Path)
    parser.add_argument("--label", default="judgment layer")
    parser.add_argument("--split", default="test")
    parser.add_argument("--conditions", default="typed,free_text,keyword")
    args = parser.parse_args()

    runs = [read_rows(path) for path in args.eval]
    conditions = [c for c in args.conditions.split(",") if c]

    print(f"# {args.label}: {len(runs)} runs, split={args.split}")
    print()
    print("| Condition | Accuracy | Brier | ECE | Coverage at 0.99 | Residual error |")
    print("| --- | --- | --- | --- | --- | --- |")
    for condition in conditions:
        accuracy = [metric(rows, args.split, condition, "accuracy") for rows in runs]
        brier = [metric(rows, args.split, condition, "brier") for rows in runs]
        ece = [metric(rows, args.split, condition, "ece") for rows in runs]
        coverage = [metric(rows, f"{args.split}_threshold", condition, "coverage") for rows in runs]
        residual = [metric(rows, f"{args.split}_threshold", condition, "residual_error") for rows in runs]
        print(
            f"| {condition} | {mean_range(accuracy, percent=True)} | {mean_range(brier)} "
            f"| {mean_range(ece)} | {mean_range(coverage, percent=True)} "
            f"| {mean_range(residual, percent=True)} |"
        )

    if args.predictions:
        tables = []
        for path in args.predictions:
            with path.open(encoding="utf-8") as handle:
                tables.append({(row["condition"], row["task_id"]): row["prediction"]
                               for row in csv.DictReader(handle)})
        keys = sorted(set.intersection(*(set(table) for table in tables)))
        print()
        print("| Condition | Items | Pairwise answer agreement |")
        print("| --- | --- | --- |")
        for condition in conditions:
            group = [key for key in keys if key[0] == condition]
            pairs = agreements = 0
            for i in range(len(tables)):
                for j in range(i + 1, len(tables)):
                    for key in group:
                        pairs += 1
                        agreements += tables[i][key] == tables[j][key]
            rate = agreements / pairs if pairs else float("nan")
            print(f"| {condition} | {len(group)} | {rate:.1%} |")


if __name__ == "__main__":
    main()
