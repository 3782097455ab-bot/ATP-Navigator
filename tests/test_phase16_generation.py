from __future__ import annotations

import json,sys,tempfile,unittest
from pathlib import Path
import pandas as pd

PROJECT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(PROJECT/"src"))
from generation.query_service import answer
from research_workspace import ResearchWorkspace


class Phase16GenerationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root=PROJECT/"results/phase16";cls.root=root
        cls.registry=pd.read_csv(root/"generated_candidate_registry.csv",keep_default_na=False)
        cls.qc=pd.read_csv(root/"generation_qc.csv",keep_default_na=False)
        cls.space=pd.read_csv(root/"generated_chemical_space.csv")
        cls.pool=pd.read_csv(root/"generated_screening_pool.csv")
        cls.vina=pd.read_csv(root/"generated_vina_results.csv")
        cls.panel=pd.read_csv(root/"generated_acquisition_panel_v1.csv")
        cls.summary=json.loads((root/"phase16_summary.json").read_text())

    def test_small_generation_cap_and_counts(self):
        self.assertEqual(len(self.qc),400);self.assertEqual(len(self.registry),360);self.assertLessEqual(len(self.registry),1000)
        self.assertEqual(int(self.qc["qc_status"].eq("accepted").sum()),360)

    def test_registry_identity_and_provenance_contract(self):
        required={"generated_candidate_id","parent_candidate_id","parent_structure_hash","generation_method",
                  "generator_version","generator_config","random_seed","reaction_or_operation","canonical_smiles",
                  "inchikey","murcko_scaffold","generation_timestamp","provenance_hash"}
        self.assertTrue(required.issubset(self.registry.columns));self.assertFalse(self.registry["canonical_smiles"].duplicated().any())
        self.assertTrue(self.registry["generated_candidate_id"].str.startswith("ATP-GEN-").all())

    def test_hit3_identity_boundary_is_preserved(self):
        rows=self.registry.loc[self.registry["parent_alias"].eq("Hit3")]
        self.assertTrue(rows["parent_htvs_identity"].eq("unresolved").all())

    def test_no_silent_qc_deletion(self):
        rejected=self.qc.loc[self.qc["qc_status"].eq("rejected")]
        self.assertTrue(rejected["rejection_reason"].astype(bool).all());self.assertEqual(len(rejected),40)

    def test_historical_duplicate_check(self):
        self.assertEqual(int(self.qc["rejection_reason"].eq("historical_htvs1633_duplicate").sum()),0)

    def test_screening_then_real_vina(self):
        self.assertEqual(len(self.pool),120);self.assertEqual(len(self.vina),120)
        self.assertTrue(self.vina["status"].eq("success").all());self.assertTrue(self.vina["pose_qc"].eq("pass").all())
        self.assertTrue(self.vina["protocol_id"].eq("vina_7p3w_v1").all())
        self.assertTrue(self.vina["pose_path"].map(lambda value:(PROJECT/value).is_file()).all())

    def test_generated_evidence_is_separate(self):
        self.assertTrue(self.vina["generated_candidate_id"].str.startswith("ATP-GEN-").all())
        self.assertFalse(self.vina["generated_candidate_id"].str.startswith("ATP-HTVS-").any())

    def test_acquisition_is_multiobjective(self):
        self.assertEqual(len(self.panel),30);self.assertEqual(self.panel["generated_candidate_id"].nunique(),30)
        for column in ["vina_component","property_tractability","novelty_vs_htvs1633","internal_diversity_contribution","warning_count","scaffold_retention"]:
            self.assertIn(column,self.panel.columns)

    def test_generator_did_not_collapse(self):
        self.assertFalse(self.summary["chemical_space"]["generator_collapse"])
        self.assertGreater(self.summary["chemical_space"]["internal_diversity"],.15)

    def test_unavailable_backends_generate_zero(self):
        status=json.loads((self.root/"generator_backend_status.json").read_text())
        for row in status["backends"]:
            if row["status"]!="available": self.assertEqual(row["generated"],0)

    def test_query_service_lineage_and_qc(self):
        candidate=self.registry.iloc[0]["generated_candidate_id"]
        self.assertEqual(answer(PROJECT,f"{candidate}从谁生成？")["candidate"],candidate)
        self.assertEqual(answer(PROJECT,"哪些生成分子与历史1633最不相似？")["criterion"],"lowest nearest HTVS-1633 Tanimoto")
        self.assertTrue(answer(PROJECT,"哪些generated candidates值得进一步做MM/GBSA？")["candidates"])
        self.assertTrue(answer(PROJECT,"RAW-00361为什么被淘汰？")["qc"])

    def test_workspace_routes_generation_query(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace=ResearchWorkspace(PROJECT,Path(tmp)/"workspace")
            session=workspace.create_session(PROJECT/"results/demo/demo_input.csv")
            result=workspace.chat(session,"哪些生成分子与历史1633最不相似？")
            self.assertEqual(result["criterion"],"lowest nearest HTVS-1633 Tanimoto")

    def test_models_remain_frozen(self):
        before=json.loads((PROJECT/"results/phase14/model_hashes_before.json").read_text())
        after=json.loads((PROJECT/"results/phase14/model_hashes_after.json").read_text())
        self.assertEqual(len(before),24);self.assertEqual(before,after);self.assertFalse(self.summary["training"])


if __name__=="__main__":unittest.main()
