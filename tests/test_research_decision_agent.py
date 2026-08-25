from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from research_decision_agent import (  # noqa: E402
    AGENT_VERSION,
    ResearchDecisionAgent,
    explain_existing,
    resolve_intent,
)


class ResearchDecisionAgentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.agent = ResearchDecisionAgent(PROJECT_ROOT)
        cls.summary = cls.agent.run("balanced", None, 6)
        cls.results = PROJECT_ROOT / "results/phase9_decision_agent"

    def test_preserves_model_and_label_boundaries(self) -> None:
        trace = json.loads((self.results / "agent_trace.json").read_text(encoding="utf-8"))
        self.assertEqual(trace["agent_version"], AGENT_VERSION)
        self.assertEqual(trace["model_change"], "none")
        self.assertFalse(trace["supervised_training"])
        self.assertEqual(trace["experimental_labels_created"], 0)
        self.assertFalse(trace["decision_score_used_as_label"])

    def test_each_profile_has_complete_unique_ranking(self) -> None:
        ranking = pd.read_csv(self.results / "robust_rankings.csv")
        self.assertEqual(set(ranking["profile"]), set(self.agent.config["profiles"]))
        for _, group in ranking.groupby("profile"):
            self.assertEqual(len(group), 17)
            self.assertEqual(group["compound_id"].nunique(), 17)
            self.assertEqual(set(group["robust_order"]), set(range(1, 18)))
            for column in ["p_top1", "p_top3", "p_top5", "p_bottom5"]:
                self.assertTrue(group[column].between(0, 1).all())

    def test_weight_distributions_remain_normalized(self) -> None:
        weights = pd.read_csv(self.results / "weight_distribution_summary.csv")
        for _, group in weights.groupby("profile"):
            self.assertAlmostEqual(float(group["central_weight"].sum()), 1.0, places=10)
            self.assertAlmostEqual(float(group["sample_mean"].sum()), 1.0, places=10)

    def test_panel_is_unique_and_does_not_claim_activity(self) -> None:
        panel = pd.read_csv(self.results / "next_experiment_panel.csv")
        self.assertEqual(len(panel), 6)
        self.assertEqual(panel["compound_id"].nunique(), 6)
        self.assertIn("Hit3", set(panel["historical_alias"]))
        self.assertTrue(panel["experimental_result_status"].eq("unknown").all())
        self.assertFalse(panel["selection_is_activity_claim"].astype(bool).any())

    def test_pareto_front_members_are_not_dominated(self) -> None:
        pareto = pd.read_csv(self.results / "pareto_analysis.csv")
        components = self.agent.config["component_columns"]
        values = pareto[components].to_numpy(dtype=float)
        optimal_indices = np.flatnonzero(pareto["pareto_optimal"].astype(bool).to_numpy())
        for index in optimal_indices:
            dominated = any(
                np.all(values[other] >= values[index]) and np.any(values[other] > values[index])
                for other in range(len(values))
                if other != index
            )
            self.assertFalse(dominated)

    def test_hit3_explanation_preserves_unknown_experiments(self) -> None:
        ranking = pd.read_csv(self.results / "robust_rankings.csv")
        hit3 = ranking.loc[
            ranking["profile"].eq("balanced") & ranking["historical_alias"].eq("Hit3"),
            "compound_id",
        ].iloc[0]
        payload = explain_existing(PROJECT_ROOT, hit3, "balanced")
        self.assertEqual(payload["experimental_ATP_activity"], "unknown")
        self.assertEqual(payload["experimental_MIC"], "unknown")

    def test_free_text_intent_requires_confirmation(self) -> None:
        intent = resolve_intent(self.agent.config, None, "优先验证ATP合酶机制和酶活")
        self.assertEqual(intent.selected_profile, "target_mechanism")
        self.assertTrue(intent.requires_human_confirmation)


if __name__ == "__main__":
    unittest.main()
