import random
import unittest

from simulator import VARIANTS, simulate_task


def variant(name):
    return next(item for item in VARIANTS if item.name == name)


class SimulatorInvariantTests(unittest.TestCase):
    def test_full_rejects_invalid_signature(self):
        row = simulate_task(random.Random(0), variant("Full"), "t", "unique", "invalid_signature")
        self.assertTrue(row["rejected"])
        self.assertTrue(row["safe_rejection"])
        self.assertEqual(row["terminal_reason"], "invalid_signature")

    def test_full_rejects_identity_and_endpoint_faults(self):
        for fault in ("forged_identity", "bad_endpoint"):
            row = simulate_task(random.Random(0), variant("Full"), "t", "sensitive", fault)
            self.assertTrue(row["rejected"], fault)
            self.assertTrue(row["safe_rejection"], fault)
            self.assertFalse(row["unauthorized_call"], fault)

    def test_full_rejects_missing_consent(self):
        row = simulate_task(random.Random(0), variant("Full"), "t", "sensitive", "missing_consent")
        self.assertTrue(row["rejected"])
        self.assertTrue(row["safe_rejection"])
        self.assertEqual(row["terminal_reason"], "consent_missing")

    def test_dedup_ablation_exposes_duplicate_side_effect(self):
        full = simulate_task(random.Random(1), variant("Full"), "t", "unique", "duplicate_event")
        ablated = simulate_task(random.Random(1), variant("B4_no_isolation_dedup"), "t", "unique", "duplicate_event")
        self.assertFalse(full["duplicate_side_effect"])
        self.assertTrue(ablated["duplicate_side_effect"])

    def test_identity_ablation_can_accept_bad_endpoint(self):
        row = simulate_task(random.Random(1), variant("B2_no_identity"), "t", "unique", "bad_endpoint")
        self.assertTrue(row["identity_bypass"])

    def test_typed_judgment_abstains_below_threshold(self):
        typed = variant("B5_typed_judgment")
        rows = [
            simulate_task(random.Random(seed), typed, "t", "ambiguous")
            for seed in range(200)
        ]
        abstained = [row for row in rows if row["clarification_requested"]]
        self.assertTrue(abstained, "expected the typed-judgment arm to abstain")
        self.assertTrue(all(row["terminal_reason"] == "awaiting_clarification" for row in abstained))
        self.assertTrue(all(not row["correct_delegation"] for row in abstained))


if __name__ == "__main__":
    unittest.main()
