"""Historical import and Decision Agent view of the ONE evidence registry.

Never imports a literature activity value as an internal candidate measurement.
The Phase 10 CSV input is a derived, hash-pinned view, not an independent database.
"""
from __future__ import annotations
import csv
import json
import math
from pathlib import Path
import pandas as pd
from .state import encode, digest, now, file_hash, write_json


def clean_numeric(values):
    return {k:float(v) for k,v in values.items() if pd.notna(v) and math.isfinite(float(v))}


def build_library(project, library, destination):
    project=Path(project)
    sources=[]
    if library=='internal':
        source=project/'data/model_v3/training_table.csv'
        table=pd.read_csv(source)
        aliases=pd.read_csv(project/'data/dataset_v0.2/samples.csv').set_index('compound_id')['historical_alias'].to_dict()
        rows=[]
        for row in table.to_dict('records'):
            result={'compound_id':row['compound_id'],'historical_alias':aliases.get(row['compound_id'],''),
                    'SMILES':row['canonical_smiles'],'docking_score':row['glide_docking_score'],'mmgbsa_score':row['label_score']}
            for output,prefix in [('docking_features','glide_'),('quickprop_features','quickprop_'),('admet_features','admet_')]:
                result[output]=encode(clean_numeric({k:v for k,v in row.items() if k.startswith(prefix) and k!='glide_docking_score'}))
            rows.append(result)
        sources=[source,project/'data/dataset_v0.2/samples.csv',project/'data/model_v3/binding_feature_table.csv']
        kind='historical_internal_17_replay_not_new_validation'
    elif library=='htvs':
        source=project/'data/htvs_structures_v0_1.csv'
        table=pd.read_csv(source,dtype={'compound_code':str,'variant':str,'pose_index':str})
        docking=pd.read_csv(project/'data/docking_features_v0_2.csv',dtype={'compound_code':str,'variant':str,'pose_index':str})
        join_keys=['canonical_id','variant','pose_index','source_file']
        if docking.duplicated(join_keys).any():
            raise ValueError('Ambiguous pose join; refuse to choose a QuickProp row')
        properties=docking.set_index(join_keys)
        rows=[]
        for row in table.to_dict('records'):
            if row['extraction_status']!='complete' or row['structure_join_status']!='matched':
                continue
            result={'compound_id':row['canonical_id'],'historical_alias':row['compound_code'],
                    'SMILES':row['canonical_smiles'],'docking_score':row['glide_docking_score'],'mmgbsa_score':'unknown'}
            key=tuple(row[k] for k in join_keys)
            matching=properties.loc[key].to_dict() if key in properties.index else {}
            for output,prefix in [('docking_features','glide_'),('quickprop_features','quickprop_')]:
                result[output]=encode(clean_numeric({k:v for k,v in matching.items() if k.startswith(prefix) and k!='glide_docking_score'}))
            result['admet_features']='{}'
            rows.append(result)
        sources=[source,project/'data/docking_features_v0_2.csv']
        kind='historical_HTVS_best_pose_only_not_SP_or_XP'
    else:
        raise ValueError('Unsupported library')
    frame=pd.DataFrame(rows)
    frame.to_csv(destination,index=False)
    lineage={'library':library,'source_kind':kind,'source_files':[{'path':str(p.relative_to(project)),'sha256':file_hash(p)} for p in sources],
             'candidate_count':len(frame),'input_sha256':file_hash(destination),
             'note':'Computed historical values are preserved, not regenerated or experimental measurements.'}
    write_json(Path(destination).with_suffix('.lineage.json'),lineage)
    return lineage


