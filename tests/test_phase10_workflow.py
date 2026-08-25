from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "examples"))

from input_processor import CandidateInputProcessor  # noqa: E402
from navigator_pipeline import NavigatorPipeline  # noqa: E402
from run_navigation_demo import build_demo_input  # noqa: E402


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class Phase10WorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temporary = tempfile.TemporaryDirectory(prefix="atp_phase10_tests_")
        cls.temp = Path(cls.temporary.name)
        cls.input_path = cls.temp / "demo_input.csv"
        build_demo_input(cls.input_path)
        cls.pipeline = NavigatorPipeline(PROJECT_ROOT)
        cls.before_hashes = dict(cls.pipeline.processor.model_hashes)
        cls.trace = cls.pipeline.run(
            cls.input_path,
            profile="atp_mechanism_focused",
            output_dir=cls.temp / "run1",
        )
        cls.ranking = pd.read_csv(cls.temp / "run1/final_navigation_report.csv")
        cls.processed = pd.read_csv(cls.temp / "run1/processed_candidate_table.csv", low_memory=False)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temporary.cleanup()

    def test_full_demo_uses_frozen_model_v3_without_training(self) -> None:
        self.assertEqual(len(self.processed), 17)
        self.assertTrue(self.processed["model_v3_status"].eq("available").all())
        self.assertTrue(self.processed["model_used"].eq("Model_v3_full_frozen").all())
        self.assertFalse(self.trace["supervised_training"])
        self.assertEqual(self.trace["model_change"], "none")

    def test_ranking_is_complete_unique_and_not_probability(self) -> None:
        self.assertEqual(set(self.ranking["rank"].astype(int)), set(range(1, 18)))
        self.assertEqual(self.ranking["compound_id"].nunique(), 17)
        self.assertTrue(
            self.ranking["score_scope"]
            .eq("batch_relative_computational_decision_not_probability")
            .all()
        )
        self.assertTrue(self.ranking["p_top3"].between(0, 1).all())

    def test_experimental_fields_remain_unknown(self) -> None:
        columns = [
            "experimental_ATP_inhibition",
            "experimental_MIC",
            "experimental_toxicity",
        ]
        self.assertTrue(self.processed[columns].eq("unknown").all().all())
        self.assertEqual(self.trace["experimental_values_imputed"], 0)

    def test_minimal_new_structure_gets_declared_fallback_but_no_final_score(self) -> None:
        path = self.temp / "minimal.csv"
        pd.DataFrame(
            [
                {
                    "compound_id": "NEW-ETHANOL",
                    "SMILES": "CCO",
                    "docking_score": -5.0,
                    "mmgbsa_score": -20.0,
                    "quickprop_features": "{}",
                    "admet_features": "{}",
                    "literature_features": "{}",
                }
            ]
        ).to_csv(path, index=False)
        output = self.temp / "minimal_processed.csv"
        frame = CandidateInputProcessor(PROJECT_ROOT).process(path, output)
        self.assertEqual(frame.iloc[0]["model_used"], "Model_v2-A_structure_only_fallback")
        self.assertEqual(frame.iloc[0]["model_v3_status"], "not_run_missing_frozen_features")
        self.assertEqual(frame.iloc[0]["experimental_MIC"], "unknown")
        trace = self.pipeline.run(path, profile="balanced", output_dir=self.temp / "minimal_run")
        ranking = pd.read_csv(self.temp / "minimal_run/final_navigation_report.csv")
        self.assertTrue(pd.isna(ranking.iloc[0]["final_score"]))
        self.assertEqual(trace["workflow_readiness"], "conditional")

    def test_invalid_smiles_is_retained_for_audit_and_not_scored(self) -> None:
        path = self.temp / "invalid.csv"
        pd.DataFrame(
            [
                {
                    "compound_id": "BAD-1",
                    "SMILES": "not_a_smiles",
                    "docking_score": -7.0,
                    "mmgbsa_score": -30.0,
                }
            ]
        ).to_csv(path, index=False)
        frame = CandidateInputProcessor(PROJECT_ROOT).process(
            path, self.temp / "invalid_processed.csv"
        )
        self.assertEqual(frame.iloc[0]["structure_status"], "invalid_smiles")
        self.assertTrue(pd.isna(frame.iloc[0]["model_score"]))
        self.assertEqual(frame.iloc[0]["experimental_ATP_inhibition"], "unknown")

    def test_profiles_are_explicit_and_normalized(self) -> None:
        config = json.loads((PROJECT_ROOT / "configs/research_profiles.json").read_text())
        required = {
            "binding_focused",
            "atp_mechanism_focused",
            "experimental_validation_focused",
        }
        self.assertTrue(required.issubset(config["profiles"]))
        for profile in config["profiles"].values():
            self.assertAlmostEqual(sum(profile["weights"].values()), 1.0, places=10)
        comparison = pd.read_csv(self.temp / "run1/profile_comparison.csv")
        self.assertEqual(set(comparison["profile"]), set(config["profiles"]))
        self.assertTrue(comparison.groupby("profile")["compound_id"].nunique().eq(17).all())
        stability = pd.read_csv(self.temp / "run1/profile_rank_stability.csv")
        self.assertEqual(len(stability), len(config["profiles"]) ** 2)

    def test_repeated_run_is_deterministic_and_models_are_unchanged(self) -> None:
        self.pipeline.run(
            self.input_path,
            profile="atp_mechanism_focused",
            output_dir=self.temp / "run2",
        )
        self.assertEqual(
            digest(self.temp / "run1/final_navigation_report.csv"),
            digest(self.temp / "run2/final_navigation_report.csv"),
        )
        self.assertEqual(self.before_hashes, self.pipeline.processor.model_hashes)

    def test_explanation_states_scientific_boundaries(self) -> None:
        text = (self.temp / "run1/candidate_explanation.md").read_text(encoding="utf-8")
        self.assertIn("not biological activity probability", text)
        self.assertIn("Experimental ATP inhibition: unknown", text)
        self.assertIn("MIC: unknown", text)


if __name__ == "__main__":
    unittest.main()
