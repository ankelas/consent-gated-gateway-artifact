"""Run the compact paired core experiment used in the manuscript.

The core study tests the architecture mechanisms that can be evaluated without
a live model or deployment: discovery/consent, endpoint identity, session
isolation, and event deduplication. Every semantic task is replayed under every
arm with the same derived seed, so differences are attributable to the arm's
mechanism rather than to a different random stream.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import random
from pathlib import Path

from simulator import CORE_VARIANTS, simulate_task


CORE_FAULTS = (
    "none",
    "duplicate_event",
    "reordered_event",
    "invalid_signature",
    "forged_identity",
    "bad_endpoint",
    "missing_consent",
    "timeout",
    "service_restart",
    "cross_session",
)
CORE_CATEGORIES = ("unique", "ambiguous", "sensitive", "no_match")
FIELDS = [
    "pair_id", "variant", "task_id", "category", "fault", "seed",
    "task_success", "correct_delegation", "safe_rejection", "unauthorized_call",
    "identity_bypass", "cross_session_leak", "duplicate_side_effect", "recovered",
    "clarification_requested", "rejected", "terminal_reason", "latency_ms",
    "message_bytes", "retry_count", "telemetry",
]


def task_seed(master_seed: int, pair_id: str) -> int:
    digest = hashlib.sha256(f"{master_seed}:{pair_id}".encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big")


def generate(master_seed: int, repetitions: int, include_scale: bool = False) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    populations = (50,)
    concurrencies = (1,)
    if include_scale:
        populations = (10, 50, 100, 500)
        concurrencies = (1, 10, 50)
    for category in CORE_CATEGORIES:
        for fault in CORE_FAULTS:
            for population in populations:
                for concurrency in concurrencies:
                    for index in range(repetitions):
                        pair_id = f"{category}:{fault}:{population}:{concurrency}:{index}"
                        seed = task_seed(master_seed, pair_id)
                        for variant in CORE_VARIANTS:
                            row = simulate_task(
                                random.Random(seed), variant, pair_id, category,
                                fault=fault, population=population, concurrency=concurrency,
                            )
                            row = {"pair_id": pair_id, "seed": seed, **row}
                            rows.append(row)
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=20260930)
    parser.add_argument("--repetitions", type=int, default=100)
    parser.add_argument("--include-scale", action="store_true")
    parser.add_argument("--output", type=Path, default=Path("data/core_results.csv"))
    args = parser.parse_args()
    rows = generate(args.seed, args.repetitions, args.include_scale)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: str(row.get(field, "")).lower() if isinstance(row.get(field), bool) else row.get(field, "") for field in FIELDS})
    pairs = len(rows) // len(CORE_VARIANTS)
    print(f"wrote {len(rows)} rows ({pairs} paired tasks, {len(CORE_VARIANTS)} arms) to {args.output}")


if __name__ == "__main__":
    main()
