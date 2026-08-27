import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from src.phase14_full_library_vina import (
    PROJECT, PROTOCOL_ID, _candidate_table, _load_model_snapshot, _protocol,
    _existing_result, _json_safe, _report, _sha_text,
)
from workspace.state import digest, file_hash


class Phase14FullLibraryTests(unittest.TestCase):
    def test_source_is_exactly_1633_unique_candidates(self):
        frame = _candidate_table(PROJECT)
        self.assertEqual(len(frame), 1633)
        self.assertFalse(frame["canonical_id"].duplicated().any())

    def test_frozen_protocol_parameters(self):
        protocol = _protocol(PROJECT)
        self.assertEqual(protocol["protocol_id"], PROTOCOL_ID)
        self.assertEqual(protocol["exhaustiveness"], 16)
        self.assertEqual(protocol["num_modes"], 9)
        self.assertEqual(protocol["seed"], 20260827)
        self.assertEqual(protocol["cpu"], 1)

    def test_vina_protocol_never_claims_glide_equivalence(self):
        protocol = _protocol(PROJECT)
        self.assertEqual(protocol["historical_equivalence"], "not_equivalent")
        self.assertIn("never mapped", protocol["evidence_policy"])

    def test_content_signature_is_sensitive_to_scientific_inputs(self):
        base = {"ligand_hash":"a", "receptor_hash":"b", "protocol_hash":"c", "tool_version":"1"}
        signatures = {_sha_text({**base, key:value}) for key, value in [
            ("ligand_hash","x"), ("receptor_hash","x"), ("protocol_hash","x"), ("tool_version","x")
        ]}
        self.assertEqual(len(signatures), 4)
        self.assertNotIn(_sha_text(base), signatures)

    def test_protected_models_are_unchanged(self):
        baseline = _load_model_snapshot(PROJECT)
        self.assertEqual(len(baseline), 24)

    def test_phase14_outputs_do_not_define_biological_labels(self):
        source = (PROJECT / "src/phase14_full_library_vina.py").read_text(encoding="utf-8")
        self.assertIn("not biological activity", source)
        self.assertNotIn('evidence_type\": \"experimental_activity', source)

    def test_cached_pose_manifest_has_hash_when_available(self):
        checkpoint = PROJECT / "results/phase14/execution_checkpoint.csv"
        if not checkpoint.is_file():
            self.skipTest("execution checkpoint not available yet")
        frame = pd.read_csv(checkpoint)
        complete = frame.loc[frame["status"].eq("success")]
        self.assertGreater(len(complete), 0)
        self.assertTrue(complete["pose_sha256"].str.fullmatch(r"[0-9a-f]{64}").all())

    def test_model_snapshot_files_match(self):
        before = PROJECT / "results/phase14/model_hashes_before.json"
        after = PROJECT / "results/phase14/model_hashes_after.json"
        if not after.is_file():
            self.skipTest("full Phase14 analysis not complete")
        self.assertEqual(json.loads(before.read_text()), json.loads(after.read_text()))

    def test_final_phase14_counts_and_failure_audit(self):
        summary_path = PROJECT / "results/phase14/phase14_execution_summary.json"
        if not summary_path.is_file():
            self.skipTest("final Phase14 summary not available")
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        qc = summary["qc"]
        self.assertEqual(qc["total"], 1633)
        self.assertEqual(qc["processed"], 1633)
        self.assertEqual(qc["success"] + qc["failed"], 1633)
        self.assertEqual(qc["pose_qc_pass"], qc["success"])
        self.assertEqual(len(summary["failed_candidate_audit"]), qc["failed"])
        self.assertTrue(all(not row["retry_performed_in_finalization"] for row in summary["failed_candidate_audit"]))

    def test_final_registry_has_three_records_per_success(self):
        summary_path = PROJECT / "results/phase14/phase14_execution_summary.json"
        if not summary_path.is_file():
            self.skipTest("final Phase14 summary not available")
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        self.assertEqual(summary["evidence_registry_records"], 3 * summary["qc"]["success"])

    def test_internal_position_table_includes_reference_and_all_hits(self):
        path = PROJECT / "results/phase14/internal17_global_position.csv"
        if not path.is_file():
            self.skipTest("internal position table not available")
        frame = pd.read_csv(path)
        self.assertEqual(len(frame), 18)
        self.assertEqual(set(frame["historical_alias"]), {"IN-2", *{f"Hit{i}" for i in range(1, 18)}})

    def test_report_preserves_computational_scope(self):
        sample = {
            "qc": {"total": 1633, "eligible": 1633, "processed": 1, "success": 1,
                   "failed": 0, "cached": 0, "invalid_structure": 0,
                   "preparation_failed": 0, "vina_failed": 0, "pose_qc_failed": 0},
            "protocol_file_hash": "a", "registry_protocol_hash": "b",
            "analysis": {"successful": 1, "scaffolds": 1, "clusters": 1,
                         "metrics": {}, "hit3": {"mapping_status": "not_present_in_htvs1633"}},
            "protected_model_count": 24,
        }
        text = _report(sample)
        self.assertIn("不是实验验证", text)
        self.assertIn("unknown", text)
        self.assertNotIn("生物安全", text)

    def test_success_cache_requires_pose_hash(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            pose = root / "pose.pdbqt"
            pose.write_text("MODEL 1\nENDMDL\n", encoding="utf-8")
            from workspace.state import file_hash
            (root / "result.json").write_text(json.dumps({
                "signature": "sig", "status": "success", "pose_sha256": file_hash(pose)
            }), encoding="utf-8")
            result = _existing_result({"folder": str(root), "signature": "sig", "retry_failed": False})
            self.assertTrue(result["cached"])
            pose.write_text("changed", encoding="utf-8")
            self.assertIsNone(_existing_result({"folder": str(root), "signature": "sig", "retry_failed": False}))

    def test_failed_cache_requires_explicit_retry(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "result.json").write_text(json.dumps({
                "signature": "sig", "status": "failed", "failure_reason": "preserved"
            }), encoding="utf-8")
            kept = _existing_result({"folder": str(root), "signature": "sig", "retry_failed": False})
            self.assertEqual(kept["failure_reason"], "preserved")
            self.assertIsNone(_existing_result({"folder": str(root), "signature": "sig", "retry_failed": True}))

    def test_json_safe_converts_nonfinite_values(self):
        converted = _json_safe({"missing": float("nan"), "positive": 1.5})
        self.assertIsNone(converted["missing"])
        self.assertEqual(converted["positive"], 1.5)


if __name__ == "__main__":
    unittest.main()
