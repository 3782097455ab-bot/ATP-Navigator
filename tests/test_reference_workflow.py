from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "src"))

from reference_workflow.pipeline import ReferencePipeline
from reference_workflow.stages.decision import run_decision
from reference_workflow.stages.molecular_filtering import run_filter
from reference_workflow.stages.refinement import _wsl_path
from reference_workflow.util import sha256_file, stable_hash


class ReferenceWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config_path = PROJECT / "configs/in2_7p3w_reference.yaml"
        cls.config = json.loads(cls.config_path.read_text(encoding="utf-8"))

    def test_scientific_route_names_are_not_conflated(self):
        self.assertFalse(self.config["generation"]["historical_library_equivalence"])
        self.assertFalse(self.config["filtering"]["historical_quickprop_equivalence"])
        self.assertFalse(self.config["docking"]["historical_glide_equivalence"])
        self.assertFalse(self.config["mmgbsa"]["historical_prime_equivalence"])

    def test_config_is_stable_json_compatible_yaml(self):
        self.assertEqual(stable_hash(self.config), ReferencePipeline(PROJECT, self.config_path).config_hash)

    def test_three_modes_share_one_controller(self):
        self.assertEqual(set(self.config["modes"]), {"smoke", "development", "full"})
        self.assertEqual([self.config["modes"][key]["library_size"] for key in ["smoke", "development", "full"]], [100, 1000, 100000])

    def test_cached_100k_hash_is_the_audited_hash(self):
        manifest = json.loads((PROJECT / "workspace_local/library_generation/in2_reconstructed_100k_v1/manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["library_hash"], "2af8186dde533bf14bef2c38cd929f2c0bd7756dc20db0bd4f67936a499458ba")
        self.assertEqual(manifest["config_hash"], "0edaacdb8a4b66f6f28108efa09d111887870a2ef58b4953eddeaca48e82dd6b")
        self.assertFalse(manifest["historical_library_equivalence"])

    def test_frozen_filter_is_deterministic_and_auditable(self):
        source = PROJECT / "workspace_local/library_generation/in2_smoke_100_v1/library.csv"
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder)
            first = run_filter(source, out, self.config["filtering"], "test_library_hash")
            second = run_filter(source, out, self.config["filtering"], "test_library_hash")
            self.assertEqual(first["filter_hash"], second["filter_hash"])
            self.assertEqual(first["accepted_count"], 7)
            self.assertTrue(second["cached"])
            rejected = pd.read_csv(out / "filter_rejections.csv")
            self.assertTrue({"reason", "threshold", "raw_value", "rationale", "kind"}.issubset(rejected.columns))

    def test_missing_mmgbsa_returns_insufficient_evidence_not_fake_score(self):
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder)
            acquisition = out / "acquisition.csv"
            mmgbsa = out / "mmgbsa.csv"
            pd.DataFrame([{"candidate_id": "X", "canonical_smiles": "CC", "status": "success", "vina_affinity": -7.0}]).to_csv(acquisition, index=False)
            pd.DataFrame([{"candidate_id": "X", "canonical_smiles": "CC", "status": "failed", "open_mmgbsa_deltaG": None}]).to_csv(mmgbsa, index=False)
            summary = run_decision(PROJECT, acquisition, mmgbsa, out / "decision", self.config["decision"], "test-empty-run")
            self.assertEqual(summary["status"], "insufficient_evidence")
            self.assertEqual(summary["output_count"], 0)

    def test_decision_accepts_library_compound_id_contract_without_guessing_identity(self):
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder)
            acquisition = out / "acquisition.csv"
            mmgbsa = out / "mmgbsa.csv"
            pd.DataFrame([{"compound_id": "X", "canonical_smiles": "CC", "status": "success", "vina_affinity": -7.0}]).to_csv(acquisition, index=False)
            pd.DataFrame([{"candidate_id": "X", "canonical_smiles": "CC", "status": "failed", "open_mmgbsa_deltaG": None}]).to_csv(mmgbsa, index=False)
            summary = run_decision(PROJECT, acquisition, mmgbsa, out / "decision", self.config["decision"], "test-compound-id-contract")
            self.assertEqual(summary["status"], "insufficient_evidence")
            self.assertEqual(summary["output_count"], 0)

    def test_wsl_path_conversion(self):
        self.assertEqual(_wsl_path(Path("D:/tiaozhansai/ATP-Navigator/x.txt")), "/mnt/d/tiaozhansai/ATP-Navigator/x.txt")

    def test_protected_model_hashes_are_unchanged(self):
        expected = json.loads((PROJECT / "results/phase14/model_hashes_before.json").read_text(encoding="utf-8"))
        self.assertEqual(len(expected), 24)
        observed = {name: sha256_file(PROJECT / name) for name in expected}
        self.assertEqual(expected, observed)

    def test_decision_weights_are_transparent(self):
        self.assertAlmostEqual(sum(self.config["decision"]["weights"].values()), 1.0)
        self.assertIn("binding", self.config["decision"]["weights"])

    def test_filter_manifest_is_frozen_before_run(self):
        self.assertTrue(self.config["filtering"]["rules_frozen_before_reference_runs"])
        self.assertTrue(all("rationale" in rule and "kind" in rule for rule in self.config["filtering"]["rules"]))

    def test_full_run_resource_gate_is_explicit_and_not_a_failure(self):
        path = PROJECT / "runs/in2-7p3w-full-reference-v1/manifests/run_manifest.json"
        if not path.is_file():
            self.skipTest("full reference run manifest not packaged")
        manifest = json.loads(path.read_text(encoding="utf-8"))
        docking = next(row for row in manifest["stages"] if row["stage_id"] == "docking")
        self.assertEqual(manifest["library_hash"], "2af8186dde533bf14bef2c38cd929f2c0bd7756dc20db0bd4f67936a499458ba")
        self.assertEqual(docking["status"], "blocked_by_resource_gate")
        self.assertEqual(docking["output_count"], 0)
        self.assertEqual(manifest["failed_jobs"], 0)
        self.assertEqual(manifest["filtered_out_candidates"], 92735)

    def test_filter_protocol_identity_is_separate_from_library_execution_hash(self):
        path = PROJECT / "runs/in2-7p3w-full-reference-v1/filtering/filter_manifest.json"
        if not path.is_file():
            self.skipTest("full filter manifest not packaged")
        manifest = json.loads(path.read_text(encoding="utf-8"))
        self.assertNotEqual(manifest["filter_protocol_hash"], manifest["filter_hash"])
        self.assertEqual(manifest["input_count"], 100000)
        self.assertEqual(manifest["accepted_count"], 7265)

    def test_full_run_manifest_artifacts_are_hash_verified(self):
        path = PROJECT / "runs/in2-7p3w-full-reference-v1/manifests/run_manifest.json"
        if not path.is_file():
            self.skipTest("full reference run manifest not packaged")
        manifest = json.loads(path.read_text(encoding="utf-8"))
        run_dir = path.parents[1]
        missing = []
        mismatched = []
        for relative, expected in manifest["artifact_hashes"].items():
            artifact = run_dir / relative
            if not artifact.is_file():
                missing.append(relative)
            elif sha256_file(artifact) != expected:
                mismatched.append(relative)
        self.assertEqual(missing, [])
        self.assertEqual(mismatched, [])

    def test_run_manifest_uses_portable_report_paths(self):
        path = PROJECT / "runs/in2-7p3w-full-reference-v1/manifests/run_manifest.json"
        if not path.is_file():
            self.skipTest("full reference run manifest not packaged")
        manifest = json.loads(path.read_text(encoding="utf-8"))
        self.assertTrue(all(not Path(value).is_absolute() for value in manifest["reports"]))
        self.assertTrue(all(not Path(value).is_absolute() for value in manifest["screening_funnel"].values()))

    def test_resume_audit_records_checkpoint_without_changing_science_config(self):
        with tempfile.TemporaryDirectory() as folder:
            pipeline = ReferencePipeline(PROJECT, self.config_path)
            run_dir = Path(folder)
            (run_dir / "manifests").mkdir(parents=True)
            checkpoint = {"status": "paused_at_declared_stage_boundary", "stages": {"library_generation": {}}}
            pipeline._record_invocation(run_dir, checkpoint, "molecular_filtering", False)
            history = json.loads((run_dir / "manifests/resume_history.json").read_text(encoding="utf-8"))
            self.assertEqual(history[0]["status_before_invocation"], "paused_at_declared_stage_boundary")
            self.assertEqual(history[0]["stages_already_checkpointed"], ["library_generation"])
            self.assertFalse(history[0]["retry_failed"])
            self.assertEqual(pipeline.config_hash, stable_hash(self.config))


if __name__ == "__main__":
    unittest.main()
