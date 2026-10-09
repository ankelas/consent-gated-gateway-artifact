"""Deterministic paired driver for the executable gateway study.

The mechanisms live in :mod:`gateway`; this module only builds a workload item
and calls the gateway, so a reader can check that no outcome flag is assigned
here.  It keeps the historical ``simulate_task`` signature so the pilot,
threshold-sweep, aggregation and test scripts keep working.

The workload generator and the gateway are offline and deterministic.  Named
random streams give every arm the same scenario and the same downstream draws,
which is what makes the arm comparison paired.
"""

from __future__ import annotations

import random
from typing import Any, Dict

from gateway import (  # noqa: F401  (re-exported for existing scripts)
    CORE_VARIANTS,
    FAULTS,
    VARIANTS,
    Arm,
    build_scenario,
    run_task,
    stream,
)


def simulate_task(
    rng: random.Random,
    variant: Arm,
    task_id: str,
    category: str,
    fault: str = "none",
    population: int = 50,
    concurrency: int = 1,
) -> Dict[str, Any]:
    """Run one logical task under one arm and attach the pairing metadata."""
    master_seed = rng.getrandbits(64)
    scenario = build_scenario(stream(master_seed, "scenario"), category, population)
    row = run_task(
        rng,
        variant,
        scenario,
        fault=fault,
        population=population,
        concurrency=concurrency,
    )
    row.update({
        "task_id": task_id,
        "category": category,
        "fault": fault,
        "agent_population": population,
        "concurrency": concurrency,
    })
    return row
