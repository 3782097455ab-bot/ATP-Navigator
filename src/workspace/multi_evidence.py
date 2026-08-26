"""Protocol/cohort-selective evidence views; Vina is never renamed Glide."""
import json
from pathlib import Path
import pandas as pd
from .state import encode,now,file_hash,write_json,digest


def enriched(state,project):
    with state.connect() as db:
        jobs={r['job_id']:dict(r) for r in db.execute('SELECT * FROM calculation_job WHERE project_id=?',(project,))}
    rows=[]
    for r in state.evidence_rows(project):
        p=json.loads(r['provenance']);j=jobs[r['source_job_id']]
        rows.append({**r,'tool_id':p.get('tool_id',j['tool_id']),'backend':p.get('backend','historical_unknown'),
                     'run_id':j['batch_id'],'job_id':j['job_id'],'value':json.loads(r['raw_value'])})
    return rows


def completeness(state,project,ids,protocol_id=None):
    records=enriched(state,project);result=[]
    for cid in ids:
        rows=[r for r in records if r['compound_id']==cid and (protocol_id is None or r['protocol_id']==protocol_id or r['evidence_type']=='structure_qc')]
        fields={r['evidence_type'] for r in rows}
        docking=bool(fields&{'vina_affinity','glide_score','glide_xp_score','docking_score'})
        mmgbsa=bool(fields&{'prime_mmgbsa','mmgbsa_score'})
        admet=any(r['evidence_type']=='admet_features' and isinstance(r['value'],dict) and 'admet_endpoint_sum' in r['value'] for r in rows)
        missing=[]
        if not docking: missing.append('docking')
        if not mmgbsa: missing.append('MMGBSA')
        if not admet: missing.append('ADMET_endpoint_evidence')
        if 'vina_affinity' in fields and not fields&{'glide_score','docking_score'}: missing.append('frozen_Glide_model_backend_compatibility')
        result.append({'compound_id':cid,'docking':docking,'MMGBSA':mmgbsa,'ADMET':admet,
                       'missing':missing,'eligible_for_completeness_review':not missing,
                       'next_step':missing[0] if missing else 'Decision Agent input QC',
                       'experimental_status':'unknown'})
    return result


def cohort_rankings(records):
    values=[r for r in records if r['evidence_type'] in {'vina_affinity','glide_score','glide_xp_score','docking_score','prime_mmgbsa','mmgbsa_score'}]
    if not values: return []
    frame=pd.DataFrame(values)
    frame['cohort']=frame.apply(lambda r:encode([r.tool_id,r.tool_version,r.protocol_id,r.run_id,r.evidence_type]),axis=1)
    output=[]
    for key,group in frame.groupby('cohort'):
        if group.compound_id.duplicated().any(): raise ValueError('Ambiguous duplicate score in a cohort')
        ranks=pd.to_numeric(group.value).rank(method='min',ascending=True)
        for (_,r),rank in zip(group.iterrows(),ranks):
            output.append({'compound_id':r.compound_id,'evidence_type':r.evidence_type,'raw_value':r.value,
                           'tool_id':r.tool_id,'tool_version':r.tool_version,'protocol_id':r.protocol_id,'source_batch':r.run_id,
                           'cohort_rank':int(rank),'cohort':key,'comparison_scope':'within_cohort_only',
                           'cross_protocol':frame.cohort.nunique()>1})
    return output


def decision_view(state,run,destination):
    ids=json.loads(run['candidate_ids']);records=enriched(state,run['project_id']);protocol=run['protocol_id']
    with state.connect() as db:
        candidates={r['candidate_id']:dict(r) for r in db.execute('SELECT * FROM candidate WHERE project_id=?',(run['project_id'],))}
    mapping={'docking_score':'docking_score','glide_score':'docking_score','glide_xp_score':'docking_score','mmgbsa_score':'mmgbsa_score',
             'prime_mmgbsa':'mmgbsa_score','docking_features':'docking_features','quickprop_features':'quickprop_features',
             'admet_features':'admet_features'}
    selected=[r for r in records if r['compound_id'] in ids and r['protocol_id']==protocol and r['evidence_type'] in mapping]
    if any(r['evidence_type']=='glide_xp_score' for r in selected):
        selected=[r for r in selected if r['evidence_type'] not in {'glide_score','docking_score'}]
    # A field from multiple source tool/version/protocol/batch cohorts is not
    # silently pooled. Researchers must select an explicit cohort in a new run.
    groups={}
    for r in selected:
        key=mapping[r['evidence_type']]
        groups.setdefault(key,set()).add((r['tool_id'],r['tool_version'],r['protocol_id'],r['run_id'],r['evidence_type']))
    conflicts=[k for k,v in groups.items() if len(v)>1]
    view=[];evidence_ids=[]
    for cid in ids:
        row={'compound_id':cid,'historical_alias':candidates[cid]['alias'],'SMILES':candidates[cid]['smiles'],
             'docking_score':'unknown','mmgbsa_score':'unknown','docking_features':'{}','quickprop_features':'{}','admet_features':'{}'}
        qc=[r for r in records if r['compound_id']==cid and r['evidence_type']=='structure_qc']
        if not any(r['value'].get('structure_status')=='valid' for r in qc): row['SMILES']='unknown'
        for r in selected:
            key=mapping[r['evidence_type']]
            if r['compound_id']!=cid or key in conflicts: continue
            state.verify_artifact(r['artifact_hash']);value=r['value']
            row[key]=encode(value) if isinstance(value,dict) else value;evidence_ids.append(r['evidence_id'])
        view.append(row)
    pd.DataFrame(view).to_csv(destination,index=False)
    return evidence_ids,conflicts


