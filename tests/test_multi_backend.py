"""Synthetic fixtures are isolated in TemporaryDirectory; never scientific evidence."""
import csv
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from workspace.multi_workflow import MultiBackendWorkspace
from workspace.multi_planner import intent,allocate,topological_nodes
from workspace.multi_evidence import cohort_rankings,decision_view
from workspace.multi_executor import MultiExecutor
from workspace.workflow_service import WorkflowService,session_evidence_answer
from workspace.state import encode,file_hash,digest,write_json
from tools.vina_adapter import parse_vina_pose,validate_box
from tools.base_adapter import ToolInfo
from tools.schrodinger_adapter import SchrodingerAdapter


class MultiBackendTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        shutil.copytree(ROOT/'src',self.root/'src',ignore=shutil.ignore_patterns('__pycache__'))
        self.caps={'tools':{'rdkit':{**ToolInfo('rdkit','RDKit','open_toolchain',['structure_qc'],'TEST_VERSION',sys.executable,
                    'open_source_no_checkout_required','available').record(),'executable_sha256':file_hash(sys.executable)}},'auxiliary_commands':{}}
        self.w=MultiBackendWorkspace(self.root,capabilities=self.caps);self.s=self.w.state
        self.input=self.root/'candidates.csv';self.input.write_text('compound_id,SMILES\nTEST_A,CCO\nTEST_B,CCN\n',encoding='utf-8')
        self.protocol={'protocol_id':'TEST_PROTOCOL','confirmation':'researcher_confirmed','seed':42,'scope':'software_smoke_only'}

    def tearDown(self): self.temp.cleanup()
    def plan(self): return self.w.create('TEST_PROJECT',self.input,'最终实验预算1',protocol=self.protocol)

    def test_three_modes_and_invalid_mode(self):
        for mode in ['commercial_full','open_toolchain','decision_only']:
            result=self.w.create('TEST_PROJECT',self.input,'最终实验预算1',mode,self.protocol)
            self.assertEqual(result['status'],'awaiting_confirmation')
        with self.assertRaises(ValueError): self.w.create('TEST_PROJECT',self.input,'','invented',self.protocol)

    def test_no_execution_before_confirmation(self):
        run=self.plan();self.assertEqual(self.w.resume(run['run_id'])['executed'],0)
        self.assertEqual(self.s.evidence_rows('TEST_PROJECT'),[])

    def test_shared_state_chat(self):
        run=self.plan();answer=self.w.chat_workspace.chat(run['session_id'],'为什么还不能排名1633个？')
        self.assertEqual(answer['source'],'shared_Evidence_Registry');self.assertEqual(len(answer['candidates']),2)
        self.assertFalse(answer['candidates'][0]['Docking'])

    def test_conversation_creates_unconfirmed_plan_same_session(self):
        run=self.plan()
        reply=self.w.chat_workspace.chat(run['session_id'],'计划计算 Docking最多2个，MMGBSA最多1个，最终实验预算1')
        self.assertEqual(reply['session_id'],run['session_id'])
        self.assertEqual(reply['status'],'awaiting_confirmation')
        self.assertEqual(self.w.status(reply['run_id'])['jobs'],[])

    def test_conversation_cannot_confirm_another_session(self):
        a=self.plan();b=self.plan()
        with self.assertRaises(ValueError): self.w.chat_workspace.chat(a['session_id'],'确认计算 '+b['run_id'])

    def test_intent_budget_phrasing(self):
        parsed=intent('ATP机制优先，MMGBSA最多计算40个，最后实验验证6个，Docking最多5个')
        self.assertEqual((parsed['mmgbsa_budget'],parsed['final_experiment_budget'],parsed['docking_budget']),(40,6,5))

    def test_budget_and_unknown_uncertainty(self):
        rows=[{'compound_id':'TEST_'+str(i),'current_rank':i+1,'scaffold':str(i),'evidence_completeness':0,
               'uncertainty':'unknown','model_disagreement':'unknown','relative_cost':2} for i in range(60)]
        selected=allocate(rows,40,max_cost=20)
        self.assertLessEqual(len(selected),10)
        self.assertTrue(all(r['uncertainty']=='unknown' for r in selected))

    def test_allocation_observed_uncertainty(self):
        rows=[{'compound_id':str(i),'current_rank':i+1,'scaffold':str(i),'uncertainty':i/40,'relative_cost':1} for i in range(40)]
        out=allocate(rows,40)
        self.assertEqual(sum(r['allocation_stratum']=='exploitation' for r in out),25)
        self.assertEqual(sum(r['allocation_stratum']=='uncertainty' for r in out),10)
        self.assertEqual(sum(r['allocation_stratum']=='diversity' for r in out),5)

    def test_invalid_allocation(self):
        with self.assertRaises(ValueError): allocate([],4,{'exploitation':1,'uncertainty':1,'diversity':0})

    def test_dag_branches_and_cycle_rejection(self):
        order=topological_nodes({'import':[],'qc':['import'],'properties':['qc'],'dock':['qc'],'decision':['properties','dock']})
        self.assertEqual(order[0],'import');self.assertEqual(order[-1],'decision')
        with self.assertRaises(ValueError): topological_nodes({'a':['b'],'b':['a']})

    def test_feedback_requires_reviewed_evidence(self):
        with self.assertRaises(ValueError): WorkflowService(self.root,capabilities=self.caps).link_reviewed_experiment('TEST_PROJECT','TEST_DECISION','TEST_EXPERIMENT')

    def test_box_cannot_be_guessed(self):
        with self.assertRaises(ValueError): validate_box(None)
        with self.assertRaises(ValueError): validate_box({'center':[0,0,0],'size':[0,1,1]})
        validate_box({'center':[0,0,0],'size':[20,20,20]})

    def test_vina_parser_requires_real_record_and_pose(self):
        p=self.root/'synthetic_test_pose.pdbqt';p.write_text('REMARK VINA RESULT: -7.0 0 0\nATOM TEST_ONLY\n')
        self.assertEqual(parse_vina_pose(p)['affinity'],-7)
        p.write_text('No calculation occurred\n')
        with self.assertRaises(ValueError): parse_vina_pose(p)

    def test_installed_help_does_not_prove_license(self):
        exe=self.root/'glide.exe';exe.write_bytes(b'TEST_NO_EXECUTION')
        (self.root/'utilities').mkdir();(self.root/'utilities/lictest.exe').write_bytes(b'TEST')
        with patch('tools.schrodinger_adapter.shutil.which',return_value=None),patch('tools.schrodinger_adapter.probe',side_effect=[
                {'return_code':0,'sha256':'TEST','text':'usage options'}, {'return_code':1,'sha256':'TEST','text':'license unavailable'}]):
            info=SchrodingerAdapter.discover('glide',[self.root]).detect()
        self.assertEqual(info['availability'],'installed_but_license_unavailable')

    def test_protocol_immutable(self):
        self.s.freeze_protocol(self.protocol)
        with self.assertRaises(ValueError): self.s.freeze_protocol({**self.protocol,'seed':24})

    def test_no_unknown_docking_backend_import(self):
        self.input.write_text('compound_id,SMILES,docking_score\nTEST_A,CCO,-7\n')
        run=self.w.create('TEST_PROJECT',self.input,'',protocol=self.protocol)
        with self.assertRaises(ValueError): self.w.import_evidence(self.w.get_run(run['run_id']))

    def test_backend_cohorts_remain_separate(self):
        records=[{'compound_id':'TEST_A','evidence_type':'vina_affinity','value':-7,'tool_id':'vina','tool_version':'1',
                  'protocol_id':'TEST_V','run_id':'TEST_R'},
                 {'compound_id':'TEST_A','evidence_type':'docking_score','value':-7,'tool_id':'glide','tool_version':'1',
                  'protocol_id':'TEST_G','run_id':'TEST_R'}]
        rows=cohort_rankings(records);self.assertEqual([r['cohort_rank'] for r in rows],[1,1]);self.assertTrue(all(r['cross_protocol'] for r in rows))

    def test_batch_cohorts_remain_separate(self):
        rows=[{'compound_id':'TEST_A','evidence_type':'vina_affinity','value':-7,'tool_id':'vina','tool_version':'1',
                  'protocol_id':'TEST_V','run_id':batch} for batch in ['TEST_1','TEST_2']]
        self.assertEqual(len({r['cohort'] for r in cohort_rankings(rows)}),2)

    def make_job(self):
        run=self.plan();batch=run['run_id'];ex=MultiExecutor(self.s,self.caps)
        archive=json.loads(self.w.get_run(batch)['input_artifact'])
        job=ex.plan(batch,'TEST_PROJECT','TEST_A','rdkit','TEST_PROTOCOL',{'stage':'structure_qc','smiles':'CCO','backend':'decision_only'},[archive])
        return batch,ex,job

    def test_duplicate_job_signature(self):
        batch,ex,job=self.make_job();before=self.s.get_job(job)
        again=ex.plan(batch,'TEST_PROJECT','TEST_A','rdkit','TEST_PROTOCOL',{'stage':'structure_qc','smiles':'CCO','backend':'decision_only'},[json.loads(self.w.get_run(batch)['input_artifact'])])
        self.assertEqual(job,again);self.assertEqual(before['attempt'],0)

    def test_unavailable_tool_blocked_no_number(self):
        batch,ex,job=self.make_job()
        with self.s.connect() as db: db.execute('UPDATE workflow_run SET confirmed=1 WHERE run_id=?',(batch,))
        ex.capabilities['tools']['rdkit']['availability']='not_found'
        result=ex.run(job);self.assertEqual(result['status'],'blocked');self.assertEqual(self.s.evidence_rows('TEST_PROJECT'),[])

    def test_failed_job_not_retried_implicitly(self):
        batch,ex,job=self.make_job();ex.update(job,'failed','SYNTHETIC_TEST_FAILURE')
        with self.s.connect() as db: db.execute('UPDATE workflow_run SET confirmed=1 WHERE run_id=?',(batch,))
        self.assertEqual(ex.run(job)['attempt'],0)

    def test_running_unknown_liveness_no_duplicate(self):
        batch,ex,job=self.make_job();ex.update(job,'running',attempt=1)
        self.assertEqual(ex.recover(job)['recovery'],'unknown_liveness_no_duplicate_launch')

    def test_actual_rdkit_job_cache_and_registration(self):
        batch,ex,job=self.make_job()
        with self.s.connect() as db: db.execute('UPDATE workflow_run SET confirmed=1 WHERE run_id=?',(batch,))
        first=ex.run(job);self.assertEqual(first['status'],'completed',first['reason'])
        second=ex.run(job);self.assertEqual(second['attempt'],1);self.assertTrue(second['cache_hit'])
        self.assertEqual(len(self.s.evidence_rows('TEST_PROJECT')),1)
        # Simulate an orchestrator crash after receipt creation but before the
        # evidence transaction, in this isolated test DB only.
        with self.s.connect() as db:
            db.execute('DELETE FROM evidence')
            db.execute("UPDATE calculation_job SET status='running' WHERE job_id=?",(job,))
        restored=ex.recover(job)
        self.assertEqual(restored['status'],'completed');self.assertEqual(restored['attempt'],1)
        self.assertEqual(len(self.s.evidence_rows('TEST_PROJECT')),1)

    def test_api_project_scoping(self):
        run=self.plan();service=WorkflowService(self.root,capabilities=self.caps)
        self.assertEqual(len(service.request('GET','/projects/TEST_PROJECT/candidates')),2)
        with self.assertRaises(ValueError): service.request('POST','/projects/OTHER/runs',{'resume':run['run_id'],'confirm':True})

    def test_api_no_arbitrary_files(self):
        service=WorkflowService(self.root,capabilities=self.caps)
        with self.assertRaises(ValueError): service.request('POST','/projects/TEST_PROJECT/runs',{'input_path':'C:/Windows/system.ini','intent':''})


if __name__=='__main__': unittest.main()
