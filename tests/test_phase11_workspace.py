"""Temporary synthetic fixtures are software tests only, never research results."""
from __future__ import annotations

import csv
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from experimental_feedback import FIELDS, FeedbackStore, write_csv_new
from feedback_evaluator import evaluate
from input_processor import CandidateInputProcessor
from navigator_pipeline import NavigatorPipeline
from research_workspace import ResearchWorkspace
from workspace_io import file_hash, read_json, within
from workspace_llm_adapter import OpenAIRouter


class FeedbackTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="atp_test_only_")
        self.root = Path(self.temp.name)
        self.incoming = self.root / "data/experimental/incoming"
        self.incoming.mkdir(parents=True)
        self.evidence = self.incoming / "synthetic_test_fixture.txt"
        self.evidence.write_text("SYNTHETIC SOFTWARE TEST ONLY. NOT AN EXPERIMENT.", encoding="utf-8")
        self.store = FeedbackStore(self.root)
        self.base = dict(zip(FIELDS, ["test-1", "TEST-ETHANOL", "CCO", "test_organism", "test_strain",
            "whole_cell", "MIC", "4", "=", "ug/mL", "test_growth", "rep-1", "TEST_ONLY_protocol",
            "2026-01-01", "TEST_ONLY", "TEST_ONLY_not_scientific_evidence", "pass", "experimental",
            "data/experimental/incoming/synthetic_test_fixture.txt", file_hash(self.evidence), "development"]))

    def tearDown(self):
        self.temp.cleanup()

    def input(self, rows):
        path = self.incoming / ("test_" + str(len(list(self.incoming.glob("*.csv")))) + ".csv")
        write_csv_new(path, rows, FIELDS)
        return path

    def test_empty_and_pending_do_not_create_labels(self):
        pending = {**self.base, "activity_value": "", "evidence_type": "experimental_pending"}
        result = self.store.ingest(self.input([pending]))
        self.assertEqual(result["counts"], {"pending": 1})
        snapshot = self.store.snapshot()
        self.assertEqual(snapshot["records"], 0)
        self.assertFalse(snapshot["promotion_allowed"])

    def test_review_required_and_immutable(self):
        batch = self.store.ingest(self.input([self.base]))
        self.assertEqual(self.store.snapshot()["records"], 0)
        self.store.review(batch["batch_id"], "human_test_reviewer", ["test-1"])
        self.assertEqual(self.store.snapshot()["records"], 1)
        self.assertEqual(self.store.evidence_for("TEST-ETHANOL")[0]["record_id"], "test-1")
        with self.assertRaises(FileExistsError):
            self.store.review(batch["batch_id"], "reviewer2", ["test-1"])

    def test_bad_provenance_and_fake_type_quarantined(self):
        for field, value in [("evidence_sha256", "wrong"), ("evidence_type", "computational"),
                             ("activity_value", "inf"), ("unit", "kcal/mol"), ("experimental_date", "2099-01-01")]:
            with self.subTest(field=field):
                rows, _ = self.store.validate(self.input([{**self.base, field: value}]))
                self.assertEqual(rows[0]["status"], "quarantined")

    def test_censored_not_exact_training_label(self):
        batch = self.store.ingest(self.input([{**self.base, "comparator": ">"}]))
        self.store.review(batch["batch_id"], "test_reviewer", ["test-1"])
        summary = self.store.snapshot()
        self.assertEqual(summary["strata"][0]["eligible_structures"], 0)

    def test_tasks_units_and_holdout_remain_separate(self):
        holdout = {**self.base, "record_id": "test-2", "replicate_id": "rep-2", "dataset_role": "holdout"}
        atp = {**self.base, "record_id": "test-3", "activity_type": "ATP_IC50", "target": "ATP synthase", "unit": "nM", "compound_id": "TEST-PROPANOL", "canonical_smiles": "CCCO"}
        batch = self.store.ingest(self.input([self.base, holdout, atp]))
        self.store.review(batch["batch_id"], "test_reviewer", ["test-1", "test-2", "test-3"])
        summary = self.store.snapshot()
        rows = pd.read_csv(self.store.root / "snapshots" / summary["snapshot_id"] / "reviewed_records.csv")
        self.assertFalse(rows.loc[rows.record_id.eq("test-1"), "training_eligible"].iloc[0])
        self.assertEqual(rows.task.nunique(), 2)

    def test_duplicate_import_does_not_inflate_n(self):
        path = self.input([self.base])
        for _ in range(2):
            batch = self.store.ingest(path)
            self.store.review(batch["batch_id"], "test_reviewer", ["test-1"])
        self.assertEqual(self.store.snapshot()["records"], 1)

    def test_source_mutation_is_detected(self):
        batch = self.store.ingest(self.input([self.base]))
        path = self.store.root / "imports" / batch["batch_id"] / "raw.csv"
        path.write_text("synthetic mutation", encoding="utf-8")
        with self.assertRaises(ValueError):
            self.store.review(batch["batch_id"], "test_reviewer", ["test-1"])

    def test_empty_evaluation_is_not_validation_pass(self):
        summary = self.store.snapshot()
        ranking = self.root / "rank.csv"
        pd.DataFrame(columns=["canonical_smiles", "rank", "final_score", "docking_score"]).to_csv(ranking, index=False)
        result = evaluate(self.store.root / "snapshots" / summary["snapshot_id"], ranking, self.root / "eval")
        self.assertEqual(result["status"], "empty_no_matched_reviewed_holdout")
        self.assertFalse(result["training_performed"])

    def test_nonempty_evaluation_uses_only_same_endpoint_holdout(self):
        rows, ranks = [], []
        for i, smiles in enumerate(["CCO", "CCCO", "CCCCO", "CCCCCO", "CCCCCCO"], 1):
            rows.append({**self.base, "record_id": f"test-{i}", "compound_id": f"TEST-{i}",
                         "canonical_smiles": smiles, "activity_value": str(i), "dataset_role": "holdout"})
            ranks.append({"canonical_smiles": smiles, "rank": i, "final_score": 100-i, "docking_score": i})
        batch = self.store.ingest(self.input(rows))
        self.store.review(batch["batch_id"], "test_reviewer", [r["record_id"] for r in rows])
        summary = self.store.snapshot()
        ranking = self.root / "rank.csv"
        pd.DataFrame(ranks).to_csv(ranking, index=False)
        result = evaluate(self.store.root / "snapshots" / summary["snapshot_id"], ranking, self.root / "eval")
        self.assertEqual(len(result["metrics"]), 2)
        self.assertAlmostEqual(result["metrics"][1]["spearman"], 1.0)
        self.assertIsNone(result["metrics"][1]["rmse"])
        self.assertEqual(result["prospective_validity"], "not_established")


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="atp_workspace_test_")
        self.workspace = ResearchWorkspace(ROOT, Path(self.temp.name) / "runtime")
        self.session = self.workspace.create_session(ROOT / "results/demo/demo_input.csv")

    def tearDown(self):
        self.temp.cleanup()

    def test_unknown_text_does_not_trigger_work(self):
        result = self.workspace.chat(self.session, "把所有数据弄好随便训练")
        self.assertEqual(result["status"], "clarification_required")

    def test_disallowed_tool_and_path(self):
        with self.assertRaises(ValueError):
            self.workspace.dispatch(self.session, "train_model", {})
        with self.assertRaises(ValueError):
            within(ROOT, "../secret.csv")
        with self.assertRaises(ValueError):
            self.workspace.dispatch(self.session, "ingest_feedback", {"path": ".git/config"})

    def test_confirmation_and_replay_execute_once(self):
        proposal = self.workspace.chat(self.session, "按 balanced 排序")
        self.assertEqual(proposal["status"], "confirmation_required")
        with patch.object(self.workspace, "_execute", return_value={"test_only": True}) as execute:
            first = self.workspace.confirm(self.session, proposal["proposal_id"])
            self.workspace.confirm(self.session, proposal["proposal_id"])
            self.assertEqual(first["status"], "completed")
            self.assertEqual(execute.call_count, 1)

    def test_confirmation_cannot_cross_sessions(self):
        proposal = self.workspace.chat(self.session, "按 balanced 排序")
        other = self.workspace.create_session(ROOT / "results/demo/demo_input.csv")
        with self.assertRaises(ValueError):
            self.workspace.confirm(other, proposal["proposal_id"])

    def test_feedback_evaluation_without_frozen_run_is_empty(self):
        proposal = self.workspace.chat(self.session, "评价反馈")
        self.assertEqual(proposal["tool"], "evaluate_feedback")
        result = self.workspace.confirm(self.session, proposal["proposal_id"])
        self.assertEqual(result["result"]["status"], "empty_waiting_for_snapshot_and_frozen_ranking")

    def test_history_persists_and_knowledge_is_source_backed(self):
        self.workspace.chat(self.session, "查资料 ATP")
        reopened = ResearchWorkspace(ROOT, self.workspace.root)
        self.assertTrue(any(e["kind"] == "tool_result" for e in reopened.history(self.session)))
        response = reopened.chat(self.session, "查资料 abaucin")
        self.assertTrue(response["sources"])
        self.assertTrue(all(c["url"].startswith("https://") for c in response["sources"]))

    def test_llm_disabled_without_consent_and_rejects_unknown_tools(self):
        with self.assertRaises(ValueError):
            OpenAIRouter()
        with self.assertRaises(ValueError):
            OpenAIRouter.parse_response({"output": [{"type": "function_call", "name": "propose_workspace_tool",
                "arguments": json.dumps({"tool": "shell", "argument": "train"})}]})
        result = OpenAIRouter.parse_response({"output": [{"type": "function_call", "name": "propose_workspace_tool",
                "arguments": json.dumps({"tool": "run_navigation", "argument": "balanced"})}]})
        self.assertEqual(result, ("run_navigation", {"profile": "balanced"}))


class InputGuardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.processor = CandidateInputProcessor(ROOT)
        cls.pipeline = NavigatorPipeline(ROOT)

    def test_reserved_features_cannot_override_structures(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            frame = pd.read_csv(ROOT / "results/demo/demo_input.csv").head(1)
            frame.loc[0, "literature_features"] = json.dumps({"desc_mol_wt": 999999, "model_score": 999999, "compound_id": 7})
            frame.to_csv(tmp / "in.csv", index=False)
            result = self.processor.process(tmp / "in.csv", tmp / "out.csv")
            self.assertLess(result.iloc[0]["desc_mol_wt"], 999999)
            self.assertEqual(result.iloc[0]["compound_id"], frame.iloc[0]["compound_id"])

    def test_experiments_identity_and_nonfinite_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            for field, value in [("experimental_MIC", "4"), ("SMILES", "CCO"), ("docking_score", "inf")]:
                frame = pd.read_csv(ROOT / "results/demo/demo_input.csv", dtype=str).head(1)
                frame.loc[0, field] = value
                frame.to_csv(tmp / "in.csv", index=False)
                with self.assertRaises(ValueError):
                    self.processor.process(tmp / "in.csv", tmp / "out.csv")

    def test_duplicate_structure_does_not_shift_other_scores(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            processed = self.processor.process(ROOT / "results/demo/demo_input.csv", tmp / "processed.csv")
            original, _ = self.pipeline._rank(processed, "balanced")
            duplicate = processed.iloc[[0]].copy()
            duplicate["compound_id"] = "TEST-DUPLICATE"
            duplicate["duplicate_structure_of"] = processed.iloc[0]["compound_id"]
            changed, _ = self.pipeline._rank(pd.concat([processed, duplicate], ignore_index=True), "balanced")
            expected = original.set_index("compound_id").final_score.sort_index()
            actual = changed.loc[changed.compound_id.ne("TEST-DUPLICATE")].set_index("compound_id").final_score.sort_index()
            pd.testing.assert_series_equal(expected, actual)

    def test_cross_process_determinism(self):
        with tempfile.TemporaryDirectory() as tmp:
            hashes = []
            for seed in ["11", "77"]:
                output = Path(tmp) / seed
                subprocess.run([sys.executable, str(ROOT / "src/navigator_pipeline.py"), "--input",
                                str(ROOT / "results/demo/demo_input.csv"), "--profile", "balanced",
                                "--output-dir", str(output)], env={**os.environ, "PYTHONHASHSEED": seed},
                               check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=120)
                hashes.append((file_hash(output / "processed_candidate_table.csv"), file_hash(output / "final_navigation_report.csv")))
            self.assertEqual(hashes[0], hashes[1])


if __name__ == "__main__":
    unittest.main()
