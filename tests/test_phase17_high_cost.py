from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

import pandas as pd

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "src"))


class Phase17HighCostTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = PROJECT / "results/phase17"
        cls.backend = json.loads((cls.root / "high_cost_backend_status.json").read_text(encoding="utf-8"))
        cls.protocol = json.loads((cls.root / "open_mmgbsa_protocol.json").read_text(encoding="utf-8"))
        cls.summary = json.loads((cls.root / "phase17_execution_summary.json").read_text(encoding="utf-8"))
        cls.panel = pd.read_csv(cls.root / "phase17_high_cost_panel.csv", keep_default_na=False)
        cls.results = pd.read_csv(cls.root / "open_mmgbsa_results.csv", keep_default_na=False)

    def test_backend_audit_covers_requested_tools(self):
        expected = {"gromacs", "gmx_MMPBSA", "ambertools_antechamber", "ambertools_tleap",
                    "ambertools_sqm", "openmm", "parmed", "acpype", "rdkit",
                    "openff_toolkit", "openmmforcefields", "schrodinger_prime_mmgbsa"}
        self.assertTrue(expected.issubset(self.backend["backends"]))

    def test_openmm_install_is_not_misrepresented_as_complete_route(self):
        self.assertTrue(self.backend["backends"]["openmm"]["installed"])
        self.assertFalse(self.backend["routes"]["openmm_mmgbsa"]["usable"])
        self.assertFalse(self.backend["complete_open_source_route_usable"])

    def test_prime_license_is_reused_not_retried(self):
        prime = self.backend["backends"]["schrodinger_prime_mmgbsa"]
        self.assertEqual(prime["status"], "license_unavailable")
        self.assertIn("not retried", prime["blocking_reason"])

    def test_candidate_pool_is_identity_isolated(self):
        pool = pd.read_csv(self.root / "phase17_candidate_pool.csv", keep_default_na=False)
        self.assertEqual(len(pool), 90)
        self.assertEqual(pool["candidate_id"].nunique(), 90)
        self.assertEqual(int(pool["candidate_origin"].eq("phase15_historical_htvs").sum()), 60)
        self.assertEqual(int(pool["candidate_origin"].eq("phase16_generated").sum()), 30)

    def test_qualification_set_composition(self):
        self.assertEqual(len(self.panel), 8)
        self.assertEqual(self.panel["candidate_id"].nunique(), 8)
        counts = self.panel["selection_class"].value_counts().to_dict()
        expected = {"reference_IN2": 1, "multi_protocol_strong": 2, "extreme_disagreement": 2,
                    "medium_controls": 1, "generated_high_ranking": 1, "generated_diverse_novel": 1}
        self.assertEqual(counts, expected)
        self.assertIn("ATP-REF-IN2", set(self.panel["candidate_id"]))

    def test_blocked_jobs_preserve_no_numeric_result(self):
        self.assertEqual(len(self.results), 8)
        self.assertTrue(self.results["status"].eq("blocked").all())
        self.assertTrue(self.results["open_mmgbsa_deltaG"].eq("").all())
        self.assertTrue(self.results["failure_reason"].str.contains("complete_open_mmgbsa_route_unavailable").all())

    def test_protocol_is_not_falsely_frozen(self):
        self.assertEqual(self.protocol["protocol_id"], "open_mmgbsa_7p3w_v1")
        self.assertFalse(self.protocol["frozen_for_batch_use"])
        self.assertEqual(self.protocol["status"], "blocked_before_qualification")
        self.assertEqual(self.protocol["output_field"], "open_mmgbsa_deltaG")

    def test_gate_stops_30_and_60(self):
        gate = self.summary["qualification"]
        self.assertFalse(gate["qualified"])
        self.assertFalse(gate["batch30_started"])
        self.assertFalse(self.summary["expanded_to_60"])
        self.assertEqual(self.summary["high_cost_evidence_records"], 0)

    def test_downstream_outputs_are_explicitly_not_available(self):
        for name in ["protocol_comparison.csv", "three_protocol_robustness.csv",
                     "parent_child_evidence_comparison.csv", "phase17_shadow_decision.csv"]:
            frame = pd.read_csv(self.root / name, keep_default_na=False)
            self.assertEqual(frame.iloc[0]["status"], "not_available")
        next20 = pd.read_csv(self.root / "phase17_next20_acquisition.csv", keep_default_na=False)
        self.assertEqual(next20.iloc[0]["status"], "not_generated")

    def test_job_checkpoint_is_terminal_and_resumable(self):
        checkpoint = json.loads((PROJECT / "workspace_local/phase17/checkpoint.json").read_text(encoding="utf-8"))
        self.assertEqual(checkpoint["requested"], 8)
        self.assertEqual(checkpoint["blocked"], 8)
        self.assertFalse(checkpoint["batch30_started"])

    def test_models_remain_frozen(self):
        before = json.loads((self.root / "model_hashes_before.json").read_text(encoding="utf-8"))
        after = json.loads((self.root / "model_hashes_after.json").read_text(encoding="utf-8"))
        self.assertEqual(len(before), 24)
        self.assertEqual(before, after)
        self.assertTrue(self.summary["model_hashes_unchanged"])
        self.assertFalse(self.summary["training_performed"])


if __name__ == "__main__":
    unittest.main()
