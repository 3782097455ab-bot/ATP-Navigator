import json
import unittest
from pathlib import Path

import pandas as pd

from src.phase14_1_identity_audit import PROJECT, RELATION_ORDER, audit, structure_keys


class Phase141IdentityTests(unittest.TestCase):
    def test_structure_keys_are_deterministic(self):
        smiles = "C[NH+](C)Cc1ccccc1"
        self.assertEqual(structure_keys(smiles), structure_keys(smiles))

    def test_audit_has_exactly_18_queries(self):
        frame, summary = audit(PROJECT)
        self.assertEqual(len(frame), 18)
        self.assertEqual(set(frame["query_id"]), {"IN-2", *{f"Hit{i}" for i in range(1, 18)}})
        self.assertEqual(sum(summary["relation_counts"].values()), 18)

    def test_relation_vocabulary_is_controlled(self):
        frame, _ = audit(PROJECT)
        self.assertTrue(set(frame["identity_relation"]).issubset(RELATION_ORDER))

    def test_related_mappings_are_not_exact(self):
        frame, _ = audit(PROJECT)
        related = frame.loc[~frame["identity_relation"].isin(["exact_canonical", "exact_inchikey"])]
        self.assertFalse(related["exact_match"].any())

    def test_hit3_is_not_guessed_from_alias(self):
        frame, _ = audit(PROJECT)
        hit3 = frame.loc[frame["query_id"].eq("Hit3")].iloc[0]
        self.assertEqual(hit3["identity_relation"], "unresolved")
        self.assertEqual(hit3["matched_htvs_id"], "")

    def test_hit13_has_structure_and_historical_support(self):
        frame, _ = audit(PROJECT)
        hit13 = frame.loc[frame["query_id"].eq("Hit13")].iloc[0]
        self.assertTrue(hit13["exact_match"])
        self.assertIn("91074", hit13["notes"])

    def test_final_vina_retry_succeeded_without_protocol_change(self):
        summary = json.loads((PROJECT / "results/phase14/phase14_execution_summary.json").read_text())
        self.assertEqual(summary["qc"]["success"], 1633)
        self.assertEqual(summary["qc"]["failed"], 0)
        self.assertEqual(summary["qc"]["phase14_1_retry_attempted"], 5)
        self.assertEqual(summary["qc"]["phase14_1_retry_success"], 5)
        self.assertEqual(summary["workers"], 2)
        self.assertEqual(summary["protocol_id"], "vina_7p3w_v1")


if __name__ == "__main__":
    unittest.main()
