"""Durable, content-addressed jobs in the existing Phase11/12 SQLite registry."""
import json
import os
from pathlib import Path
import subprocess
import sys
from tools.tool_registry import adapter
from tools.base_adapter import child_environment
from .state import encode,now,write_json,file_hash,digest


class MultiExecutor:
    def __init__(self,state,capabilities):
        self.state=state;self.capabilities=capabilities

    def plan(self,batch,project,candidate,tool,protocol,request,inputs):
        info=self.capabilities['tools'][tool]
        command={'request':request,'tool_version':info['tool_version'],
                 'executable_sha256':info.get('executable_sha256'),'protocol_hash':digest(self.state.protocol(protocol)),
                 'worker_sha256':file_hash(self.state.project/('src/tools/commercial_worker.py' if tool in {'ligprep','glide','prime_mmgbsa','qikprop'} else 'src/tools/computation_worker.py'))}
        job=self.state.job(batch,project,candidate,tool,protocol,inputs,command)
        with self.state.connect() as db:
            db.execute("UPDATE calculation_job SET status='awaiting_confirmation' WHERE job_id=? AND status='planned'",(job,))
            db.execute('INSERT OR IGNORE INTO workflow_job_link VALUES (?,?)',(batch,job))
        return job

    def update(self,job,status,reason='',**extra):
        allowed={'attempt','started_at','completed_at','return_code','stdout_path','stderr_path','output_artifacts'}
        if set(extra)-allowed: raise ValueError('Unknown job update field')
        with self.state.connect() as db:
            fields={'status':status,'reason':reason,**extra}
            db.execute('UPDATE calculation_job SET '+','.join(k+'=?' for k in fields)+' WHERE job_id=?',[*fields.values(),job])

    def run(self,job_id,retry=False):
        job=self.state.get_job(job_id)
        with self.state.connect() as db:
            confirmation=db.execute('SELECT r.confirmed FROM workflow_run r JOIN workflow_job_link l ON r.run_id=l.run_id WHERE l.job_id=? AND r.confirmed=1 LIMIT 1',(job_id,)).fetchone()
        if job['status']=='completed': return self.recover(job_id)
        if job['status']=='running': return self.recover(job_id)
        if not confirmation or not confirmation['confirmed']:
            return job
        if job['status']=='cancelled' or (job['status']=='failed' and not retry): return job
        info=self.capabilities['tools'][job['tool_id']];adapt=adapter(info)
        errors=adapt.validate_environment()
        if errors:
            self.update(job_id,'blocked','; '.join(errors));return self.state.get_job(job_id)
        for item in json.loads(job['input_artifacts']): self.state.verify_artifact(item['artifact_hash'])
        command=json.loads(job['command_manifest'])
        worker=self.state.project/('src/tools/commercial_worker.py' if job['tool_id'] in {'ligprep','glide','prime_mmgbsa','qikprop'} else 'src/tools/computation_worker.py')
        if file_hash(worker)!=command['worker_sha256']:
            self.update(job_id,'blocked','worker_changed_create_new_plan');return self.state.get_job(job_id)
        if command['tool_version']!=info['tool_version'] or command['executable_sha256']!=info.get('executable_sha256'):
            self.update(job_id,'blocked','tool_version_or_executable_changed_create_new_plan');return self.state.get_job(job_id)
        if command['protocol_hash']!=digest(self.state.protocol(job['protocol_id'])):
            raise ValueError('Frozen protocol mismatch')
        with self.state.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            claim=db.execute("UPDATE calculation_job SET status='running',attempt=attempt+1,started_at=? WHERE job_id=? AND status IN ('awaiting_confirmation','ready','blocked','failed')",(now(),job_id))
            if claim.rowcount!=1: return self.state.get_job(job_id)
        current=self.state.get_job(job_id)
        folder=self.state.root/'multi_jobs'/job_id/('attempt_'+str(current['attempt']))
        folder.mkdir(parents=True,exist_ok=False)
        request={**command['request'],'candidate_id':job['candidate_id'],'tool_id':job['tool_id'],
                 'protocol':self.state.protocol(job['protocol_id']),'executable':info['executable_path']}
        write_json(folder/'request.json',request)
        argv=adapt.build_command(self.state.project,folder/'request.json')
        manifest={'argv':argv,'cwd':str(folder),'job_id':job_id,'expected_outputs':['result.json'],
                  'timeout_seconds':request.get('timeout_seconds',300),'protocol_hash':command['protocol_hash']}
        write_json(folder/'command.json',manifest)
        self.update(job_id,'running',stdout_path=str(folder/'stdout.txt'),stderr_path=str(folder/'stderr.txt'))
        flags=(subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP) if os.name=='nt' else 0
        try:
            proc=subprocess.Popen([sys.executable,str(self.state.project/'src/workspace/multi_supervisor.py'),str(folder/'command.json')],
                                   cwd=folder,env=child_environment(),creationflags=flags)
            proc.wait()
        except OSError as e:
            self.update(job_id,'failed',str(e),return_code=-1,completed_at=now())
        return self.recover(job_id)

    def recover(self,job_id):
        job=self.state.get_job(job_id)
        if job['status'] not in {'running','completed'}: return job
        folder=self.state.root/'multi_jobs'/job_id/('attempt_'+str(job['attempt']))
        if job['status']=='completed':
            for a in json.loads(job['output_artifacts']): self.state.verify_artifact(a['artifact_hash'])
        receipt_path=folder/'receipt.json'
        if not receipt_path.is_file():
            process_file=folder/'process.json'
            if process_file.is_file():
                sys.path.insert(0,str(self.state.project/'workspace_local/tool_deps'))
                try:
                    import psutil
                    p=json.loads(process_file.read_text(encoding='utf-8'))
                    alive=False
                    for role in ['supervisor','child']:
                        try:
                            actual=psutil.Process(p[role+'_pid'])
                            alive |= abs(actual.create_time()-p[role+'_created'])<.01 and actual.is_running()
                        except psutil.NoSuchProcess: pass
                    if not alive:
                        self.update(job_id,'failed','interrupted_process_absent_explicit_retry_required',completed_at=now())
                        return self.state.get_job(job_id)
                except (ImportError,KeyError,OSError,TypeError): pass
            return {**job,'recovery':'unknown_liveness_no_duplicate_launch'}
        receipt=json.loads(receipt_path.read_text(encoding='utf-8'))
        try:
            if receipt['command_sha256']!=file_hash(folder/'command.json'): raise ValueError('Command tampered')
            if receipt['return_code']!=0:
                self.update(job_id,'failed',receipt.get('error') or 'Native process failed',return_code=receipt['return_code'],completed_at=receipt['completed_at'])
                return self.state.get_job(job_id)
            path=folder/'result.json'
            if file_hash(path)!=receipt['result_sha256']: raise ValueError('Result hash changed')
            info=self.capabilities['tools'][job['tool_id']];adapt=adapter(info)
            result=adapt.parse_output(path,job['candidate_id'])
            artifacts=[self.state.artifact(path),self.state.artifact(folder/'command.json'),self.state.artifact(receipt_path)]
            for item in receipt['artifacts']:
                p=Path(item['path']).resolve()
                if not p.is_relative_to(folder.resolve()) or file_hash(p)!=item['sha256']: raise ValueError('Native artifact changed')
                artifacts.append(self.state.artifact(p))
            if job['status']!='completed':
                self.update(job_id,'completed',return_code=0,completed_at=receipt['completed_at'],output_artifacts=encode(artifacts))
            # Idempotent registration also repairs interruption after completed compute.
            adapt.register_evidence(self.state,self.state.get_job(job_id),artifacts[0],result)
            return {**self.state.get_job(job_id),'cache_hit':job['status']=='completed'}
        except Exception as e:
            if job['status']=='completed': raise
            self.update(job_id,'failed','Output validation: '+str(e),completed_at=now())
            return self.state.get_job(job_id)

    def output(self,job_id,suffix):
        job=self.state.get_job(job_id)
        if job['status']!='completed': return None
        for a in json.loads(job['output_artifacts']):
            p=self.state.verify_artifact(a['artifact_hash'])
            if p.name.endswith(suffix): return {'path':str(p),'sha256':a['artifact_hash']}
        return None