def import_library(state,project_id,batch_id,input_path,protocol_id,lineage):
    table=pd.read_csv(input_path,dtype=str,keep_default_na=False)
    required={'compound_id','SMILES'}
    if not required.issubset(table.columns) or table['compound_id'].duplicated().any():
        raise ValueError('Input requires unique compound_id and SMILES')
    archive=state.artifact(input_path)
    for row in table.to_dict('records'):
        state.candidate(project_id,row['compound_id'],row['SMILES'],row.get('historical_alias',''))
    job=state.job(batch_id,project_id,'__library__','historical_import',protocol_id,[archive],
                  {'action':'import_existing_computational_evidence','source_sha256':archive['artifact_hash'],'lineage':lineage})
    with state.connect() as db:
        db.execute("UPDATE calculation_job SET status='completed',completed_at=?,return_code=0,output_artifacts=? WHERE job_id=?",
                   (now(),encode([archive]),job))
    rows=[]
    stage='HTVS' if lineage.get('library')=='htvs' else 'historical_docking_mode_unknown'
    for row in table.to_dict('records'):
        for key in ['docking_score','mmgbsa_score','docking_features','quickprop_features','admet_features']:
            value=row.get(key,'')
            if value.strip().lower() in {'','unknown','nan','none','{}'}:
                continue
            if key.endswith('_features'):
                value=json.loads(value)
                if not isinstance(value,dict):
                    raise ValueError('Features must be an object')
                value=clean_numeric(value)
            else:
                value=float(value)
            rows.append({'compound_id':row['compound_id'],'evidence_type':key,'raw_value':value,
                         'unit':{'docking_score':'Glide_score','mmgbsa_score':'kcal/mol'}.get(key,'mixed_bundle'),
                         'provenance':{'stage':stage,'historical_protocol_completeness':'incomplete','lineage':lineage}})
    state.register_many(project_id,job,archive['artifact_hash'],rows,'historical_result')
    if lineage.get('library')=='internal':
        import_disagreement(state,project_id,batch_id,table['compound_id'].tolist())
    return table['compound_id'].tolist(),job


def import_disagreement(state,project_id,batch_id,candidate_ids):
    """Frozen OOF rank disagreement is an observed model comparison, not an assay."""
    first=state.project/'results/model_v3/model_v3_oof_predictions.csv'
    second=state.project/'results/model_v4_alpha/internal_oof_predictions.csv'
    if not first.exists() or not second.exists():
        return
    a=pd.read_csv(first)[['compound_id','oof_prediction']]
    b=pd.read_csv(second)[['compound_id','model_v4_alpha_oof_prediction']]
    merged=a.merge(b,on='compound_id',validate='one_to_one')
    merged=merged.loc[merged.compound_id.isin(candidate_ids)].copy()
    if merged.empty:
        return
    merged['disagreement']=(merged.oof_prediction.rank(method='average')-merged.model_v4_alpha_oof_prediction.rank(method='average')).abs()/max(len(merged)-1,1)
    artifacts=[state.artifact(first),state.artifact(second)]
    protocol={'protocol_id':'frozen_oof_rank_disagreement_'+digest([x['artifact_hash'] for x in artifacts])[:12],
              'method':'absolute_v3_v4alpha_rank_difference_divided_by_n_minus_1','training':False}
    state.freeze_protocol(protocol)
    job=state.job(batch_id,project_id,'__library__','historical_model_comparison',protocol['protocol_id'],artifacts,
                  {'action':'read_frozen_OOF_rank_disagreement','n':len(merged)})
    with state.connect() as db:
        db.execute("UPDATE calculation_job SET status='completed',completed_at=?,return_code=0,output_artifacts=? WHERE job_id=?",
                   (now(),encode(artifacts),job))
    state.register_many(project_id,job,artifacts[0]['artifact_hash'],
                        [{'compound_id':r.compound_id,'evidence_type':'model_rank_disagreement','raw_value':r.disagreement,
                          'unit':'normalized_absolute_rank_difference'} for r in merged.itertuples()],
                        'frozen_model_output',{'source_artifact_hashes':[x['artifact_hash'] for x in artifacts],
                                               'interpretation':'model disagreement, not validated prediction uncertainty'})


