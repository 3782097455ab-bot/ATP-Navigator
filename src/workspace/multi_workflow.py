"""Multi-backend DAG over the existing Project State, not a parallel datastore."""
import csv
import json
from pathlib import Path
import sys
import uuid
import pandas as pd
from .state import State,encode,now,write_json,file_hash,digest
from .multi_executor import MultiExecutor
from .multi_planner import intent,allocate,topological_nodes
from .multi_evidence import completeness,enriched,decide,cohort_rankings
from tools.tool_registry import discover
from tools.vina_adapter import VinaAdapter,validate_box

MODES={'commercial_full','open_toolchain','decision_only'}


class MultiBackendWorkspace:
    def __init__(self,project_root,runtime_root=None,capabilities=None):
        self.state=State(project_root,runtime_root);self.capabilities=capabilities
        from research_workspace import ResearchWorkspace
        self.chat_workspace=ResearchWorkspace(project_root,self.state.root)
        with self.state.connect() as db:
            db.executescript('''
            CREATE TABLE IF NOT EXISTS workflow_run(run_id TEXT PRIMARY KEY,project_id TEXT,session_id TEXT,
                mode TEXT,protocol_id TEXT,intent TEXT,candidate_ids TEXT,input_artifact TEXT,created_at TEXT,
                confirmed INTEGER DEFAULT 0,status TEXT,capabilities TEXT,output_dir TEXT,source_metadata TEXT);
            CREATE TABLE IF NOT EXISTS workflow_node(run_id TEXT,node_id TEXT,dependencies TEXT,status TEXT,
                selection TEXT,jobs TEXT,reason TEXT,PRIMARY KEY(run_id,node_id));
            CREATE TABLE IF NOT EXISTS workflow_job_link(run_id TEXT,job_id TEXT,PRIMARY KEY(run_id,job_id));
            CREATE TABLE IF NOT EXISTS workflow_feedback_link(calculation_run_id TEXT,decision_run_id TEXT,
                candidate_panel_id TEXT,experiment_run_id TEXT,project_id TEXT,PRIMARY KEY(calculation_run_id,decision_run_id));
            CREATE TABLE IF NOT EXISTS workflow_experiment_link(calculation_run_id TEXT,decision_run_id TEXT,
                candidate_panel_id TEXT,experiment_run_id TEXT,project_id TEXT,record_ids TEXT,snapshot_id TEXT,
                PRIMARY KEY(calculation_run_id,decision_run_id,experiment_run_id));
            ''')

    def get_run(self,run_id):
        with self.state.connect() as db:
            row=db.execute('SELECT * FROM workflow_run WHERE run_id=?',(run_id,)).fetchone()
        if not row: raise ValueError('Unknown calculation run')
        return dict(row)

    def capabilities_for(self,run=None):
        if self.capabilities is not None: return self.capabilities
        return json.loads(run['capabilities']) if run else discover(self.state.project)

    def create(self,project_id,input_path,text,mode='decision_only',protocol=None,source_metadata=None,session_id=None):
        if mode not in MODES: raise ValueError('Unknown backend mode')
        state=self.state;state.project_id(project_id);input_path=Path(input_path).resolve()
        frame=pd.read_csv(input_path,dtype=str,keep_default_na=False)
        if not {'compound_id','SMILES'}<=set(frame.columns) or frame.empty or frame.compound_id.duplicated().any():
            raise ValueError('Nonempty candidate CSV requires unique compound_id and SMILES')
        parsed=intent(text)
        policy=state.project/'configs/acquisition_policy.json'
        if policy.is_file(): parsed['allocation']=json.loads(policy.read_text(encoding='utf-8'))['allocation']
        if parsed['expected_candidates'] not in (None,len(frame)): raise ValueError('Declared candidate count does not match input')
        protocol=dict(protocol or json.loads((state.project/'configs/projects/ab_atp_synthase/docking_protocol.json').read_text(encoding='utf-8')))
        if 'protocol_id' not in protocol: raise ValueError('Explicit protocol_id required')
        for key in ['receptor','grid']:
            item=protocol.get(key)
            if item:
                item=dict(item);path=Path(item['path'])
                item['path']=str((state.project/path).resolve() if not path.is_absolute() else path.resolve())
                protocol[key]=item
                if file_hash(item['path'])!=item['sha256']: raise ValueError(key+' hash mismatch')
                state.artifact(item['path'])
        for candidate,item in protocol.get('reference_poses',{}).items():
            item=dict(item);path=Path(item['path'])
            item['path']=str((state.project/path).resolve() if not path.is_absolute() else path.resolve())
            protocol['reference_poses'][candidate]=item
            if file_hash(item['path'])!=item['sha256']:
                raise ValueError('reference pose hash mismatch: '+candidate)
            state.artifact(item['path'])
        state.freeze_protocol(protocol)
        for row in frame.to_dict('records'):
            state.candidate(project_id,row['compound_id'],row['SMILES'],row.get('historical_alias',''))
        archive=state.artifact(input_path)
        if session_id:
            with state.connect() as db:
                old=db.execute('SELECT * FROM sessions WHERE id=?',(session_id,)).fetchone()
            if not old or old['input_sha256']!=archive['artifact_hash']: raise ValueError('Session input identity mismatch')
            session=session_id
        else: session=self.chat_workspace.create_session(input_path)
        batch=state.batch(project_id,parsed,session);caps=self.capabilities_for()
        output=state.project/'results/multibackend'/batch;output.mkdir(parents=True,exist_ok=False)
        source_metadata=source_metadata or {}
        with state.connect() as db:
            db.execute('INSERT INTO workflow_run VALUES (?,?,?,?,?,?,?,?,?,0,?,?,?,?)',
                       (batch,project_id,session,mode,protocol['protocol_id'],encode(parsed),encode(frame.compound_id.tolist()),
                        encode(archive),now(),'awaiting_confirmation',encode(caps),str(output),encode(source_metadata)))
            graph={'import':[],'structure_qc':['import'],'receptor_preparation':['import'],
                   'ligand_preparation':['structure_qc'],'commercial_ligprep':['ligand_preparation'],
                   'docking':['ligand_preparation','receptor_preparation'],'stronger_docking':['docking'],
                   'pose_qc':['docking'],'mmgbsa':['pose_qc'],'properties':['structure_qc'],
                   'evidence_completeness':['mmgbsa','properties'],'decision':['evidence_completeness']}
            if mode=='commercial_full':
                graph['docking']=['commercial_ligprep','receptor_preparation']
                if parsed['xp_budget']>0: graph['pose_qc']=['stronger_docking']
            topological_nodes(graph)
            for node,deps in graph.items():
                db.execute('INSERT INTO workflow_node VALUES (?,?,?,?,?,?,?)',(batch,node,encode(deps),'planned','[]','{}',''))
        write_json(output/'plan.json',{'run_id':batch,'project_id':project_id,'session_id':session,'mode':mode,
                 'structured_intent':parsed,'protocol':protocol,'dag':graph,'candidate_count':len(frame),'status':'awaiting_confirmation'})
        write_json(output/'system_capabilities.json',caps)
        state.event(session,'calculation_plan_created',{'run_id':batch,'confirmation_required':True,'mode':mode})
        return {'run_id':batch,'session_id':session,'status':'awaiting_confirmation','structured_intent':parsed,'output_dir':str(output)}

    def node(self,run,node):
        with self.state.connect() as db:
            return dict(db.execute('SELECT * FROM workflow_node WHERE run_id=? AND node_id=?',(run,node)).fetchone())

    def set_node(self,run,node,status,selection=None,jobs=None,reason=''):
        old=self.node(run,node)
        with self.state.connect() as db:
            db.execute('UPDATE workflow_node SET status=?,selection=?,jobs=?,reason=? WHERE run_id=? AND node_id=?',
                (status,encode(selection) if selection is not None else old['selection'],encode(jobs) if jobs is not None else old['jobs'],reason,run,node))

    def import_evidence(self,run):
        state=self.state;archive=json.loads(run['input_artifact']);state.verify_artifact(archive['artifact_hash'])
        if run['mode']!='decision_only': return
        metadata=json.loads(run['source_metadata']);frame=pd.read_csv(archive['path'],dtype=str,keep_default_na=False)
        if 'docking_score' in frame and metadata.get('source_tool') not in {'glide','vina'}:
            raise ValueError('Unsupported/unknown docking backend; do not reinterpret as Glide')
        if not metadata.get('source_tool') or not metadata.get('source_batch'):
            if any(k in frame.columns for k in ['docking_score','mmgbsa_score']):
                raise ValueError('Imported scores require explicit source_tool/source_batch/protocol provenance')
        job=state.job(run['run_id'],run['project_id'],'__library__','computational_import',run['protocol_id'],[archive],
                      {'action':'QC_import','source_metadata':metadata,'input_hash':archive['artifact_hash']})
        rows=[]
        for row in frame.to_dict('records'):
            for key in ['docking_score','mmgbsa_score','quickprop_features','docking_features','admet_features']:
                value=row.get(key,'')
                if value in {'','unknown','{}'}: continue
                value=json.loads(value) if key.endswith('_features') else float(value)
                field='vina_affinity' if key=='docking_score' and metadata.get('source_tool')=='vina' else key
                tool=metadata.get('source_tool') if key=='docking_score' else metadata.get('mmgbsa_tool','unknown') if key=='mmgbsa_score' else metadata.get(key+'_tool','historical_property_source')
                rows.append({'compound_id':row['compound_id'],'evidence_type':field,'raw_value':value,
                    'unit':('kcal/mol' if field in {'vina_affinity','mmgbsa_score'} else 'Glide_score' if field=='docking_score' else 'property_bundle'),
                    'provenance':{**metadata,'tool_id':tool,'backend':'historical_import','source_batch':metadata.get('source_batch')}})
        encode(rows)  # Reject nonfinite/nonnumeric JSON before marking the import completed.
        with state.connect() as db:
            db.execute("UPDATE calculation_job SET status='completed',completed_at=?,return_code=0,output_artifacts=? WHERE job_id=?",
                       (now(),encode([archive]),job))
            db.execute('INSERT OR IGNORE INTO workflow_job_link VALUES (?,?)',(run['run_id'],job))
        state.register_many(run['project_id'],job,archive['artifact_hash'],rows,'historical_result')

    def candidates_for(self,run,ids):
        from rdkit import Chem
        from rdkit.Chem.Scaffolds import MurckoScaffold
        with self.state.connect() as db:
            candidates={r['candidate_id']:dict(r) for r in db.execute('SELECT * FROM candidate WHERE project_id=?',(run['project_id'],))}
        records=[r for r in enriched(self.state,run['project_id']) if r['protocol_id']==run['protocol_id'] and r['compound_id'] in ids]
        if any(r['evidence_type']=='glide_xp_score' for r in records):
            records=[r for r in records if r['evidence_type'] not in {'glide_score','docking_score'}]
        ranks=cohort_rankings(records);cohorts={r['cohort'] for r in ranks if r['evidence_type'] in {'glide_score','glide_xp_score','vina_affinity','docking_score'}}
        rankmap={r['compound_id']:r['cohort_rank'] for r in ranks if r['cohort'] in cohorts} if len(cohorts)==1 else {}
        missing={r['compound_id']:r for r in completeness(self.state,run['project_id'],ids,run['protocol_id'])}
        result=[]
        for cid in ids:
            row={'compound_id':cid,'current_rank':rankmap.get(cid,'unknown'),'uncertainty':'unknown','model_disagreement':'unknown',
                 'scaffold':MurckoScaffold.MurckoScaffoldSmiles(mol=Chem.MolFromSmiles(candidates[cid]['smiles'])),
                 'evidence_completeness':sum(missing[cid][k] for k in ['docking','MMGBSA','ADMET'])/3,'relative_cost':1}
            # Only observed same-project model disagreement, never manufactured uncertainty.
            for evidence in records:
                if evidence['compound_id']==cid and evidence['evidence_type']=='model_rank_disagreement': row['model_disagreement']=evidence['value']
                if evidence['compound_id']==cid and evidence['evidence_type']=='decision_metrics':
                    value=evidence['value']
                    if {'rank_p05','rank_p95'}<=set(value): row['uncertainty']=(value['rank_p95']-value['rank_p05'])/max(len(ids)-1,1)
            result.append(row)
        return result

    def resume(self,run_id,confirm=False,retry_failed=False,max_new_docking_jobs=None):
        if max_new_docking_jobs is not None and (type(max_new_docking_jobs) is not int or max_new_docking_jobs<1):
            raise ValueError('max_new_docking_jobs must be a positive integer')
        run=self.get_run(run_id);state=self.state;output=Path(run['output_dir'])
        if confirm:
            with state.connect() as db: db.execute('UPDATE workflow_run SET confirmed=1 WHERE run_id=?',(run_id,))
            state.event(run['session_id'],'calculation_plan_confirmed',{'run_id':run_id,'expensive_scope':json.loads(run['intent'])})
            run=self.get_run(run_id)
        if not run['confirmed']: return {'status':'awaiting_confirmation','run_id':run_id,'executed':0}
        caps=self.capabilities_for(run);executor=MultiExecutor(state,caps);ids=json.loads(run['candidate_ids']);p=state.protocol(run['protocol_id']);cfg=json.loads(run['intent'])
        new_docking_jobs=0;cache_hits=0
        archive=json.loads(run['input_artifact']);frame=pd.read_csv(state.verify_artifact(archive['artifact_hash']),dtype=str,keep_default_na=False).set_index('compound_id')
        self.import_evidence(run);self.set_node(run_id,'import','completed',ids)
        with state.connect() as db:
            oldjobs=[r[0] for r in db.execute('SELECT job_id FROM workflow_job_link WHERE run_id=?',(run_id,))]
        for j in oldjobs:
            if state.get_job(j)['tool_id']!='computational_import': executor.recover(j)
        mode=run['mode'];costs={'docking':2,'stronger_docking':10,'mmgbsa':50,'properties':1}
        with state.connect() as db:
            graph={r['node_id']:json.loads(r['dependencies']) for r in db.execute('SELECT * FROM workflow_node WHERE run_id=?',(run_id,))}
        stages=[s for s in topological_nodes(graph) if s not in {'import','evidence_completeness','decision'}]
        for stage in stages:
            node=self.node(run_id,stage)
            if node['status']=='completed' or node['status']=='skipped': continue
            if mode=='decision_only' and stage not in {'structure_qc','properties'}:
                self.set_node(run_id,stage,'skipped',reason='decision_only_import_no_computation_requested');continue
            if mode!='commercial_full' and stage in {'commercial_ligprep','stronger_docking'}:
                self.set_node(run_id,stage,'skipped',reason='backend_has_no_Glide_XP_stage');continue
            if stage=='mmgbsa' and mode=='open_toolchain':
                self.set_node(run_id,stage,'skipped' if cfg['mmgbsa_budget']==0 else 'blocked',reason='explicit_zero_budget' if cfg['mmgbsa_budget']==0 else 'open_MMGBSA_adapter_reserved_not_implemented; Vina_is_not_MMGBSA');continue
            limit=cfg['docking_budget'] if stage=='docking' else cfg['xp_budget'] if stage=='stronger_docking' else cfg['mmgbsa_budget'] if stage=='mmgbsa' else len(ids)
            if limit==0:
                self.set_node(run_id,stage,'skipped',reason='explicit_zero_budget');continue
            deps=json.loads(node['dependencies']);eligible=list(ids)
            for dep in deps:
                parent=self.node(run_id,dep);jobs=json.loads(parent['jobs'])
                if dep=='import': continue
                if dep=='receptor_preparation':
                    if parent['status']!='completed': eligible=[]
                else: eligible=[c for c in eligible if c in jobs and state.get_job(jobs[c])['status']=='completed']
            if stage=='receptor_preparation':
                if mode=='commercial_full':
                    okay=p.get('grid') and p.get('receptor') and p.get('confirmation')=='researcher_confirmed'
                    self.set_node(run_id,stage,'completed' if okay else 'blocked',reason='hash_pinned_receptor_and_grid' if okay else 'historical_grid_missing_or_new_protocol_unconfirmed');continue
                if not p.get('receptor'):
                    self.set_node(run_id,stage,'blocked',reason='receptor_not_selected');continue
                if p.get('confirmation') not in {'researcher_confirmed','official_tutorial_smoke_only'}:
                    self.set_node(run_id,stage,'blocked',reason='new_receptor_and_box_protocol_confirmation_required');continue
                eligible=ids[:1]  # one shared receptor preparation artifact; no dummy candidate identity
            selection=json.loads(node['selection'])
            if not selection and eligible:
                options=self.candidates_for(run,eligible)
                for option in options: option['relative_cost']=costs.get(stage,1)
                selection=[r['compound_id'] for r in allocate(options,limit,cfg['allocation'],cfg['preserve_scaffold_diversity'])]
                write_json(output/(stage+'_selection.json'),{'selected':selection,'budget':limit,'allocation':cfg['allocation'],
                           'reasoned_selection':allocate(options,limit,cfg['allocation'],cfg['preserve_scaffold_diversity'])})
            if not selection:
                self.set_node(run_id,stage,'blocked',reason='predecessor_evidence_missing: '+','.join(deps));continue
            jobs=json.loads(node['jobs'])
            for cid in selection:
                if cid not in eligible: continue
                request={'stage':stage,'smiles':frame.loc[cid,'SMILES'],'backend':mode}
                tool='rdkit';problems=[];inputs=[archive]
                if stage=='ligand_preparation':
                    tool='meeko' if mode=='open_toolchain' else 'rdkit'
                    if p.get('ligand_preparation')!='ETKDGv3_MMFF_preserve_input': problems.append('ligand_preparation_protocol_unconfirmed')
                elif stage=='receptor_preparation':
                    tool='meeko';request['receptor']=p['receptor']
                elif stage=='commercial_ligprep':
                    tool='ligprep';request['ligand']=executor.output(json.loads(self.node(run_id,'ligand_preparation')['jobs'])[cid],'ligand.sdf')
                    request['stage']='ligprep'
                elif stage in {'docking','stronger_docking'}:
                    tool='vina' if mode=='open_toolchain' else 'glide';request['stage']='docking';request['precision']='XP' if stage=='stronger_docking' else p.get('precision','SP')
                    prep='ligand_preparation' if mode=='open_toolchain' else 'commercial_ligprep'
                    suffix='ligand.pdbqt' if mode=='open_toolchain' else 'prepared.sdf'
                    request['ligand']=executor.output(json.loads(self.node(run_id,prep)['jobs'])[cid],suffix)
                    if mode=='open_toolchain':
                        rjobs=json.loads(self.node(run_id,'receptor_preparation')['jobs'])
                        request['receptor']=executor.output(next(iter(rjobs.values())),'receptor.pdbqt')
                        try: validate_box(p.get('box'))
                        except (ValueError,TypeError) as e: problems.append(str(e))
                elif stage in {'pose_qc','mmgbsa'}:
                    source='stronger_docking' if mode=='commercial_full' and cfg['xp_budget']>0 else 'docking'
                    sourcejobs=json.loads(self.node(run_id,source)['jobs'])
                    request['pose']=executor.output(sourcejobs[cid],'pose.pdbqt' if mode=='open_toolchain' else 'dock_pv.maegz')
                    if stage=='mmgbsa':
                        tool='prime_mmgbsa'
                        if not isinstance(p.get('mmgbsa'),dict) or any(p['mmgbsa'].get(k) in (None,'unknown') for k in ['job_type','force_field','solvation_model','receptor_flexibility']):
                            problems.append('MMGBSA_protocol_unconfirmed')
                    elif mode=='commercial_full': tool='glide';request['tool_id_override']='commercial_pose_qc'
                    else:
                        ligand_jobs=json.loads(self.node(run_id,'ligand_preparation')['jobs'])
                        request['ligand']=executor.output(ligand_jobs[cid],'ligand.pdbqt')
                        reference=p.get('reference_poses',{}).get(cid)
                        if reference: request['reference_pose']=reference
                elif stage=='properties' and mode=='commercial_full':
                    tool='qikprop'
                    preps=json.loads(self.node(run_id,'commercial_ligprep')['jobs'])
                    request['ligand']=executor.output(preps[cid],'prepared.sdf') if cid in preps else None
                if stage not in {'structure_qc','properties'} and p.get('confirmation') not in {'researcher_confirmed','official_tutorial_smoke_only'}:
                    problems.append('protocol_confirmation_required')
                for field in ['ligand','pose','receptor','reference_pose']:
                    if field in request:
                        if request[field] is None: problems.append(field+'_artifact_missing')
                        else: inputs.append(state.artifact(request[field]['path']))
                if p.get('grid'): inputs.append(state.artifact(p['grid']['path']))
                j=jobs.get(cid) or executor.plan(run_id,run['project_id'],cid,tool,run['protocol_id'],request,inputs)
                jobs[cid]=j;self.set_node(run_id,stage,'running',selection,jobs)
                if problems: executor.update(j,'blocked','; '.join(problems))
                else:
                    before=state.get_job(j)
                    completed=executor.run(j,retry=retry_failed)
                    if completed.get('cache_hit'): cache_hits+=1
                    if stage=='docking' and completed['status']=='completed' and completed['attempt']>before['attempt']:
                        new_docking_jobs+=1
                        if max_new_docking_jobs is not None and new_docking_jobs>=max_new_docking_jobs:
                            self.set_node(run_id,stage,'paused',selection,jobs,
                                          reason='controlled_interruption_after_real_docking_jobs')
                            paused=self.status(run_id)
                            paused.update({'status':'paused','controlled_interruption':True,
                                           'executed_new_docking_jobs':new_docking_jobs,'cache_hits':cache_hits})
                            write_json(output/('controlled_interruption_'+uuid.uuid4().hex[:10]+'.json'),paused)
                            return paused
            statuses=[state.get_job(j)['status'] for j in jobs.values()]
            status='completed' if len(jobs)==len(selection) and all(x=='completed' for x in statuses) else 'failed' if 'failed' in statuses else 'blocked'
            self.set_node(run_id,stage,status,selection,jobs,reason='' if status=='completed' else 'See candidate jobs and predecessor gates')
        self.set_node(run_id,'evidence_completeness','completed',ids,reason='assessed_not_imputed')
        snapshots=output/'decisions';snapshots.mkdir(exist_ok=True)
        # No repeated decision run if the selected evidence set did not change.
        digest_now=digest({'schema':'multi_backend_v1_registry_inference', 'evidence':[{k:r[k] for k in ['evidence_id','artifact_hash']} for r in state.evidence_rows(run['project_id']) if r['compound_id'] in ids and json.loads(r['provenance']).get('origin')!='frozen_model_output']})
        decision_folder=snapshots/digest_now[:16]
        if (decision_folder/'decision_summary.json').is_file(): decision=json.loads((decision_folder/'decision_summary.json').read_text(encoding='utf-8'))
        else:
            if decision_folder.exists(): decision_folder=snapshots/(digest_now[:16]+'_'+uuid.uuid4().hex[:6])
            decision=decide(state,run,decision_folder)
        self.set_node(run_id,'decision','completed',ids,reason='frozen_decision_evaluated; missing final scores remain unknown')
        result=self.status(run_id);result['decision']=decision
        result['executed_new_docking_jobs']=new_docking_jobs;result['cache_hits']=cache_hits
        write_json(output/('execution_snapshot_'+uuid.uuid4().hex[:10]+'.json'),result)
        with state.connect() as db: db.execute('UPDATE workflow_run SET status=? WHERE run_id=?',('completed_with_blocks' if result['blocked_nodes'] else 'completed',run_id))
        state.event(run['session_id'],'computation_resume_finished',{'run_id':run_id,'decision_run_id':decision['decision_run_id'],'training':False})
        return result

    def status(self,run_id):
        run=self.get_run(run_id)
        with self.state.connect() as db:
            nodes=[dict(r) for r in db.execute('SELECT * FROM workflow_node WHERE run_id=?',(run_id,))]
            jobs=[dict(r) for r in db.execute('SELECT j.* FROM calculation_job j JOIN workflow_job_link l ON j.job_id=l.job_id WHERE l.run_id=?',(run_id,))]
        return {'run_id':run_id,'project_id':run['project_id'],'mode':run['mode'],'session_id':run['session_id'],
                'confirmed':bool(run['confirmed']),'nodes':nodes,'jobs':jobs,'blocked_nodes':[n['node_id'] for n in nodes if n['status']=='blocked'],
                'evidence_count':len(self.state.evidence_rows(run['project_id'])),'training':False}
