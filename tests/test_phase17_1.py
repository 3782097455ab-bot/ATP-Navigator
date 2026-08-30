from __future__ import annotations

import json
import math
import re
import unittest
from pathlib import Path

import pandas as pd

from src.phase17_1.engine import (
    PROTOCOL_ID,
    build_cumulative_plan,
    execution_policy,
    result_row,
    systematic_corruption,
    verify_protocol,
)
from src.phase17_1.protocol import stable_hash


PROJECT = Path(__file__).resolve().parents[1]


class Phase171Tests(unittest.TestCase):
    def test_v2_protocol_is_self_consistent_and_not_v1_overwrite(self):
        path = PROJECT / "results/phase17_1/open_mmgbsa_7p3w_v2.json"
        protocol = json.loads(path.read_text(encoding="utf-8"))
        verify_protocol(protocol)
        self.assertEqual(protocol["protocol_id"], PROTOCOL_ID)
        self.assertEqual(
            protocol["protocol_hash"],
            stable_hash({key: value for key, value in protocol.items() if key != "protocol_hash"}),
        )
        self.assertEqual(protocol["resource_policy"]["concurrent_jobs"], 1)
        self.assertTrue(protocol["forbidden_equivalences"])

    def test_competition_policy_stops_automatic_expansion_at_30(self):
        policy = execution_policy(PROJECT)
        self.assertEqual(policy["qualification_target"], 8)
        self.assertEqual(policy["pilot_target"], 30)
        self.assertFalse(policy["auto_expand_to_60"])
        self.assertEqual(policy["optional_extension_target"], 60)
        self.assertFalse(policy["scientific_protocol_changed"])

    def test_cumulative_plan_reuses_fixed_phase17_qualification_set(self):
        import pandas as pd

        plan = build_cumulative_plan(PROJECT)
        frozen = pd.read_csv(PROJECT / "results/phase17/phase17_high_cost_panel.csv")
        self.assertEqual(len(plan), 60)
        self.assertEqual(plan["candidate_id"].nunique(), 60)
        self.assertEqual(plan.iloc[:8]["candidate_id"].tolist(), frozen["candidate_id"].tolist())
        self.assertTrue(plan.iloc[:8]["stage_added"].eq("qualification").all())
        self.assertTrue(plan.iloc[8:30]["stage_added"].eq("pilot30").all())
        self.assertTrue(plan.iloc[30:60]["stage_added"].eq("expanded60").all())

    def test_unrun_candidate_has_no_numerical_evidence(self):
        candidate = {
            "panel_order": 1,
            "stage_added": "qualification",
            "candidate_id": "X",
            "candidate_origin": "test",
            "selection_class": "test",
        }
        row = result_row(candidate, None)
        self.assertEqual(row["status"], "planned")
        self.assertIsNone(row["open_mmgbsa_deltaG"])
        self.assertFalse(row["finite_result"])
        self.assertEqual(row["activity_label"], "not_applicable")

    def test_single_technical_failure_is_not_systematic_corruption(self):
        rows = [
            {"status": "success", "failure_stage": "", "failure_reason": ""}
            for _ in range(7)
        ] + [{
            "status": "failed",
            "failure_stage": "parameterization",
            "failure_reason": "technical backend error",
        }]
        self.assertFalse(systematic_corruption(rows)["detected"])

    def test_repeated_nonfinite_results_trigger_gate_protection(self):
        rows = [{
            "status": "failed",
            "failure_stage": "analysis",
            "failure_reason": "nonfinite parser output",
        }, {
            "status": "failed",
            "failure_stage": "analysis",
            "failure_reason": "nonfinite parser output",
        }]
        self.assertTrue(systematic_corruption(rows)["detected"])

    def test_post_analysis_is_strict_json_and_does_not_impute_missing_glide(self):
        path = PROJECT / "results/phase17_1/post_analysis.json"
        raw = path.read_text(encoding="utf-8")
        self.assertIsNone(re.search(r":\s*(?:NaN|Infinity|-Infinity)(?:[,}\]])", raw))
        payload = json.loads(raw)
        audit = payload["nan_audit"]
        self.assertFalse(audit["imputation_performed"])
        self.assertEqual(audit["glide_exact_id_recovered"], 24)
        self.assertEqual(audit["glide_remaining_missing"], 6)
        self.assertEqual(audit["technical_errors_unresolved"], [])

    def test_pairwise_metrics_use_only_finite_matched_observations(self):
        payload = json.loads((PROJECT / "results/phase17_1/post_analysis.json").read_text(encoding="utf-8"))
        matched = {
            (row["protocol_a"], row["protocol_b"]): row["matched_n"]
            for row in payload["pairwise_metrics"]
        }
        self.assertEqual(matched[("glide", "vina")], 24)
        self.assertEqual(matched[("glide", "open_mmgbsa")], 24)
        self.assertEqual(matched[("vina", "open_mmgbsa")], 30)

    def test_shadow_outputs_preserve_unavailable_as_nan_with_reason(self):
        comparison = pd.read_csv(PROJECT / "results/phase17_1/three_protocol_comparison.csv")
        self.assertEqual(len(comparison), 30)
        unavailable = comparison.loc[~comparison["three_protocol_complete"]]
        self.assertEqual(len(unavailable), 6)
        self.assertTrue(unavailable["glide_score"].isna().all())
        self.assertTrue(unavailable["three_protocol_missing_reason"].notna().all())
        self.assertTrue(pd.to_numeric(comparison["open_mmgbsa_deltaG"], errors="coerce").map(math.isfinite).all())

    def test_post_analysis_did_not_start_optional_expansion(self):
        payload = json.loads((PROJECT / "results/phase17_1/post_analysis.json").read_text(encoding="utf-8"))
        self.assertFalse(payload["candidate_computation_executed"])
        self.assertFalse(payload["optional_60_expansion_started"])
        self.assertFalse(payload["registry_evidence_mutated"])


if __name__ == "__main__":
    unittest.main()
