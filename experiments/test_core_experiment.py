import csv
import tempfile
import unittest
from pathlib import Path

from core_experiment import CORE_CATEGORIES, CORE_FAULTS, CORE_VARIANTS, generate


class CoreExperimentTests(unittest.TestCase):
    def test_replays_are_paired_and_deterministic(self):
        first = generate(20260930, 2)
        second = generate(20260930, 2)
        self.assertEqual(first, second)
        self.assertEqual(len(first), len(CORE_CATEGORIES) * len(CORE_FAULTS) * 2 * len(CORE_VARIANTS))
        by_pair = {}
        for row in first:
            by_pair.setdefault(row["pair_id"], []).append(row)
        self.assertTrue(all(len(rows) == len(CORE_VARIANTS) for rows in by_pair.values()))
        self.assertTrue(all(len({row["seed"] for row in rows}) == 1 for rows in by_pair.values()))

    def test_core_arms_are_the_declared_five(self):
        self.assertEqual(
            {variant.name for variant in CORE_VARIANTS},
            {"B1_auto_discovery", "B2_no_identity", "B3_no_consent", "B4_no_isolation_dedup", "Full"},
        )


if __name__ == "__main__":
    unittest.main()
