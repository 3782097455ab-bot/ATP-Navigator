"""UI-ready local service functions; one state/registry, no independent chat cache."""
import json
from pathlib import Path
from .multi_workflow import MultiBackendWorkspace
from .multi_evidence import completeness,enriched


def session_calculation_action(workspace,session_id,text):
    with workspace._connect() as db:
        if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='workflow_run'").fetchone():
            return {'status':'project_context_required','message':'先通过CLI/API创建项目并选择候选与受体。'}
        row=db.execute('SELECT * FROM workflow_run WHERE session_id=? ORDER BY created_at DESC LIMIT 1',(session_id,)).fetchone()
    if not row: return {'status':'project_context_required'}
    run=dict(row);engine=MultiBackendWorkspace(workspace.project,workspace.root,json.loads(run['capabilities']))
    action,_,value=text.partition(' ')
    if action=='计划计算':
        artifact=json.loads(run['input_artifact'])
        return engine.create(run['project_id'],artifact['path'],value,run['mode'],engine.state.protocol(run['protocol_id']),
                             json.loads(run['source_metadata']),session_id=session_id)
    target=engine.get_run(value.strip())
    if target['session_id']!=session_id: raise ValueError('Calculation run belongs to another session')
    return engine.resume(target['run_id'],confirm=action=='确认计算')


def session_evidence_answer(db,session_id):
    if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='workflow_run'").fetchone():
        return {'status':'no_computational_run','message':'该会话尚未关联多后端计算计划。'}
    run=db.execute('SELECT * FROM workflow_run WHERE session_id=? ORDER BY created_at DESC LIMIT 1',(session_id,)).fetchone()
    if not run: return {'status':'no_computational_run'}
    ids=json.loads(run['candidate_ids']);rows=[]
    for cid in ids:
        evidence=list(db.execute('SELECT evidence_type,raw_value FROM evidence WHERE project_id=? AND compound_id=? AND protocol_id=?',
                                         (run['project_id'],cid,run['protocol_id'])))
        fields={r[0] for r in evidence}
        has_admet=any(r[0]=='admet_features' and isinstance(json.loads(r[1]),dict) and 'admet_endpoint_sum' in json.loads(r[1]) for r in evidence)
        checks={'Docking':bool(fields&{'vina_affinity','glide_score','glide_xp_score','docking_score'}),
                'MMGBSA':bool(fields&{'prime_mmgbsa','mmgbsa_score'}),'ADMET':has_admet}
        missing=[k for k,v in checks.items() if not v]
        if 'vina_affinity' in fields and not fields&{'glide_score','glide_xp_score','docking_score'}: missing.append('冻结Glide模型的后端兼容性')
        rows.append({'compound_id':cid,**checks,'missing':missing,'next_step':missing[0] if missing else '进入Decision Agent输入QC'})
    return {'run_id':run['run_id'],'project_id':run['project_id'],'source':'shared_Evidence_Registry',
            'candidates':rows,'reason':'缺失关键计算证据或后端不兼容时final_score=unknown；实验数据不推测。',
            'execution_command':'python src/run_computational_workflow.py resume '+run['run_id']+' --confirm',
            'note':'该回复只查询状态，不自动批准或执行计算。'}


class WorkflowService:
    ROUTES=['/projects','/projects/{id}/candidates','/projects/{id}/jobs','/projects/{id}/evidence',
            '/projects/{id}/decisions','/projects/{id}/experiments','/projects/{id}/chat','/projects/{id}/runs']
    def __init__(self,project_root,runtime_root=None,capabilities=None):
        self.engine=MultiBackendWorkspace(project_root,runtime_root,capabilities)

    def request(self,method,path,payload=None):
        payload=payload or {};parts=path.strip('/').split('/');state=self.engine.state
        if parts==['projects']:
            if method=='POST': return {'project_id':state.project_id(payload['project_id'])}
            if method=='GET':
                with state.connect() as db: return [dict(r) for r in db.execute('SELECT * FROM execution_project')]
        if len(parts)!=3 or parts[0]!='projects': raise ValueError('Unknown API path')
        project,resource=parts[1:]
        if method=='POST' and resource=='runs':
            if 'resume' in payload:
                run=self.engine.get_run(payload['resume'])
                if run['project_id']!=project: raise ValueError('Project/run mismatch')
                return self.engine.resume(run['run_id'],payload.get('confirm',False),payload.get('retry_failed',False))
            selected=Path(payload['input_path']).resolve()
            if not selected.is_relative_to(state.project.parent): raise ValueError('Input outside explicitly allowed research workspace')
            return self.engine.create(project,selected,payload['intent'],payload.get('mode','decision_only'),payload.get('protocol'),payload.get('source_metadata'))
        if method=='POST' and resource=='chat':
            with state.connect() as db:
                linked=db.execute('SELECT 1 FROM workflow_run WHERE project_id=? AND session_id=?',(project,payload['session_id'])).fetchone()
            if not linked: raise ValueError('Session/project mismatch')
            return self.engine.chat_workspace.chat(payload['session_id'],payload['message'])
        if method=='POST' and resource=='experiments':
            return self.link_reviewed_experiment(project,payload['decision_run_id'],payload['experiment_run_id'])
        if method!='GET': raise ValueError('Unsupported operation')
        if resource=='evidence': return enriched(state,project)
        if resource=='experiments':
            from experimental_feedback import FeedbackStore
            with state.connect() as db:
                links=[dict(r) for r in db.execute('SELECT * FROM workflow_feedback_link WHERE project_id=?',(project,))]
                linked_experiments=[dict(r) for r in db.execute('SELECT * FROM workflow_experiment_link WHERE project_id=?',(project,))]
            return {'reviewed_feedback':FeedbackStore(state.project).status(),'links':links,'linked_experiments':linked_experiments,'training':False}
        table={'candidates':'candidate','jobs':'calculation_job','decisions':'decision_run','runs':'workflow_run'}.get(resource)
        if not table: raise ValueError('Unknown resource')
        with state.connect() as db: return [dict(r) for r in db.execute('SELECT * FROM '+table+' WHERE project_id=?',(project,))]

    def link_reviewed_experiment(self,project,decision_id,experiment_id):
        from experimental_feedback import FeedbackStore
        state=self.engine.state;store=FeedbackStore(state.project);snapshot=store.status()['latest_snapshot']
        if not snapshot: raise ValueError('No human-reviewed experimental snapshot; keep feedback empty')
        with state.connect() as db:
            link=db.execute('SELECT * FROM workflow_feedback_link WHERE project_id=? AND decision_run_id=?',(project,decision_id)).fetchone()
            if not link: raise ValueError('Decision/project mismatch')
            ids=[r[0] for r in db.execute('SELECT candidate_id FROM candidate WHERE project_id=?',(project,))]
        records=[r['record_id'] for cid in ids for r in store.evidence_for(cid) if r.get('batch_id')==experiment_id]
        if not records: raise ValueError('No reviewed records for this project/experimental batch')
        with state.connect() as db:
            db.execute('INSERT OR IGNORE INTO workflow_experiment_link VALUES (?,?,?,?,?,?,?)',
                (link['calculation_run_id'],decision_id,link['candidate_panel_id'],experiment_id,project,json.dumps(records),snapshot['snapshot_id']))
        return {'status':'reviewed_feedback_linked','records':len(records),'training':False,
                'prospective_status':'requires_separate_chronology_check_not_implied_by_link'}
