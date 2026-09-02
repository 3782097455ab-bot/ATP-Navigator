from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "src"))

from library_generation import ReconstructedLibraryGenerator
from workspace.state import file_hash
from workspace.tool_registry import contracts


class ReconstructedLibraryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        for relative in [
            "configs/library_generation/in2_reconstructed_v1.json",
            "configs/library_generation/building_blocks_v1.csv",
            "configs/library_generation/reaction_templates_v1.json",
            "configs/projects/ab_atp_synthase/vina_7p3w_v1/candidate_identity_manifest.csv",
        ]:
            target = self.root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(PROJECT / relative, target)
        self.engine = ReconstructedLibraryGenerator(
            self.root, "configs/library_generation/in2_reconstructed_v1.json"
        )

    def tearDown(self):
        self.temp.cleanup()

    def test_same_input_config_seed_same_hash(self):
        first = self.engine.generate(30, "determinism_a")
        second = self.engine.generate(30, "determinism_b")
        self.assertEqual(first["library_hash"], second["library_hash"])
        self.assertEqual(first["config_hash"], second["config_hash"])

    def test_checkpoint_resume_matches_uninterrupted(self):
        reference = self.engine.generate(40, "reference")
        paused = self.engine.generate(40, "resumed", stop_after_processed=11)
        self.assertEqual(paused["status"], "paused_checkpoint")
        completed = self.engine.generate(40, "resumed")
        self.assertEqual(completed["status"], "completed")
        self.assertEqual(reference["library_hash"], completed["library_hash"])

    def test_provenance_and_rejection_accounting(self):
        manifest = self.engine.generate(25, "provenance")
        library = pd.read_csv(self.root / manifest["library_file"], keep_default_na=False)
        required = {"compound_id", "parent_id", "canonical_smiles", "inchikey", "generation_method",
                    "attachment_site", "reaction_smarts", "building_block_id", "building_block_smiles",
                    "generator_config", "seed", "timestamp", "provenance_hash"}
        self.assertTrue(required.issubset(library.columns))
        self.assertTrue(library["provenance_hash"].str.fullmatch(r"[0-9a-f]{64}").all())
        self.assertFalse(library["canonical_smiles"].duplicated().any())
        self.assertEqual(manifest["counts"]["raw_processed"],
                         manifest["counts"]["accepted_unique"] + manifest["counts"]["rejected"])
        self.assertEqual(manifest["classification"], "reconstructed reproducible derivative library")
        self.assertFalse(manifest["historical_library_equivalence"])

    def test_backend_names_do_not_conflate_commercial_and_open_tools(self):
        tools = contracts()
        self.assertEqual(tools["vina"].protocol_id, "vina_7p3w_v1")
        self.assertNotEqual(tools["vina"].tool_id, tools["glide"].tool_id)
        self.assertEqual(tools["open_mmgbsa"].protocol_id, "open_mmgbsa_7p3w_v2")
        self.assertNotEqual(tools["open_mmgbsa"].tool_id, tools["prime_mmgbsa"].tool_id)

    def test_protected_models_unchanged(self):
        expected = json.loads((PROJECT / "results/phase14/model_hashes_before.json").read_text(encoding="utf-8"))
        actual = {name: file_hash(PROJECT / name) for name in expected}
        self.assertEqual(expected, actual)


if __name__ == "__main__":
    unittest.main()
