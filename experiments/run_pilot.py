"""Generate pilot experiment records for the modular architecture paper."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path
import random
from typing import Iterable, List, Dict

from simulator import FAULTS, VARIANTS, simulate_task


FIELDS = [
    "variant", "task_id", "category", "fault", "agent_population", "concurrency",
    "task_success", "correct_delegation", "safe_rejection", "unauthorized_call",
    "identity_bypass", "cross_session_leak", "duplicate_side_effect", "recovered",
    "clarification_requested", "rejected", "terminal_reason", "latency_ms",
    "message_bytes", "retry_count",
]


def _bool(value: object) -> object:
    return str(value).lower() if isinstance(value, bool) else value


def generate(mode: str, seed: int, tasks_per_cell: int) -> List[Dict[str, object]]:
    rng = random.Random(seed)
    rows: List[Dict[str, object]] = []
    if mode in {"e1", "all"}:
        categories = ("unique", "ambiguous", "sensitive", "no_match")
        for variant in VARIANTS:
            for index in range(tasks_per_cell):
                category = categories[index % len(categories)]
                rows.append(simulate_task(
                    rng, variant, f"e1-{variant.name}-{index}", category,
                    population=50, concurrency=1,
                ))
    if mode in {"e2", "all"}:
        fault_cells = ("duplicate_event", "reordered_event", "invalid_signature", "forged_identity",
                       "bad_endpoint", "missing_consent", "timeout", "service_restart", "cross_session")
        for variant in VARIANTS:
            for fault in fault_cells:
                for index in range(max(1, tasks_per_cell // 2)):
                    category = "sensitive" if fault in {"forged_identity", "bad_endpoint", "missing_consent"} else "unique"
                    rows.append(simulate_task(
                        rng, variant, f"e2-{variant.name}-{fault}-{index}", category,
                        fault=fault, population=50, concurrency=10,
                    ))
    if mode in {"e3", "all"}:
        for variant in VARIANTS:
            for population in (10, 50, 100, 500):
                for concurrency in (1, 10, 50):
                    for index in range(max(1, tasks_per_cell // 4)):
                        rows.append(simulate_task(
                            rng, variant, f"e3-{variant.name}-{population}-{concurrency}-{index}",
                            "unique", population=population, concurrency=concurrency,
                        ))
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("e1", "e2", "e3", "all"), default="all")
    parser.add_argument("--seed", type=int, default=20260921)
    parser.add_argument("--tasks-per-cell", type=int, default=40)
    parser.add_argument("--output", type=Path, default=Path("experiments/data/pilot_results.csv"))
    args = parser.parse_args()

    rows = generate(args.mode, args.seed, args.tasks_per_cell)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: _bool(row.get(field, "")) for field in FIELDS})
    print(f"wrote {len(rows)} rows to {args.output}")


if __name__ == "__main__":
    main()
