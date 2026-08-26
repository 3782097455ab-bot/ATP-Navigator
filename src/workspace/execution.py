"""Safe job state machine, actual subprocesses, immutable results and recovery."""
from __future__ import annotations
import csv
import json
import subprocess
import sys
from pathlib import Path
from .state import encode, now, file_hash, write_json
from .protocols import protocol_issues
from .parsers import parse_csv

TRANSITIONS = {'planned':{'ready','blocked','cancelled'},'ready':{'running','blocked','cancelled'},
               'running':{'completed','failed','blocked'},'blocked':{'ready','cancelled'},
               'failed':{'ready','cancelled'},'completed':set(),'cancelled':set()}


class Executor:
    def __init__(self,state,capabilities):
        self.state=state
        self.capabilities=capabilities

    def transition(self,job_id,status,reason='',**fields):
        if set(fields)-{'started_at','completed_at','return_code','stdout_path','stderr_path','output_artifacts','attempt'}:
            raise ValueError('Unknown job fields')
        with self.state.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            old=db.execute('SELECT status FROM calculation_job WHERE job_id=?',(job_id,)).fetchone()
            if not old or status not in TRANSITIONS[old[0]]:
                raise ValueError('Invalid job state transition')
            values={'status':status,'reason':reason,**fields}
            db.execute('UPDATE calculation_job SET '+','.join(k+'=?' for k in values)+' WHERE job_id=?',[*values.values(),job_id])

    def block(self,job_id,reasons):
        job=self.state.get_job(job_id)
        if job['status'] in {'planned','ready','running'}:
            self.transition(job_id,'blocked','; '.join(reasons))
        return self.state.get_job(job_id)

    def readiness(self,job_id,predecessor_ok=True):
        job=self.state.get_job(job_id)
        manifest=json.loads(job['command_manifest'])
        tool=self.capabilities['tools'].get(job['tool_id'],{})
        issues=[]
        if tool.get('availability')!='available':
            issues.append('tool_'+tool.get('availability','not_found')+': '+tool.get('reason',''))
        issues+=protocol_issues(self.state.protocol(job['protocol_id']),job['tool_id'],manifest.get('stage'))
        if not predecessor_ok:
            issues.append('stage_gate_missing_'+str(manifest.get('predecessor')))
        if job['tool_id'] not in {'rdkit','glide','prime_mmgbsa','qikprop'}:
            issues.append('adapter_not_implemented')
        if job['tool_id']!='rdkit' and not manifest.get('prepared_input'):
            issues.append('hash_pinned_prepared_ligand_or_poseviewer_missing')
        if not json.loads(job['input_artifacts']):
            issues.append('input_artifact_missing')
        return issues

    def launch(self,job_id,predecessor_ok=True,retry=False):
        job=self.state.get_job(job_id)
        if job['status']=='completed':
            # A repeat does not recalculate. Verify archived outputs before reuse.
            for artifact in json.loads(job['output_artifacts']):
                self.state.verify_artifact(artifact['artifact_hash'])
            return self.recover(job_id)
        if job['status']=='running':
            return self.recover(job_id)
        if job['status']=='cancelled':
            return job
        if job['status']=='failed' and not retry:
            return job  # no hidden retries or repeated license spending
        reasons=self.readiness(job_id,predecessor_ok)
        if reasons:
            return self.block(job_id,reasons)
        for artifact in json.loads(job['input_artifacts']):
            self.state.verify_artifact(artifact['artifact_hash'])
        if job['status']!='ready':
            self.transition(job_id,'ready')
        # Claim atomically before starting a subprocess; racing callers cannot execute twice.
        attempt=job['attempt']+1
        self.transition(job_id,'running',started_at=now(),attempt=attempt)
        root=self.state.root/'jobs'/job_id/f'attempt_{attempt}'
        root.mkdir(parents=True,exist_ok=False)
        request=json.loads(job['command_manifest'])
        tool=job['tool_id']
        if tool=='rdkit':
            source=self.state.verify_artifact(json.loads(job['input_artifacts'])[0]['artifact_hash'])
            argv=[sys.executable,str(self.state.project/'src/workspace/rdkit_worker.py'),'--input',str(source),'--output',str(root/'result.csv')]
        else:
            request['executable']=self.capabilities['tools'][tool]['executable']
            write_json(root/'tool_request.json',request)
            runner=self.capabilities['commands'].get('run')
            if not runner:
                return self.block(job_id,['Schrodinger Python runner missing'])
            argv=[runner,str(self.state.project/'src/workspace/schrodinger_worker.py'),'--manifest',str(root/'tool_request.json')]
        command={'argv':argv,'cwd':str(root),'shell':False,'expected_outputs':['result.csv'],
                 'job_id':job_id,'protocol_id':job['protocol_id'],
                 'worker_sha256':file_hash(self.state.project/('src/workspace/rdkit_worker.py' if tool=='rdkit' else 'src/workspace/schrodinger_worker.py'))}
        write_json(root/'command.json',command)
        with self.state.connect() as db:
            db.execute('UPDATE calculation_job SET stdout_path=?,stderr_path=?,command_manifest=? WHERE job_id=?',
                       (str(root/'stdout.txt'),str(root/'stderr.txt'),encode({**request,'actual_command':command}),job_id))
        try:
            process=subprocess.Popen([sys.executable,str(self.state.project/'src/workspace/job_runner.py'),
                                      '--manifest',str(root/'command.json')],cwd=root,shell=False)
            # Supervisor survives an interrupted orchestration process and writes a receipt.
            process.wait()
            return self.recover(job_id)
        except OSError as error:
            self.transition(job_id,'failed',type(error).__name__+': '+str(error),completed_at=now(),return_code=-1)
            return self.state.get_job(job_id)

    def recover(self,job_id):
        job=self.state.get_job(job_id)
        if job['status'] not in {'running','completed'}:
            return job
        root=self.state.root/'jobs'/job_id/f"attempt_{job['attempt']}"
        receipt_path=root/'receipt.json'
        if not receipt_path.is_file():
            # Unknown liveness is deliberately not auto-retried (PID reuse possible).
            return {**job,'recovery':'awaiting_supervisor_receipt_or_manual_inspection_no_duplicate_launch'}
        receipt=json.loads(receipt_path.read_text(encoding='utf-8'))
        if receipt['command_sha256']!=file_hash(root/'command.json'):
            return self.block(job_id,['command_manifest_integrity_failure'])
        if receipt['return_code']!=0:
            self.transition(job_id,'failed',receipt.get('error') or 'Tool nonzero exit',completed_at=receipt['completed_at'],return_code=receipt['return_code'])
            return self.state.get_job(job_id)
        try:
            for item in receipt['outputs']:
                if file_hash(item['path'])!=item['sha256']:
                    raise ValueError('Output hash mismatch')
            path=root/'result.csv'
            if not any(Path(item['path'])==path for item in receipt['outputs']):
                raise ValueError('Result absent from completion receipt')
            with self.state.connect() as db:
                allowed={r[0] for r in db.execute('SELECT candidate_id FROM candidate WHERE project_id=?',(job['project_id'],))}
            if job['tool_id']=='rdkit':
                with path.open(encoding='utf-8-sig',newline='') as stream:
                    rows=list(csv.DictReader(stream))
                if not rows or any(r['compound_id'] not in allowed for r in rows):
                    raise ValueError('Unknown/empty RDKit result identities')
                evidence=[]
                for row in rows:
                    evidence.append({'compound_id':row['compound_id'],'evidence_type':'structure_qc',
                                     'raw_value':row,'tool_version':row['tool_version'],'unit':'mixed_descriptor_bundle'})
            else:
                evidence=parse_csv(path,job['tool_id'],{job['candidate_id']})
                for row in evidence:
                    row['tool_version']=self.capabilities['tools'][job['tool_id']]['version']
                    row['provenance']={'stage':json.loads(job['command_manifest'])['stage']}
            artifacts=[self.state.artifact(path),self.state.artifact(root/'command.json'),self.state.artifact(receipt_path)]
            native=root/'native_artifacts.json'
            if native.is_file():
                artifacts += [self.state.artifact(root/p) for p in json.loads(native.read_text())['files']]
            if self.state.get_job(job_id)['status']=='running':
                self.transition(job_id,'completed',completed_at=receipt['completed_at'],return_code=0,output_artifacts=encode(artifacts))
            self.state.register_many(job['project_id'],job_id,artifacts[0]['artifact_hash'],evidence,'tool_execution',
                                     {'stage':json.loads(job['command_manifest']).get('stage'),'command_sha256':file_hash(root/'command.json')})
        except Exception as error:
            current=self.state.get_job(job_id)
            if current['status']=='running':
                self.transition(job_id,'failed','Result validation: '+str(error),return_code=0,completed_at=now())
            else:
                raise  # Completed compute but registration error must be visible, not hidden.
        return self.state.get_job(job_id)