def registry_view(state,project_id,candidate_ids,destination,binding_protocol_id=None):
    evidence=state.evidence_rows(project_id)
    selected=set(candidate_ids)
    with state.connect() as db:
        candidates={r['candidate_id']:dict(r) for r in db.execute('SELECT * FROM candidate WHERE project_id=?',(project_id,))}
    rows={c:{'compound_id':c,'SMILES':candidates[c]['smiles'],'historical_alias':candidates[c]['alias'],
             'docking_score':'unknown','mmgbsa_score':'unknown','docking_features':{},'quickprop_features':{},'admet_features':{}}
          for c in candidate_ids}
    ids=[]
    qc_seen=set()
    for item in evidence:
        compound=item['compound_id']
        if compound not in selected:
            continue
        field=item['evidence_type']
        if field=='structure_qc':
            state.verify_artifact(item['artifact_hash'])
            qc=json.loads(item['raw_value'])
            rows[compound]['SMILES']=qc.get('canonical_smiles','unknown') if qc.get('structure_status')=='valid' else 'unknown'
            qc_seen.add(compound)
            ids.append(item['evidence_id'])
            continue
        if field not in {'docking_score','mmgbsa_score','docking_features','quickprop_features','admet_features'} and not field.startswith(('glide_','quickprop_')):
            continue
        if binding_protocol_id and (field in {'docking_score','mmgbsa_score','docking_features'} or field.startswith('glide_')) and item['protocol_id']!=binding_protocol_id:
            continue
        state.verify_artifact(item['artifact_hash'])
        value=json.loads(item['raw_value'])
        if field.startswith('glide_'):
            rows[compound]['docking_features'][field]=value
        elif field.startswith('quickprop_') and field!='quickprop_features':
            rows[compound]['quickprop_features'][field]=value
        elif field.endswith('_features'):
            rows[compound][field].update(value)
        else:
            rows[compound][field]=value
        ids.append(item['evidence_id'])
    for row in rows.values():
        if row['compound_id'] not in qc_seen:
            row['SMILES']='unknown'  # no completed structure QC, no hidden bypass
        for key in ['docking_features','quickprop_features','admet_features']:
            row[key]=encode(row[key])
    pd.DataFrame(rows.values()).to_csv(destination,index=False)
    write_json(Path(destination).with_suffix('.registry.json'),{'project_id':project_id,'evidence_ids':ids,
                'registry':str(state.db_path),'view_sha256':file_hash(destination),'binding_protocol_id':binding_protocol_id,
                'policy':'binding scores require the selected protocol; chemical properties retain provenance; experimental values excluded'})
    return ids


def planner_candidates(state,project_id,candidate_ids,compatible_protocols=None):
    from rdkit import Chem
    from rdkit.Chem.Scaffolds import MurckoScaffold
    with state.connect() as db:
        candidates={r['candidate_id']:dict(r) for r in db.execute('SELECT * FROM candidate WHERE project_id=?',(project_id,))}
    evidence=state.evidence_rows(project_id)
    features={c:{} for c in candidate_ids}
    stages={c:set() for c in candidate_ids}
    for item in evidence:
        compound=item['compound_id']
        if compound not in features:
            continue
        field=item['evidence_type']
        value=json.loads(item['raw_value'])
        features[compound][field]=value
        provenance=json.loads(item['provenance'])
        if field=='structure_qc' and value.get('structure_status')=='valid':
            stages[compound].add('structure_qc')
        compatible=compatible_protocols is None or item['protocol_id'] in compatible_protocols
        if compatible and field=='docking_score' and provenance.get('stage') in {'HTVS','SP','XP'}:
            stages[compound].add(provenance['stage'])
        if compatible and field=='mmgbsa_score':
            stages[compound].add('MMGBSA')
    ranked=sorted(candidate_ids,key=lambda c:(features[c].get('docking_score',float('inf')),c))
    ranks={c:i+1 for i,c in enumerate(ranked) if 'docking_score' in features[c]}
    result=[]
    for compound in candidate_ids:
        mol=Chem.MolFromSmiles(candidates[compound]['smiles'])
        fields=features[compound]
        metrics=fields.get('decision_metrics',{})
        spread=(metrics['rank_p95']-metrics['rank_p05'])/max(len(candidate_ids)-1,1) if {'rank_p05','rank_p95'}<=metrics.keys() else 'unknown'
        result.append({'compound_id':compound,'current_rank':ranks.get(compound,'unknown'),
                       'rank_source':'historical_or_executed_docking_not_final_activity',
                       'scaffold':MurckoScaffold.MurckoScaffoldSmiles(mol=mol,includeChirality=True),
                       'evidence_completeness':sum(k in fields for k in ['docking_score','mmgbsa_score','admet_features'])/3,
                       'uncertainty':spread,'model_disagreement':fields.get('model_rank_disagreement','unknown'),'relative_cost':50})
        if 'rank' in metrics:
            result[-1]['current_rank']=metrics['rank']
            result[-1]['rank_source']='frozen_decision_robust_rank'
    return result,stages