def decide(state,run,folder):
    from .evidence_bridge import sync_feedback
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=False)
    ids=json.loads(run['candidate_ids']);intent=json.loads(run['intent']);protocol=state.protocol(run['protocol_id'])
    evidence_ids,conflicts=decision_view(state,run,folder/'candidate_view.csv')
    records=[r for r in enriched(state,run['project_id']) if r['compound_id'] in ids and r['protocol_id']==run['protocol_id']]
    pd.DataFrame(cohort_rankings(records)).to_csv(folder/'backend_cohort_rankings.csv',index=False)
    missing=completeness(state,run['project_id'],ids,run['protocol_id'])
    if protocol.get('target_reference') not in {'7P3W',None} or protocol.get('scope')=='software_smoke_only':
        table=pd.DataFrame([{'compound_id':c,'final_score':'unknown','rank':'unknown','reason':'software_smoke_only_not_ATP_candidate_selection'} for c in ids])
        table.to_csv(folder/'final_navigation_report.csv',index=False)
    else:
        from navigator_pipeline import NavigatorPipeline
        NavigatorPipeline(state.project).run(folder/'candidate_view.csv',profile=intent['research_profile'],
                                             output_dir=folder,report_path=folder/'candidate_explanation.md')
        table=pd.read_csv(folder/'final_navigation_report.csv')
    panel=table.loc[pd.to_numeric(table.final_score,errors='coerce').notna()].head(intent['final_experiment_budget'])
    panel.to_csv(folder/'experimental_panel.csv',index=False)
    token='decision_multi_'+digest([run['run_id'],str(folder)])[:20]
    panel_id='panel_'+digest([token,file_hash(folder/'experimental_panel.csv')])[:20]
    with state.connect() as db:
        db.execute('INSERT INTO decision_run VALUES (?,?,?,?,?,?,?,?,?,?)',(token,run['project_id'],run['run_id'],run['session_id'],
                   run['protocol_id'],'frozen_v3_no_training',encode(evidence_ids),str(folder/'final_navigation_report.csv'),file_hash(folder/'final_navigation_report.csv'),now()))
        db.execute('INSERT INTO workflow_feedback_link VALUES (?,?,?,?,?)',(run['run_id'],token,panel_id,None,run['project_id']))
        db.execute('UPDATE sessions SET latest_run=? WHERE id=?',(str(folder),run['session_id']))
    feedback=sync_feedback(state,run['project_id'],ids,token,'frozen_v3_no_training')
    inference={'protocol_id':'frozen_multi_inference_'+digest([run['protocol_id'],intent['research_profile']])[:16],
               'input_protocol':run['protocol_id'],'profile':intent['research_profile'],'model':'frozen_v3','training':False}
    state.freeze_protocol(inference)
    artifact=state.artifact(folder/'final_navigation_report.csv')
    job=state.job(run['run_id'],run['project_id'],'__library__','frozen_model',inference['protocol_id'],
                  [state.artifact(folder/'candidate_view.csv')],{'action':'read_frozen_inference_result','decision_run_id':token})
    with state.connect() as db:
        db.execute("UPDATE calculation_job SET status='completed',completed_at=?,return_code=0,output_artifacts=? WHERE job_id=?",(now(),encode([artifact]),job))
    numeric=[]
    for row in table.to_dict('records'):
        for field in ['model_score','binding_score','ATP_score','antibacterial_score','drug_score','final_score']:
            value=pd.to_numeric(row.get(field),errors='coerce')
            if pd.notna(value): numeric.append({'compound_id':row['compound_id'],'evidence_type':field,'raw_value':float(value),
                                               'unit':'computational_score_not_probability'})
    state.register_many(run['project_id'],job,artifact['artifact_hash'],numeric,'frozen_model_output',
                         {'tool_id':'frozen_model','backend':'frozen_model','decision_run_id':token,'input_protocol_id':run['protocol_id']})
    result={'decision_run_id':token,'candidate_panel_id':panel_id,'calculation_run_id':run['run_id'],
            'panel_size':len(panel),'candidate_count':len(ids),'missing_evidence':missing,'cohort_conflicts':conflicts,
            'feedback':feedback,'training':False,'path':str(folder),'scoring_logic':'unchanged; unavailable components stay unknown'}
    write_json(folder/'decision_summary.json',result)
    return result
