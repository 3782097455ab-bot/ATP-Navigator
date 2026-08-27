from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "src"))

from acquisition.query_service import answer
from research_workspace import ResearchWorkspace


class Phase15AcquisitionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = PROJECT / "results/phase15"
        cls.panel = pd.read_csv(root / "acquisition_panel_v1.csv")
        cls.protocol = pd.read_csv(root / "protocol_robustness.csv")
        cls.uncertainty = pd.read_csv(root / "uncertainty_decomposition.csv")
        cls.voi = pd.read_csv(root / "voi_proxy.csv")
        cls.budget = pd.read_csv(root / "budget_simulation.csv")
        cls.summary = json.loads((root / "phase15_summary.json").read_text(encoding="utf-8"))

    def test_panel_has_60_unique_candidates(self):
        self.assertEqual(len(self.panel), 60)
        self.assertEqual(self.panel["canonical_id"].nunique(), 60)

    def test_panel_quotas(self):
        expected = {"multi_protocol_strong": 15, "extreme_disagreement": 15,
                    "rank_boundary_uncertain": 10, "scaffold_diverse": 10,
                    "medium_controls": 5, "historical_bridge_interpretable": 5}
        self.assertEqual(self.panel["acquisition_class"].value_counts().to_dict(), expected)

    def test_protocol_robustness_has_full_library(self):
        self.assertEqual(len(self.protocol), 1633)
        self.assertTrue(self.protocol["protocol_disagreement_score"].between(0, 1).all())

    def test_uncertainty_is_decomposed(self):
        required = {"protocol_uncertainty", "model_uncertainty", "objective_uncertainty",
                    "model_disagreement_if_available", "evidence_uncertainty",
                    "chemical_space_uncertainty", "model_uncertainty_status"}
        self.assertTrue(required.issubset(self.uncertainty.columns))
        self.assertTrue(self.uncertainty["model_uncertainty"].isna().all())

    def test_all_requested_budgets_exist(self):
        self.assertEqual(sorted(self.budget["budget"].unique().tolist()), [10, 20, 40, 60, 100])

    def test_baseline_and_advanced_strategies_exist(self):
        required = {"random", "vina_top", "glide_top", "consensus_top", "disagreement_aware",
                    "diversity_aware", "uncertainty_aware", "rank_boundary", "evidence_gap",
                    "ATP_Navigator_hybrid"}
        self.assertTrue(required.issubset(set(self.budget["strategy"])))

    def test_outputs_do_not_claim_biological_hits(self):
        columns = " ".join(self.budget.columns).lower()
        self.assertNotIn("biological_hit_rate", columns)
        self.assertNotIn("expected_activity_gain", columns)
        self.assertFalse(self.summary["biological_activity_claim"])

    def test_voi_is_nonnegative_and_cost_explicit(self):
        self.assertTrue(self.voi["voi_proxy"].ge(0).all())
        self.assertTrue(self.voi["acquisition_cost"].gt(0).all())

    def test_gnina_never_fabricates_when_unavailable(self):
        status = self.summary["gnina"]
        if status["status"] == "unavailable":
            self.assertEqual(status["shadow_scores_generated"], 0)
        self.assertFalse(status["blocking"])

    def test_historical_models_remain_identical(self):
        before = json.loads((PROJECT / "results/phase14/model_hashes_before.json").read_text(encoding="utf-8"))
        after = json.loads((PROJECT / "results/phase14/model_hashes_after.json").read_text(encoding="utf-8"))
        self.assertEqual(len(before), 24)
        self.assertEqual(before, after)

    def test_query_service_returns_budget20(self):
        result = answer(PROJECT, "如果MM/GBSA只能再算20个，算谁？")
        self.assertEqual(result["budget"], 20)
        self.assertEqual(len(result["candidates"]), 20)

    def test_query_service_covers_required_questions(self):
        questions = [
            "为什么选这个候选？Vina和Glide意见冲突的有哪些？",
            "哪些候选两个协议都很强？",
            "哪个候选的不确定性主要来自协议？",
            "如果预算从60降到20，哪些候选会被删除？",
        ]
        for question in questions:
            with self.subTest(question=question):
                self.assertNotEqual(answer(PROJECT, question).get("status"), "unsupported_question")

    def test_workspace_routes_acquisition_question(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = ResearchWorkspace(PROJECT, Path(tmp) / "workspace")
            session = workspace.create_session(PROJECT / "results/demo/demo_input.csv")
            result = workspace.chat(session, "如果MM/GBSA只能再算20个，算谁？")
            self.assertEqual(result["budget"], 20)
            self.assertEqual(len(result["candidates"]), 20)


if __name__ == "__main__":
    unittest.main()
