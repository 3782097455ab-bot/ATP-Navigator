"""Research intent -> real jobs -> shared evidence -> preserved decision -> panel."""
from __future__ import annotations
import json
from dataclasses import asdict
from pathlib import Path
import pandas as pd
from .state import State, now, file_hash, digest, encode, write_json
from .tool_capabilities import discover
from .protocols import discover_protocol, rdkit_protocol
from .planner import parse_intent, acquire, gate, PREDECESSOR
from .execution import Executor
from .evidence_bridge import build_library, import_library, planner_candidates, run_decision


def model_hashes(project):
    return {str(p.relative_to(project)):file_hash(p) for p in sorted((Path(project)/'models').rglob('*')) if p.is_file()}


class ComputationalWorkspace:
    def __init__(self,project_root,runtime_root=None):
        self.state=State(project_root,runtime_root)

    def run(self,project_id,text,library='internal',input_path=None,session_id=None,protocol_path=None,
            knowledge_dir=None,confirmed=False,output_dir=None):
        if not confirmed:
            return {'status':'confirmation_required','structured_intent':asdict(parse_intent(text)),
                    'library':library,'no_computations_started':True}
        state=self.state
        state.project_id(project_id)
        intent=parse_intent(text)
        before=model_hashes(state.project)
        batch=state.batch(project_id,asdict(intent),session_id)
        output=Path(output_dir or state.project/'results/phase12'/batch)
        output.mkdir(parents=True,exist_ok=False)
        write_json(output/'research_intent.json',{'text':text,'structured_intent':asdict(intent),'confirmation':'explicit_user_or_cli_yes'})
        if session_id:
            with state.connect() as db:
                session=db.execute('SELECT * FROM sessions WHERE id=?',(session_id,)).fetchone()
            if not session:
                raise ValueError('Unknown Phase11 session')
            input_path=Path(session['input_path'])
            if file_hash(input_path)!=session['input_sha256']:
                raise ValueError('Session input hash changed')
        if input_path:
            input_path=Path(input_path).resolve()
            lineage={'library':'user_input','source_kind':'supplied_computational_evidence_not_independently_verified',
                     'input_sha256':file_hash(input_path),'source_files':[str(input_path)]}
        else:
            input_path=output/'candidate_library.csv'
            lineage=build_library(state.project,library,input_path)
        if not session_id:
            from research_workspace import ResearchWorkspace
            session_id=ResearchWorkspace(state.project,state.root).create_session(input_path)
            with state.connect() as db:
                db.execute('UPDATE calculation_batch SET session_id=? WHERE batch_id=?',(session_id,batch))
        state.event(session_id,'computation_intent_confirmed',{'batch_id':batch,'intent':asdict(intent)})
        licensing=state.project/'configs/workspace_license_features.json'
        capability=discover(output/'system_capabilities.json',license_features=json.loads(licensing.read_text()) if licensing.is_file() else None)
        # Top-level pointer/capability snapshot requested by Phase12; immutable copy is in the run directory.
        write_json(state.project/'results/system_capabilities.json',capability)
        historical=discover_protocol(state.project,output/'protocol_manifest.json')
        state.freeze_protocol(historical)
        active=json.loads(Path(protocol_path).read_text(encoding='utf-8')) if protocol_path else historical
        state.freeze_protocol(active)
        ids,import_job=import_library(state,project_id,batch,input_path,historical['protocol_id'],lineage)
        if intent.expected_candidates is not None and intent.expected_candidates!=len(ids):
            raise ValueError(f'Candidate count mismatch: requested {intent.expected_candidates}, actual {len(ids)}; confirm corrected scope')
        archive=state.artifact(input_path)
        rdprotocol=rdkit_protocol(capability['tools']['rdkit']['version'])
        state.freeze_protocol(rdprotocol)
        rdjob=state.job(batch,project_id,'__library__','rdkit',rdprotocol['protocol_id'],[archive],
                        {'action':'structure_qc','stage':'structure_qc','worker_sha256':file_hash(state.project/'src/workspace/rdkit_worker.py')})
        executor=Executor(state,capability)
        old_attempt=state.get_job(rdjob)['attempt']
        rdresult=executor.launch(rdjob)
        jobs=[import_job,rdjob]
        plan={'project_id':project_id,'session_id':session_id,'batch_id':batch,'candidate_count':len(ids),
              'intent':asdict(intent),'stages':[],'protocol_id':active['protocol_id'],'candidate_ids':ids,
              'input_path':str(input_path),'input_sha256':file_hash(input_path),'output_directory':str(output),
              'planning_note':'Future-stage slots are not chosen/executed until predecessor evidence exists; historical mode/protocol uncertainty is retained.',
              'acquisition_formula':'(.40 rank_utility+.20 missing_fraction+.15 observed_uncertainty+.15 observed_disagreement+.10 scaffold_novelty)/relative_cost'}
        stage_limits={'HTVS':len(ids),'SP':intent.sp_budget,'XP':intent.xp_budget,'MMGBSA':intent.mmgbsa_budget,
                      'QikProp':intent.sp_budget,'MD':intent.md_budget}
        tool_for={'HTVS':'glide','SP':'glide','XP':'glide','MMGBSA':'prime_mmgbsa','QikProp':'qikprop','MD':'desmond'}
        all_acquisition=[]
        plan['stage_limits']=stage_limits
        write_json(output/'calculation_plan.json',plan)
        with state.connect() as db:
            db.execute('UPDATE calculation_batch SET plan=? WHERE batch_id=?',(encode(plan),batch))
        compatible={active['protocol_id'],*active.get('approved_predecessor_protocol_ids',[])}
        for stage,limit in stage_limits.items():
            candidates,stages=planner_candidates(state,project_id,ids,compatible)
            for candidate in candidates:
                candidate['relative_cost']={'HTVS':2,'SP':10,'XP':20,'MMGBSA':50,'QikProp':5,'MD':500}[stage]
            needs=[c for c in candidates if stage not in stages[c['compound_id']]]
            selected=gate(needs,stage,stages,limit,diverse=intent.preserve_scaffold_diversity) if limit else []
            row={'stage':stage,'budget':limit,'existing_stage_evidence':len(candidates)-len(needs),
                 'eligible':len(selected),'planned_candidate_ids':[r['compound_id'] for r in selected],
                 'deferred_slots':max(0,min(limit,len(needs))-len(selected)),
                 'status':'planned' if selected else ('not_requested' if limit==0 else 'existing_or_awaiting_predecessor')}
            plan['stages'].append(row)
            write_json(output/'calculation_plan.json',plan)
            with state.connect() as db:
                db.execute('UPDATE calculation_batch SET plan=? WHERE batch_id=?',(encode(plan),batch))
            all_acquisition.extend({**c,'stage':stage} for c in selected)
            for candidate in selected:
                compound=candidate['compound_id']
                prepared=active.get('prepared_inputs',{}).get(compound,{}).get(stage)
                inputs=[archive]
                if prepared and Path(prepared['path']).is_file():
                    if file_hash(prepared['path'])!=prepared['sha256']:
                        raise ValueError('Prepared input checksum mismatch')
                    inputs.append(state.artifact(prepared['path']))
                command={'tool_id':tool_for[stage],'candidate_id':compound,'stage':stage,'predecessor':PREDECESSOR[stage],
                         'prepared_input':prepared,'grid':active.get('grid'),
                         'cli_arguments':active.get('mmgbsa_protocol',{}).get('cli_arguments',[]) if isinstance(active.get('mmgbsa_protocol'),dict) and stage=='MMGBSA' else [],
                         'worker_sha256':file_hash(state.project/'src/workspace/schrodinger_worker.py')}
                job=state.job(batch,project_id,compound,tool_for[stage],active['protocol_id'],inputs,command)
                jobs.append(job)
                # Planning can use historical rankings, execution cannot silently mix protocols.
                previous=PREDECESSOR[stage]
                actual_predecessor=previous=='structure_qc' and previous in stages[compound]
                if previous!='structure_qc':
                    actual_predecessor=any(e['compound_id']==compound and e['protocol_id'] in compatible and
                        ((json.loads(e['provenance']).get('stage')==previous and e['evidence_type']=='docking_score') or
                         (previous=='MMGBSA' and e['evidence_type']=='mmgbsa_score')) for e in state.evidence_rows(project_id))
                executor.launch(job,actual_predecessor)
            # A concrete blocked gate job records why the remaining budget cannot yet be allocated.
            if not selected and needs and limit:
                job=state.job(batch,project_id,'__pending_'+stage+'__',tool_for[stage],active['protocol_id'],[],
                              {'stage':stage,'predecessor':PREDECESSOR[stage],'budget_slots':min(limit,len(needs))})
                jobs.append(job)
                executor.block(job,['stage_gate_missing_'+PREDECESSOR[stage],*executor.readiness(job,False)])
        pd.DataFrame(all_acquisition,columns=['stage','compound_id','current_rank','scaffold','evidence_completeness',
                     'uncertainty','model_disagreement','relative_cost','acquisition_rank','acquisition_score','reason','interpretation']).to_csv(output/'next_calculation_candidates.csv',index=False)
        write_json(output/'calculation_plan.json',plan)
        with state.connect() as db:
            db.execute('UPDATE calculation_batch SET plan=? WHERE batch_id=?',(encode(plan),batch))
        decision=run_decision(state,project_id,batch,session_id,ids,active['protocol_id'],intent.research_profile,
                              output/'decision',intent.final_experiment_budget)
        followup,followup_stages=planner_candidates(state,project_id,ids,compatible)
        proposals=acquire([c for c in followup if 'MMGBSA' not in followup_stages[c['compound_id']]],
                          intent.mmgbsa_budget,intent.preserve_scaffold_diversity)
        for proposal in proposals:
            proposal['stage_gate']='eligible_for_protocol_check' if 'XP' in followup_stages[proposal['compound_id']] else 'blocked_pending_XP'
            proposal['executed']=False
        pd.DataFrame(proposals,columns=['compound_id','current_rank','rank_source','scaffold','evidence_completeness',
                     'uncertainty','model_disagreement','relative_cost','acquisition_rank','acquisition_score','reason',
                     'stage_gate','executed','interpretation']).to_csv(output/'mmgbsa_acquisition_proposals.csv',index=False)
        knowledge={}
        if knowledge_dir:
            from .knowledge_qc import import_knowledge
            knowledge=import_knowledge(state,knowledge_dir,output/'knowledge_qc')
        after=model_hashes(state.project)
        if before!=after:
            raise RuntimeError('Historical model integrity changed')
        actual=[state.get_job(j) for j in dict.fromkeys(jobs)]
        pd.DataFrame(actual).to_csv(output/'calculation_jobs.csv',index=False)
        pd.DataFrame(state.evidence_rows(project_id)).to_csv(output/'evidence_registry.csv',index=False)
        summary={'batch_id':batch,'project_id':project_id,'session_id':session_id,'candidate_count':len(ids),
                 'tool_execution_completed':sum(j['status']=='completed' and j['tool_id']=='rdkit' for j in actual),
                 'rdkit_execution_reused':rdresult['attempt']==old_attempt,
                 'commercial_execution_completed':sum(j['status']=='completed' and j['tool_id'] in {'glide','prime_mmgbsa','qikprop'} for j in actual),
                 'blocked_jobs':sum(j['status']=='blocked' for j in actual),
                 'failed_jobs':sum(j['status']=='failed' for j in actual),'decision':decision,
                 'historical_model_hashes_unchanged':before==after,'model_hashes':after,'knowledge_qc':knowledge,
                 'training_performed':False,'experimental_measurements_generated':0,'output_directory':str(output),
                 'limitations':['Commercial adapters not validated on this machine without installation/license/grid.',
                                'Historical docking protocol incomplete; no assertion of new-protocol equivalence.',
                                'Acquisition is a transparent heuristic, not validated information gain.',
                                'No experimental outcome or performance improvement claimed.']}
        write_json(output/'execution_summary.json',summary)
        with state.connect() as db:
            db.execute('UPDATE calculation_batch SET actual=? WHERE batch_id=?',(encode({k:v for k,v in summary.items() if k!='decision'}),batch))
        state.event(session_id,'computation_batch_finished',{'batch_id':batch,'decision_run_id':decision['decision_run_id'],'output_directory':str(output)})
        return summary

    def recover_batch(self,batch_id):
        """Reconcile durable receipts; never blindly relaunch an unknown running job.

        New scheduling after recovery requires the usual new, confirmed intent.
        Successful signatures are reused even in a new batch/session.
        """
        with self.state.connect() as db:
            batch=db.execute('SELECT * FROM calculation_batch WHERE batch_id=?',(batch_id,)).fetchone()
            jobs=[dict(r) for r in db.execute('SELECT * FROM calculation_job WHERE batch_id=?',(batch_id,))]
        if not batch:
            raise ValueError('Unknown batch')
        executor=Executor(self.state,discover())
        reconciled=[]
        for job in jobs:
            if job['status']=='running' or (job['status']=='completed' and job['tool_id'] in {'rdkit','glide','prime_mmgbsa','qikprop'}):
                reconciled.append(executor.recover(job['job_id']))
            else:
                reconciled.append(job)
        result={'batch_id':batch_id,'jobs':reconciled,'new_executions':0,
                'next_step':'Submit the same confirmed intent to continue scheduling; completed input/protocol/command signatures are reused.'}
        self.state.event(batch['session_id'],'batch_recovery',{'batch_id':batch_id,'statuses':[j['status'] for j in reconciled]})
        return result
