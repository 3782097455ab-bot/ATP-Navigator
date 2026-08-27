"""Phase 13 protocol, evidence-isolation and audit acceptance tests."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))

from workspace.state import State,file_hash,now,encode
from workspace.workflow_service import project_candidate_docking_evidence,project_vina_glide_disagreements
from tools.vina_adapter import parse_vina_pose


class Phase13ProtocolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder=ROOT/'configs/projects/ab_atp_synthase/vina_7p3w_v1'
        cls.protocol=json.loads((cls.folder/'vina_protocol.json').read_text(encoding='utf-8'))
        cls.site=json.loads((cls.folder/'binding_site_manifest.json').read_text(encoding='utf-8'))
        cls.provenance=json.loads((cls.folder/'protocol_provenance.json').read_text(encoding='utf-8'))

    def test_historical_site_and_receptor_are_hash_pinned(self):
        self.assertEqual(self.protocol['target_reference'],'7P3W')
        self.assertEqual(self.protocol['relation_to_historical_glide'],'derived_from_historical_site')
        self.assertEqual(self.protocol['historical_equivalence'],'not_equivalent')
        receptor=ROOT/self.protocol['receptor']['path']
        self.assertEqual(file_hash(receptor),self.protocol['receptor']['sha256'])

    def test_box_is_explicit_not_guessed(self):
        box=self.protocol['box']
        self.assertEqual(box['center'],[198.147968145161,182.436946193548,155.933369258065])
        self.assertEqual(box['size'],[25.9912574278463]*3)
        self.assertIn('VSW.maegz',self.site['box_source']['file'])

    def test_reference_pose_is_hash_pinned(self):
        reference=self.protocol['reference_poses']['ATP-REF-IN2']
        self.assertEqual(file_hash(ROOT/reference['path']),reference['sha256'])
        self.assertIn('historical IN-2 pose',self.provenance['sources'][2]['supports'])
        self.assertIn('No Vina value is an activity label',self.provenance['claim_boundary'])

    def test_open_score_cannot_claim_glide_equivalence(self):
        self.assertIn('open_toolchain',self.protocol['protocol_kind'])
        self.assertIn('never mapped to Model v3 Glide features',self.protocol['evidence_policy'])
        self.assertIn('not Glide-equivalent',self.site['non_equivalence_statement'])


class Phase13RegistryQueryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.state=State(self.root);self.project='P13_TEST';self.state.project_id(self.project)
        self.state.candidate(self.project,'C1','CCO','Hit3');self.state.candidate(self.project,'C2','CCN','Hit2')
        self.vina={'protocol_id':'VINA_TEST','tool_family':'vina'}
        self.glide={'protocol_id':'GLIDE_TEST','tool_family':'glide'}
        self.state.freeze_protocol(self.vina);self.state.freeze_protocol(self.glide)
        self._record('C1','vina_affinity',-8.0,'vina',self.vina)
        self._record('C2','vina_affinity',-6.0,'vina',self.vina)
        self._record('C1','docking_score',-5.0,'glide',self.glide)
        self._record('C2','docking_score',-9.0,'glide',self.glide)

    def tearDown(self): self.temp.cleanup()

    def _record(self,candidate,evidence,value,tool,protocol):
        source=self.root/(candidate+'_'+tool+'.txt');source.write_text(str(value),encoding='utf-8')
        artifact=self.state.artifact(source)
        job=self.state.job('RUN_'+tool,self.project,candidate,tool,protocol['protocol_id'],[artifact],{'test':True})
        with self.state.connect() as db:
            db.execute("UPDATE calculation_job SET status='completed',completed_at=?,return_code=0,output_artifacts=? WHERE job_id=?",
                       (now(),encode([artifact]),job))
        self.state.register_many(self.project,job,artifact['artifact_hash'],[{
            'compound_id':candidate,'evidence_type':evidence,'raw_value':value,
            'unit':'kcal/mol' if tool=='vina' else 'Glide_score',
            'provenance':{'tool_id':tool,'tool_family':tool}}],'tool_execution')

    def test_candidate_query_keeps_protocols_separate(self):
        result=project_candidate_docking_evidence(self.state,self.project,'Hit3')
        self.assertEqual(result['status'],'available')
        self.assertEqual({row['tool_family'] for row in result['docking_evidence']},{'vina','glide'})
        self.assertEqual({row['protocol_id'] for row in result['docking_evidence']},{'VINA_TEST','GLIDE_TEST'})
        self.assertIn('不合并',result['interpretation'])

    def test_disagreement_uses_ranks_not_pooled_raw_values(self):
        result=project_vina_glide_disagreements(self.state,self.project)
        self.assertEqual(result['status'],'available')
        self.assertEqual(result['n'],2)
        self.assertIn('rank disagreement',result['comparison'])
        self.assertTrue(all('absolute_rank_shift' in row for row in result['largest_disagreements']))

    def test_unknown_identity_is_not_guessed(self):
        result=project_candidate_docking_evidence(self.state,self.project,'almost Hit3')
        self.assertEqual(result['status'],'not_found')


class Phase13SavedRunTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.output=ROOT/'results/phase13'

    def test_real_project_parser_and_pose_count(self):
        manifest=(self.output/'pose_artifact_manifest.csv').read_text(encoding='utf-8')
        self.assertEqual(manifest.count('\n')-1,17)
        poses=sorted((self.output/'poses').glob('*.pdbqt'))
        self.assertEqual(len(poses),17)
        for pose in poses:
            parsed=parse_vina_pose(pose)
            self.assertGreaterEqual(parsed['pose_count'],1)
            self.assertLessEqual(parsed['pose_count'],9)
            self.assertTrue(-100.0<parsed['affinity']<100.0)

    def test_resume_and_duplicate_prevention_saved_acceptance(self):
        result=json.loads((self.output/'resume_validation.json').read_text(encoding='utf-8'))
        self.assertEqual(result['status'],'pass')
        self.assertEqual(result['completed_before_pause'],7)
        self.assertEqual(result['completed_after_resume'],17)
        self.assertTrue(result['duplicate_execution_prevented'])
        self.assertTrue(result['output_hashes_preserved'])

    def test_in2_reference_metric_is_not_activity(self):
        import csv
        with (self.output/'evidence_registry_export.csv').open(encoding='utf-8') as stream:
            rows=list(csv.DictReader(stream))
        qc=[json.loads(row['raw_value']) for row in rows
            if row['compound_id']=='ATP-REF-IN2' and row['evidence_type']=='pose_qc']
        self.assertEqual(len(qc),1)
        self.assertEqual(qc[0]['historical_reference']['metric_scope'],
                         'protocol-comparison metric only; not biological validation')

    def test_shadow_comparison_and_no_vina_as_glide_feature(self):
        import csv
        metrics=json.loads((self.output/'shadow_comparison_metrics.json').read_text(encoding='utf-8'))
        self.assertEqual(metrics['status'],'complete');self.assertEqual(metrics['n'],17)
        self.assertEqual(metrics['scope'],'descriptive protocol comparison only; not biological validation')
        with (self.output/'evidence_registry_export.csv').open(encoding='utf-8') as stream:
            rows=list(csv.DictReader(stream))
        forbidden=[row for row in rows if row['tool_family']=='vina' and row['evidence_type']=='docking_score']
        self.assertEqual(forbidden,[])


if __name__=='__main__':
    unittest.main()
