from __future__ import annotations

import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "src"))

from agent.structure_viewer import PoseRegistry
from app.data_adapter import ProjectData
from app.phase18b_views import deployment_info


class PublicReleaseTests(unittest.TestCase):
    def test_cloud_viewer_is_fail_closed(self):
        with patch.dict(os.environ, {"ATP_NAVIGATOR_DEPLOYMENT_MODE": "cloud_viewer"}, clear=False):
            info = deployment_info(PROJECT)
        self.assertEqual(info["mode"], "cloud_viewer")
        self.assertFalse(info["can_execute_local_tools"])
        self.assertIn("ephemeral", info["collaboration_persistence"])

    def test_committed_cloud_pose_has_registered_hashes(self):
        manifest = json.loads((PROJECT / "data/cloud_demo/pose_manifest.json").read_text(encoding="utf-8"))
        result = PoseRegistry(PROJECT).lookup(manifest["candidate_id"])
        self.assertEqual(result["status"], "available")
        self.assertEqual(result["protocol"], "vina_7p3w_v1")
        self.assertEqual(result["pose_hash"], manifest["pose_sha256"])

    def test_benchmark_registry_is_catalog_only(self):
        data = ProjectData(PROJECT)
        registry = data.benchmark_registry()
        self.assertEqual(len(registry), 26)
        self.assertTrue(registry["registry_type"].eq("benchmark_metadata_catalog").all())
        self.assertTrue(registry["execution_status"].eq("not_run").all())
        self.assertFalse(registry["training_allowed"].astype(bool).any())
        self.assertEqual(
            data.benchmark_status()["Part1 experimental benchmark records"],
            "available_general_binding_only",
        )

    def test_member2_audit_preserves_raw_structure(self):
        frame = ProjectData(PROJECT).project / "data/external/integrated/member2_gn_mic_audit.csv"
        self.assertTrue(frame.is_file())
        import pandas as pd

        audit = pd.read_csv(frame, dtype=str, keep_default_na=False)
        self.assertEqual(len(audit), 310)
        self.assertTrue(audit["raw_smiles"].ne("").all())
        self.assertTrue(audit["provenance"].str.contains("Member2_GN_antibacterial_week1.xlsx", regex=False).all())
        self.assertTrue(audit["training_status"].eq("pending_endpoint_and_provenance_review").all())


if __name__ == "__main__":
    unittest.main()