def run_decision(state,project_id,batch_id,session_id,candidate_ids,protocol_id,profile,output,budget):
    from navigator_pipeline import NavigatorPipeline, json_safe
    from experimental_feedback import FeedbackStore
    output=Path(output)
    output.mkdir(parents=True,exist_ok=False)
    view=output/'registry_candidate_view.csv'
    evidence_ids=registry_view(state,project_id,candidate_ids,view,protocol_id)
    trace=NavigatorPipeline(state.project).run(view,profile=profile,output_dir=output,
                                               report_path=output/'candidate_explanation.md')
    trace=json_safe(trace)  # empty score distributions are null, never fabricated zero
    ranking=output/'final_navigation_report.csv'
    table=pd.read_csv(ranking)
    panel=table.loc[pd.to_numeric(table['final_score'],errors='coerce').notna()].sort_values('rank').head(budget)
    panel.to_csv(output/'experimental_panel.csv',index=False)
    run_id='decision_'+batch_id.removeprefix('batch_')
    model_version='frozen_v3_or_explicit_v2a_fallback_Phase11_decision'
    with state.connect() as db:
        db.execute('INSERT INTO decision_run VALUES (?,?,?,?,?,?,?,?,?,?)',
                   (run_id,project_id,batch_id,session_id,protocol_id,model_version,encode(evidence_ids),str(ranking),file_hash(ranking),now()))
        if session_id:
            db.execute('UPDATE sessions SET latest_run=? WHERE id=?',(str(output),session_id))
    artifact=state.artifact(ranking)
    inference_protocol={'protocol_id':'frozen_inference_'+digest(trace.get('preserved_model_hashes',{}))[:12],
                        'model_version':model_version,'training':False,'models':trace.get('preserved_model_hashes',{}),'profile':profile}
    # Profile is part of inference protocol identity as decision outputs are profile-dependent.
    inference_protocol['protocol_id']='frozen_inference_'+digest(inference_protocol)[:12]
    state.freeze_protocol(inference_protocol)
    job=state.job(batch_id,project_id,'__library__','frozen_model',inference_protocol['protocol_id'],[state.artifact(view)],
                  {'action':'frozen_inference','decision_run_id':run_id,'input_sha256':file_hash(view)})
    with state.connect() as db:
        db.execute("UPDATE calculation_job SET status='completed',completed_at=?,return_code=0,output_artifacts=? WHERE job_id=?",
                   (now(),encode([artifact]),job))
    numeric=[]
    for row in table.to_dict('records'):
        for field in ['model_score','binding_score','ATP_score','antibacterial_score','drug_score','final_score']:
            if field in row and pd.notna(row[field]):
                numeric.append({'compound_id':row['compound_id'],'evidence_type':field,'raw_value':float(row[field]),
                                'unit':'computational_score_not_probability','provenance':{'decision_run_id':run_id,'profile':profile}})
        values={k:float(row[k]) for k in ['rank','rank_p05','rank_p95','evidence_coverage'] if k in row and pd.notna(row[k])}
        if values:
            numeric.append({'compound_id':row['compound_id'],'evidence_type':'decision_metrics','raw_value':values,
                            'unit':'rank_and_coverage','provenance':{'decision_run_id':run_id,'profile':profile}})
    state.register_many(project_id,job,artifact['artifact_hash'],numeric,'frozen_model_output')
    feedback=sync_feedback(state,project_id,candidate_ids,run_id,model_version)
    return {'decision_run_id':run_id,'candidate_count':len(table),'complete_decisions':int(pd.to_numeric(table['final_score'],errors='coerce').notna().sum()),
            'experimental_panel_count':len(panel),'requested_panel_budget':budget,'feedback':feedback,
            'ranking_sha256':file_hash(ranking),'model_version':model_version,'trace':trace}


def sync_feedback(state,project_id,candidate_ids,decision_run_id,model_version):
    """Index reviewed Phase11 records; do not rewrite its store, QC, or labels."""
    from experimental_feedback import FeedbackStore
    feedback=FeedbackStore(state.project)
    status=feedback.status()
    latest=status.get('latest_snapshot')
    count=0
    if latest:
        with state.connect() as db:
            for compound in candidate_ids:
                for row in feedback.evidence_for(compound):
                    db.execute('INSERT OR IGNORE INTO feedback_link VALUES (?,?,?,?,?,?,?,?)',
                               (project_id,compound,row['assay_protocol_id'],decision_run_id,model_version,
                                row['record_id'],latest['snapshot_id'],encode(row)))
                    count+=1
    return {'status':'empty' if count==0 else 'reviewed_records_indexed','records':count,
            'prospective_metrics':'not_available','training_performed':False,
            'note':'A link does not establish prospective chronology; actual independent assay dates and frozen pre-experiment ranking are still required.'}
