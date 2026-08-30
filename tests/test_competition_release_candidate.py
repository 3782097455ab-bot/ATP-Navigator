from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

import pandas as pd

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "src"))

from agent.actions import ActionRegistry
from agent.providers import RuleBasedProvider


class CompetitionReleaseCandidateTests(unittest.TestCase):
    def test_member_manifest_and_endpoint_segregation(self):
        root = PROJECT / "results/release_candidate/member_data_integration"
        manifest = pd.read_csv(root / "member_data_manifest.csv")
        self.assertIn("BindingDB_BindingDB_Articles.tsv", set(manifest["filename"]))
        member1 = pd.read_csv(root / "member1_qc.csv")
        member2 = pd.read_csv(root / "member2_qc.csv")
        self.assertEqual(int(member1["training_eligible"].sum()), 0)
        self.assertTrue(member2["endpoint_semantics"].eq("whole_cell_MIC_not_ATP_synthase_activity").all())

    def test_bindingdb_atpase_is_not_mislabeled_as_atp_synthase(self):
        summary = json.loads((PROJECT / "results/release_candidate/member_data_integration/integration_summary.json").read_text(encoding="utf-8"))
        self.assertEqual(summary["member3_part1"]["direct_atp_synthase_rows"], 0)
        self.assertEqual(summary["member3_part1"]["training_eligible_rows"], 0)

    def test_shadow_did_not_promote(self):
        gate = json.loads((PROJECT / "results/release_candidate/model_promotion/model_promotion_gate.json").read_text(encoding="utf-8"))
        self.assertFalse(gate["promotion_passed"])
        self.assertEqual(gate["official_model_after"], "Model v3")
        self.assertEqual(gate["model_v3_direct_comparison_status"], "not_applicable_task_mismatch")

    def test_release_decision_is_versioned_shadow(self):
        frame = pd.read_csv(PROJECT / "results/release_candidate/decision_runs/competition_rc_decision_v1.csv")
        self.assertEqual(len(frame), 30)
        self.assertTrue(frame["run_role"].eq("release_candidate_updated_evidence_shadow").all())
        self.assertTrue(frame["experimental_ATP_inhibition"].eq("unknown").all())
        self.assertTrue(frame["experimental_MIC"].eq("unknown").all())

    def test_phase17_dialogue_can_explain_specific_change_and_closeness(self):
        provider = RuleBasedProvider()
        parsed = provider.parse("为什么ATP-HTVS-66618B00A972加入MMGBSA后变化这么大？", {})
        self.assertEqual(parsed.constraints["analysis_view"], "candidate_explanation")
        registry = ActionRegistry(PROJECT)
        result = registry.compare_protocol({"analysis_view": "candidate_explanation", "candidate_scope": ["ATP-HTVS-66618B00A972"], "top_k": 5})
        self.assertIn("优先级下降", result["answer"])
        closeness = registry.compare_protocol({"analysis_view": "protocol_closeness", "top_k": 5})
        self.assertIn("Vina", closeness["answer"])

    def test_protected_models_remain_unchanged(self):
        reference = json.loads((PROJECT / "results/phase14/model_hashes_after.json").read_text(encoding="utf-8"))
        import hashlib
        for relative, expected in reference.items():
            self.assertEqual(hashlib.sha256((PROJECT / relative).read_bytes()).hexdigest(), expected)


if __name__ == "__main__":
    unittest.main()
