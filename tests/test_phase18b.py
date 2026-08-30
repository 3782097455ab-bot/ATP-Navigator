from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "src"))

from agent.actions import ACTION_QUERY_CANDIDATE, ActionRegistry
from agent.activity import ActivityService
from agent.collaboration import CollaborationStore
from agent.orchestrator import ConversationalOrchestrator
from agent.providers import RuleBasedProvider
from agent.structure_viewer import PoseRegistry

def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class IntentTests(unittest.TestCase):
    def setUp(self):
        self.provider = RuleBasedProvider()
        self.context = {"selected_candidate_set": ["ATP-HTVS-A", "ATP-HTVS-B"]}

    def test_required_intents_route_to_supported_operations(self):
        cases = {
            "Hit13有哪些证据？": "evidence_query",
            "Hit13的来源和hash是什么？": "provenance_query",
            "找出Glide和Vina分歧最大的10个": "protocol_comparison",
            "为什么推荐Hit3？": "decision_ranking",
            "如果MMGBSA只能再算20个，帮我选": "acquisition",
            "围绕IN-2扩100个分子，保留核心骨架": "generation",
            "为Hit13创建MMGBSA计算计划": "calculation_plan",
            "当前任务状态和进度": "job_status",
            "项目还缺什么证据？": "missing_evidence",
            "哪些后端工具不可用？": "tool_capability",
            "ATP-GEN-7A898D5E996B的parent lineage": "parent_lineage",
            "导出这些候选": "export_request",
            "查看Hit13": "candidate_query",
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(self.provider.parse(text, self.context).operation, expected)

    def test_multi_turn_here_resolves_previous_selection(self):
        parsed = self.provider.parse("那从这里挑5个做进一步计算", self.context)
        self.assertEqual(parsed.operation, "acquisition")
        self.assertEqual(parsed.candidate_scope, self.context["selected_candidate_set"])
        self.assertEqual(parsed.budget, 5)

    def test_phase17_1_questions_route_to_read_only_protocol_views(self):
        cases = {
            "哪些候选三个协议最一致？": "consensus",
            "哪些候选加入MMGBSA后判断变化最大？": "evidence_impact",
            "哪些候选仍然证据冲突？": "disagreement",
        }
        for text, view in cases.items():
            with self.subTest(text=text):
                parsed = self.provider.parse(text, self.context)
                self.assertEqual(parsed.operation, "protocol_comparison")
                self.assertEqual(parsed.constraints["analysis_view"], view)


class OrchestratorAndCollaborationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        db = Path(self.temp.name) / "collaboration.sqlite3"
        self.store = CollaborationStore(PROJECT, database=db)
        self.engine = ConversationalOrchestrator(PROJECT, collaboration=self.store)
        self.session = self.engine.new_session("reviewer-a")

    def tearDown(self):
        self.temp.cleanup()

    def test_unconfirmed_plan_cannot_execute(self):
        calls = []
        self.engine.actions.actions["ACTION_RUN_ACQUISITION"] = lambda args: calls.append(args) or {"status": "completed"}
        result = self.engine.handle(self.session, "如果MMGBSA只能再算5个，帮我选")
        self.assertEqual(result["status"], "confirmation_required")
        self.assertEqual(calls, [])
        self.assertEqual(self.store.plan(result["plan"]["plan_id"])["status"], "pending_confirmation")

    def test_confirm_executes_only_the_allowlisted_action(self):
        calls = []
        self.engine.actions.actions["ACTION_RUN_ACQUISITION"] = lambda args: calls.append(args) or {
            "status": "completed", "candidate_ids": ["ATP-HTVS-X"], "evidence_generated": []
        }
        preview = self.engine.handle(self.session, "如果MMGBSA只能再算5个，帮我选")
        result = self.engine.confirm(self.session, preview["plan"]["plan_id"])
        self.assertEqual(result["plan_status"], "completed")
        self.assertEqual(len(calls), 1)
        self.assertEqual(self.store.session(self.session)["context"]["selected_candidate_set"], ["ATP-HTVS-X"])

    def test_action_registry_rejects_executable_text(self):
        registry = ActionRegistry(PROJECT)
        with self.assertRaises(ValueError):
            registry.execute(ACTION_QUERY_CANDIDATE, {"shell": "rm -rf /"})

    def test_vote_does_not_modify_ai_score(self):
        before = self.engine.actions.data.decision_ranking("balanced").copy()
        candidate = str(before.iloc[0]["compound_id"])
        self.store.vote("atp_synthase", candidate, "reviewer-a", "Low Priority")
        after = self.engine.actions.data.decision_ranking("balanced")
        self.assertEqual(before[["compound_id", "final_score"]].to_dict("records"), after[["compound_id", "final_score"]].to_dict("records"))

    def test_final_decision_keeps_snapshot_and_timeline(self):
        ranking = self.engine.actions.data.decision_ranking("balanced")
        candidate = str(ranking.iloc[0]["compound_id"])
        snapshot = self.engine.evidence_snapshot_hash(candidate)
        self.store.final_decision("atp_synthase", candidate, "Hold", "reviewer-a", "Await ATP assay", ranking.head(1).to_dict("records"), snapshot)
        timeline = self.store.timeline("atp_synthase", candidate)
        self.assertEqual(timeline[0]["event_type"], "final_human_decision")
        self.assertEqual(timeline[0]["payload"]["evidence_snapshot_hash"], snapshot)

    def test_wet_lab_queue_cannot_claim_unreviewed_completion(self):
        with self.assertRaises(ValueError):
            self.store.queue("atp_synthase", "X", "Completed", "assay", "reviewer-a")

    def test_current_queue_is_limited_to_planning_states(self):
        self.store.queue("atp_synthase", "X", "Proposed", "review future validation", "reviewer-a")
        with self.assertRaises(ValueError):
            self.store.queue("atp_synthase", "X", "Approved", "synthesis", "reviewer-a")

    def test_calculation_plan_is_blocked_without_fake_result(self):
        preview = self.engine.handle(self.session, "为NO-SUCH-CANDIDATE创建MMGBSA计算计划")
        self.assertEqual(preview["status"], "confirmation_required")
        with patch.object(self.engine.actions, "_product_job", return_value="job_blocked_test"):
            result = self.engine.confirm(self.session, preview["plan"]["plan_id"])
        self.assertEqual(result["status"], "blocked")
        self.assertFalse(result["scientific_values_generated"])
        self.assertIn("required_dependency", result)

    def test_confirmed_action_links_registered_job_and_provenance(self):
        jobs = self.engine.actions.data.jobs()
        real = jobs.loc[jobs["job_id"].notna()].iloc[0]
        real_job = str(real["job_id"])
        self.engine.actions.actions["ACTION_RUN_ACQUISITION"] = lambda args: {
            "status": "completed",
            "candidate_ids": [str(real["candidate_id"])],
            "job_ids": [real_job],
            "evidence_generated": [],
            "provenance": [{"source": "Calculation Job Registry", "job_id": real_job}],
        }
        preview = self.engine.handle(self.session, "如果MMGBSA只能再算1个，帮我选")
        result = self.engine.confirm(self.session, preview["plan"]["plan_id"])
        self.assertEqual(result["job_ids"], [real_job])
        linked = self.engine.linked_jobs(self.session)
        self.assertTrue(any(row["job_id"] == real_job for row in linked))


class StructuralAndBoundaryTests(unittest.TestCase):
    def test_phase17_1_registry_views_are_queryable(self):
        registry = ActionRegistry(PROJECT)
        consensus = registry.compare_protocol({"analysis_view": "consensus", "top_k": 3})
        impact = registry.compare_protocol({"analysis_view": "evidence_impact", "top_k": 3})
        conflict = registry.compare_protocol({"analysis_view": "disagreement", "top_k": 3})
        self.assertEqual(len(consensus["records"]), 3)
        self.assertEqual(len(impact["records"]), 3)
        self.assertEqual(len(conflict["records"]), 3)
        self.assertIn("MM/GBSA", impact["answer"])
        self.assertNotEqual(consensus["candidate_ids"], conflict["candidate_ids"])

    def test_candidate_and_evidence_views_include_real_open_mmgbsa(self):
        registry = ActionRegistry(PROJECT)
        master = registry.data.candidate_explorer_candidates()
        self.assertEqual(int(master["open_mmgbsa_deltaG"].notna().sum()), 30)
        evidence = registry.data.evidence_matrix()
        self.assertEqual(int(evidence["mmgbsa"].eq("available").sum()) >= 30, True)

    def test_registered_pose_and_missing_pose(self):
        registry = PoseRegistry(PROJECT)
        candidate = "ATP-HTVS-18A7589C7FB7"
        available = registry.lookup(candidate)
        self.assertEqual(available["status"], "available")
        self.assertEqual(available["protocol"], "vina_7p3w_v1")
        self.assertEqual(registry.lookup("NO-SUCH-CANDIDATE")["message"], "No registered pose available.")

    def test_read_only_dialogue_does_not_mutate_frozen_phase14(self):
        target = PROJECT / "results/phase14/full_library_vina_ranking.csv"
        before = digest(target)
        temp = tempfile.TemporaryDirectory()
        try:
            store = CollaborationStore(PROJECT, database=Path(temp.name) / "collaboration.sqlite3")
            engine = ConversationalOrchestrator(PROJECT, collaboration=store)
            session = engine.new_session("reviewer")
            result = engine.handle(session, "找出Glide和Vina分歧最大的10个")
            self.assertEqual(result["status"], "available")
        finally:
            temp.cleanup()
        self.assertEqual(before, digest(target))

    def test_unknown_evidence_remains_non_numeric(self):
        registry = ActionRegistry(PROJECT)
        matrix = registry.data.evidence_matrix()
        values = set(matrix.drop(columns=["compound_id", "source"]).astype(str).stack())
        self.assertIn("unknown", values)
        self.assertNotIn("0", values)

    def test_dbtl_is_computational_not_wet_lab_claim(self):
        temp = tempfile.TemporaryDirectory()
        try:
            store = CollaborationStore(PROJECT, database=Path(temp.name) / "collaboration.sqlite3")
            snapshot = ActivityService(PROJECT, store).dbtl_snapshot()
            self.assertEqual(snapshot["scope"], "computational DBTL / iterative decision loop")
            self.assertFalse(snapshot["wet_lab_closed_loop_claim"])
        finally:
            temp.cleanup()


if __name__ == "__main__":
    unittest.main()
