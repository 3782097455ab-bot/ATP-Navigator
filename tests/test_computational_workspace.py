"""Phase12 tests. All synthetic parser/feedback fixtures are temporary TEST data."""
import csv
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from workspace.state import State, encode, file_hash, write_json
from workspace.tool_capabilities import discover,find_command,license_classification
from workspace.protocols import rdkit_protocol,protocol_issues
from workspace.planner import parse_intent,acquire,gate
from workspace.execution import Executor
from workspace.parsers import parse_records
from workspace.knowledge_qc import classify
from workspace.evidence_bridge import registry_view,sync_feedback


class ComputationalWorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='atp_phase12_test_')
        self.folder=Path(self.temp.name)
        self.state=State(ROOT,self.folder/'runtime')
        self.state.project_id('test_project')
        self.state.candidate('test_project','TEST-1','CCO')
        self.cap=discover(env={},roots=[],which=lambda name:None)
        self.protocol=rdkit_protocol(self.cap['tools']['rdkit']['version'])
        self.state.freeze_protocol(self.protocol)
        self.batch=self.state.batch('test_project',{'test_fixture':True})
        self.input=self.folder/'input.csv'
        self.input.write_text('compound_id,SMILES\nTEST-1,CCO\n',encoding='utf-8')
        self.artifact=self.state.artifact(self.input)
        self.executor=Executor(self.state,self.cap)

    def tearDown(self):
        self.temp.cleanup()

    def job(self,tool='rdkit',inputs=None):
        return self.state.job(self.batch,'test_project','__library__',tool,self.protocol['protocol_id'],
                              [self.artifact] if inputs is None else inputs,{'stage':'structure_qc'})

    def test_discovery_contract_and_rdkit_actual(self):
        self.assertEqual(self.cap['tools']['rdkit']['availability'],'available')
        for record in self.cap['tools'].values():
            self.assertTrue({'tool_id','version','executable','availability','license_status','input_contract',
                             'output_contract','estimated_cost','protocol_id'}<=record.keys())

    def test_discovery_finds_executable_in_installation(self):
        (self.folder/'glide.exe').write_bytes(b'TEST_NOT_EXECUTABLE')
        self.assertEqual(find_command('glide',[self.folder],lambda n:None),str((self.folder/'glide.exe').resolve()))

    def test_license_server_status_not_checkout(self):
        result=subprocess.CompletedProcess([],0,'server OK','')
        self.assertEqual(license_classification(True,result)[0],'configuration_missing')
        result=subprocess.CompletedProcess([],1,'No valid license found','')
        self.assertEqual(license_classification(True,result)[0],'installed_but_unlicensed')

    def test_unavailable_tool_blocked_without_values(self):
        job=self.job('glide')
        result=self.executor.launch(job)
        self.assertEqual(result['status'],'blocked')
        self.assertIn('tool_not_found',result['reason'])
        self.assertEqual(self.state.evidence_rows('test_project'),[])
        self.assertEqual(result['output_artifacts'],'[]')

    def test_actual_rdkit_command_provenance_no_fabricated_binding(self):
        job=self.job()
        result=self.executor.launch(job)
        self.assertEqual(result['status'],'completed')
        self.assertEqual(result['return_code'],0)
        evidence=self.state.evidence_rows('test_project')
        self.assertEqual(len(evidence),1)
        self.assertEqual(evidence[0]['source_job_id'],job)
        self.assertEqual(json.loads(evidence[0]['provenance'])['origin'],'tool_execution')
        values=json.loads(evidence[0]['raw_value'])
        self.assertAlmostEqual(float(values['MW']),46.069,places=3)
        self.assertEqual(len(values['morgan1024']),1024)
        self.assertNotIn('mmgbsa_score',values)
        manifest=self.state.root/'jobs'/job/'attempt_1/command.json'
        command=json.loads(manifest.read_text())
        self.assertFalse(command['shell'])
        self.assertEqual(command['argv'][0],sys.executable)

    def test_duplicate_execution_prevented_and_receipt_recoverable(self):
        first=self.job()
        second=self.job()
        self.assertEqual(first,second)
        self.executor.launch(first)
        # Simulate orchestration crash between tool completion and evidence commit.
        with self.state.connect() as db:
            db.execute('DELETE FROM evidence')
        again=self.executor.launch(second)
        self.assertEqual(again['attempt'],1)
        self.assertEqual(len(self.state.evidence_rows('test_project')),1)

    def test_duplicate_content_at_different_paths_not_reexecuted(self):
        other=self.folder/'same_content.csv'
        shutil.copyfile(self.input,other)
        first=self.job()
        second=self.job(inputs=[self.state.artifact(other)])
        self.assertEqual(first,second)

    def test_empty_decision_trace_serializes_null_not_fake_zero(self):
        from navigator_pipeline import json_safe
        self.assertEqual(json.loads(encode(json_safe({'correlation':float('nan')}))),{'correlation':None})

    def test_running_without_receipt_never_reexecutes(self):
        job=self.job()
        self.executor.transition(job,'ready')
        self.executor.transition(job,'running',attempt=1)
        result=self.executor.launch(job)
        self.assertEqual(result['status'],'running')
        self.assertIn('no_duplicate_launch',result['recovery'])

    def test_failed_job_explicit_retry(self):
        job=self.job()
        self.executor.transition(job,'ready')
        self.executor.transition(job,'running',attempt=0)
        self.executor.transition(job,'failed','TEST_FAILURE')
        self.assertEqual(self.executor.launch(job)['status'],'failed')
        self.assertEqual(self.executor.launch(job,retry=True)['status'],'completed')

    def test_protocol_immutability(self):
        altered={**self.protocol,'protonation':'different'}
        with self.assertRaisesRegex(ValueError,'immutable'):
            self.state.freeze_protocol(altered)

    def test_unknown_grid_blocks_protocol(self):
        issues=protocol_issues({'confirmation':'required'},'glide','XP')
        self.assertIn('protocol.grid=unknown',issues)
        self.assertIn('protocol_confirmation_required',issues)

    def test_stage_gate_no_xp_before_sp(self):
        rows=[{'compound_id':'TEST-1','current_rank':1,'scaffold':'CC'}]
        stages={'TEST-1':{'structure_qc','HTVS'}}
        self.assertEqual(len(gate(rows,'SP',stages,1)),1)
        self.assertEqual(gate(rows,'XP',stages,1),[])

    def test_budget_and_cost_enforced(self):
        rows=[{'compound_id':str(i),'current_rank':i+1,'relative_cost':50} for i in range(100)]
        self.assertEqual(len(acquire(rows,40)),40)
        self.assertEqual(len(acquire(rows,40,max_cost=100)),2)
        self.assertEqual(acquire(rows,0),[])

    def test_scaffold_diversity_tiebreak(self):
        rows=[{'compound_id':'A','scaffold':'X','current_rank':1},
              {'compound_id':'B','scaffold':'X','current_rank':1},
              {'compound_id':'C','scaffold':'Y','current_rank':1}]
        self.assertEqual([r['compound_id'] for r in acquire(rows,2)],['A','C'])

    def test_unknown_uncertainty_stays_unknown(self):
        row=acquire([{'compound_id':'A','uncertainty':'unknown'}],1)[0]
        self.assertEqual(row['uncertainty'],'unknown')
        self.assertIn('not_activity_probability',row['interpretation'])

    def test_intent_parsing_and_reject_conflict(self):
        intent=parse_intent('ATP机制优先，候选1633个，MM/GBSA预算最多40个，XP最多100个，最后给我6个实验候选')
        self.assertEqual((intent.mmgbsa_budget,intent.xp_budget,intent.final_experiment_budget,intent.expected_candidates),(40,100,6,1633))
        with self.assertRaises(ValueError):
            parse_intent('MMGBSA最多20，MMGBSA最多40')

    def test_glide_parser(self):
        rows=parse_records([{'compound_id':'TEST-1','r_i_docking_score':'-5.2','r_i_glide_emodel':'-30'}],'glide',{'TEST-1'})
        self.assertEqual(len(rows),2)
        self.assertEqual(rows[0]['normalized_value'],None)

    def test_prime_and_qikprop_parsers(self):
        rows=parse_records([{'compound_id':'TEST-1','MMGBSA dG Bind':'-21'}],'prime_mmgbsa',{'TEST-1'})
        self.assertEqual(rows[0]['unit'],'kcal/mol')
        rows=parse_records([{'compound_id':'TEST-1','r_qp_QPlogPo/w':'2.1'}],'qikprop',{'TEST-1'})
        self.assertEqual(rows[0]['evidence_type'],'quickprop_qplogpo_w')

    def test_parser_rejects_identity_duplicate_and_nan_inf(self):
        for records in [[{'compound_id':'wrong','r_i_docking_score':-1}],
                        [{'compound_id':'TEST-1','r_i_docking_score':'inf'}],
                        [{'compound_id':'TEST-1','r_i_docking_score':-1}]*2]:
            with self.assertRaises(ValueError):
                parse_records(records,'glide',{'TEST-1'})

    def test_failed_job_cannot_register_evidence(self):
        job=self.job()
        with self.assertRaises(ValueError):
            self.state.register_many('test_project',job,self.artifact['artifact_hash'],[], 'tool_execution')

    def test_artifact_tampering_detected(self):
        archived=Path(self.artifact['path'])
        archived.write_text('TEST_TAMPER',encoding='utf-8')
        with self.assertRaises(ValueError):
            self.state.verify_artifact(self.artifact['artifact_hash'])

    def test_registry_view_does_not_fill_missing_scores(self):
        output=self.folder/'view.csv'
        registry_view(self.state,'test_project',['TEST-1'],output)
        with output.open(encoding='utf-8') as stream:
            row=next(csv.DictReader(stream))
        self.assertEqual(row['mmgbsa_score'],'unknown')
        self.assertEqual(row['docking_score'],'unknown')
        self.assertEqual(row['SMILES'],'unknown')

    def test_candidate_identity_collision(self):
        with self.assertRaises(ValueError):
            self.state.candidate('test_project','TEST-1','CCC')

    def test_target_annotation_conflict_quarantined(self):
        row={'SMILES':'CCO','target':'ATP synthase','reference':'Carboxylic acid isosteres inhibit pilus biogenesis in E. coli.'}
        result=classify('ATP_target_expansion.csv',row)
        self.assertEqual(result['status'],'quarantined')
        self.assertFalse(result['training_allowed'])

    def test_endpoint_segregation_and_censoring(self):
        mic=classify('negative_SAR_examples.csv',{'SMILES':'CCO','activity_type':'MIC','activity_value':'>128','unit':'ug/mL'})
        cyt=classify('negative_SAR_examples.csv',{'SMILES':'CCO','activity_type':'CC50','activity_value':'128','unit':'ug/mL'})
        self.assertEqual(mic['comparator'],'>')
        self.assertNotEqual(mic['endpoint_stratum'],cyt['endpoint_stratum'])

    def test_bridge_only_retrieval(self):
        result=classify('chemical_space_bridge.csv',{'SMILES':'CCO','antibacterial_activity':'inactive'})
        self.assertEqual(result['status'],'unverified_retrieval_pool')
        self.assertFalse(result['internal_evidence_allowed'])

    def test_feedback_linkage_empty_and_reviewed(self):
        with patch('experimental_feedback.FeedbackStore') as store:
            store.return_value.status.return_value={'latest_snapshot':None}
            result=sync_feedback(self.state,'test_project',['TEST-1'],'TEST-DECISION','TEST-MODEL')
            self.assertEqual(result['status'],'empty')
            self.assertEqual(result['prospective_metrics'],'not_available')
            store.return_value.status.return_value={'latest_snapshot':{'snapshot_id':'TEST-SNAPSHOT'}}
            store.return_value.evidence_for.return_value=[{'record_id':'TEST-RECORD','assay_protocol_id':'TEST-ASSAY'}]
            result=sync_feedback(self.state,'test_project',['TEST-1'],'TEST-DECISION','TEST-MODEL')
            self.assertEqual(result['records'],1)
            with self.state.connect() as db:
                row=dict(db.execute('SELECT * FROM feedback_link').fetchone())
            self.assertEqual(row['decision_run_id'],'TEST-DECISION')
            self.assertEqual(row['protocol_id'],'TEST-ASSAY')


if __name__=='__main__':
    unittest.main()
