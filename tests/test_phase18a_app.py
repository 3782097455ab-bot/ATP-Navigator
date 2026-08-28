"""Phase 18A productization boundary and data-integration tests."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pandas as pd

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "src"))

from app.data_adapter import ProjectData
from app.export_service import enrich
from app.query_router import ResearchQueryRouter


class Phase18ADataAdapterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = ProjectData(PROJECT)

    def test_candidate_sources_remain_identity_separated(self):
        frame = self.data.candidate_master()
        self.assertEqual(len(frame.loc[frame.candidate_source.eq("HTVS 1633")]), 1633)
        self.assertEqual(len(frame.loc[frame.candidate_source.eq("Phase 16 generated")]), 360)
        self.assertEqual(len(frame.loc[frame.candidate_source.eq("Internal 17")]), 17)
        self.assertEqual(len(frame), 2010)

    def test_unknown_missing_and_not_applicable_are_not_zero(self):
        frame = self.data.evidence_matrix()
        values = set(frame.drop(columns=["compound_id", "source"]).astype(str).stack())
        self.assertIn("missing", values)
        self.assertIn("unknown", values)
        self.assertIn("not_applicable", values)
        self.assertNotIn("0", values)

    def test_dashboard_uses_real_artifact_counts(self):
        values = self.data.dashboard_metrics()
        self.assertEqual(values["historical_candidates"], 1633)
        self.assertEqual(values["generated_candidates"], 360)
        self.assertEqual(values["historical_vina_evidence"], 1633)
        self.assertEqual(values["generated_vina_evidence"], 120)
        self.assertEqual(values["acquisition_panel"], 60)

    def test_phase15_acquisition_reuses_frozen_engine(self):
        selected = self.data.acquisition_recommendations("ATP_Navigator_hybrid", 20)
        self.assertEqual(len(selected), 20)
        self.assertFalse(selected.canonical_id.duplicated().any())
        self.assertTrue(selected.recommended_next_evidence.str.contains("MM/GBSA", regex=False).all())

    def test_decision_profiles_read_frozen_results(self):
        ranking = self.data.decision_ranking("balanced")
        self.assertEqual(len(ranking), 17)
        self.assertEqual(sorted(ranking["rank"].astype(int)), list(range(1, 18)))

    def test_feedback_empty_state_is_explicit(self):
        status = self.data.feedback_status()
        self.assertEqual(status["imports"], 0)
        self.assertIsNone(status["latest_snapshot"])
        self.assertFalse(status["training_performed_by_feedback_store"])

    def test_dialogue_does_not_invent_unavailable_physics(self):
        result = ResearchQueryRouter(self.data).answer("哪些高成本工具现在不可用？")
        self.assertTrue(result["records"])
        self.assertIn("不会", result["answer"])

    def test_export_adds_audit_metadata_without_changing_rows(self):
        source = pd.DataFrame([{"compound_id": "X", "score": None}])
        result = enrich(source, "unit_test", self.data)
        self.assertEqual(len(result), 1)
        self.assertIn("_git_commit", result)
        self.assertTrue(pd.isna(result.loc[0, "score"]))

    def test_no_phase18a_model_or_scientific_result_writer(self):
        source_files = list((PROJECT / "src/app").glob("*.py")) + [PROJECT / "app.py"]
        text = "\n".join(path.read_text(encoding="utf-8") for path in source_files)
        self.assertNotIn("fit(", text)
        self.assertNotIn("model.save", text)
        self.assertNotIn("vina_affinity =", text)


if __name__ == "__main__":
    unittest.main()
