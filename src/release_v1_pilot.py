"""Conditional data-release pilot. No production model or decision score changes.

External IC50 tasks are fit separately by assay; the internal comparison uses
only its original MMGBSA target and original leave-scaffold-out folds. No MIC,
ETC, cytotoxicity, decision score, or fabricated experiment becomes a label.
"""
from __future__ import annotations
import argparse
import json
import math
from pathlib import Path
import joblib
import numpy as np
import pandas as pd
from rdkit import Chem,DataStructs
from rdkit.Chem import rdFingerprintGenerator
from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import LeaveOneGroupOut
from model_v3_pipeline import descriptor_row
from model_v2_pipeline import make_regressor,ranking_metrics
from release_v1_audit import identity_key
from workspace.state import file_hash,write_json
from navigator_pipeline import json_safe

PARAMS={'n_estimators':128,'max_depth':4,'min_samples_leaf':2,'random_state':42,'n_jobs':1}


def fingerprints(smiles):
    generator=rdFingerprintGenerator.GetMorganGenerator(radius=2,fpSize=1024,includeChirality=True)
    return [generator.GetFingerprint(Chem.MolFromSmiles(s)) for s in smiles]


def features(smiles):
    fps=fingerprints(smiles)
    rows=[]
    for smi,fp in zip(smiles,fps):
        row={f'morgan1024_{i:04d}':int(bit) for i,bit in enumerate(fp.ToBitString())}
        row.update(descriptor_row(Chem.MolFromSmiles(smi)))
        rows.append(row)
    return pd.DataFrame(rows),fps


def measure(y,pred,k=5,higher=False):
    # Legacy metric helper uses lower-is-better energy semantics.
    result=ranking_metrics(-np.asarray(y) if higher else y,-np.asarray(pred) if higher else pred,k=k)
    return json_safe(result)


def pilot(project,release,experiment_id='release_v1_shadow_001',knowledge_mode='add'):
    project,release=Path(project).resolve(),Path(release).resolve()
    output=project/'results'/experiment_id
    modeldir=project/'models/experiments'/experiment_id
    output.mkdir(parents=True,exist_ok=False)
    modeldir.mkdir(parents=True,exist_ok=False)
    frozen_before={str(p.relative_to(project)):file_hash(p) for p in (project/'models').rglob('*') if p.is_file() and not p.is_relative_to(modeldir)}
    data=pd.read_csv(release/'pilot_eligible_measurements.csv')
    internal=pd.read_csv(project/'data/model_v3/training_table.csv')
    original_oof=pd.read_csv(project/'results/model_v3/model_v3_oof_predictions.csv').set_index('compound_id').loc[internal.compound_id]
    internal_ids=set(internal.canonical_smiles.map(identity_key))
    overlap=data.parent_identity.isin(internal_ids)
    data.loc[overlap].to_csv(output/'external_internal_overlap_excluded.csv',index=False)
    usable=data.loc[~overlap].copy()
    internal_x,internal_fp=features(internal.canonical_smiles)
    augmented=pd.DataFrame(index=internal.index)
    taskmetrics,taskrows,models,scale=[],[],{},[]
    for assay,group in usable.groupby('assay_id',sort=True):
        group=group.reset_index(drop=True)
        row={'assay_id':assay,'organism':group.organism.iloc[0],'doi':group.doi.iloc[0],
             'n':len(group),'scaffolds':group.scaffold.nunique(),'endpoint':'IC50_ATP_synthesis',
             'label':'recomputed_p_activity_within_assay','cross_DOI_validation':'not_available_single_DOI_per_assay'}
        if len(group)<5 or group.scaffold.nunique()<2:
            scale.append({**row,'status':'reference_only_small_data_no_fit'})
            continue
        x,fps=features(group.canonical_smiles)
        y=group.recomputed_p_activity.to_numpy(float)
        prediction=np.full(len(group),np.nan)
        mean_prediction=np.full(len(group),np.nan)
        for train,test in LeaveOneGroupOut().split(x,y,group.scaffold):
            if len(train)<4:
                continue
            assert not set(group.scaffold.iloc[train])&set(group.scaffold.iloc[test])
            model=RandomForestRegressor(**PARAMS).fit(x.iloc[train],y[train])
            prediction[test]=model.predict(x.iloc[test])
            mean_prediction[test]=y[train].mean()
        valid=np.isfinite(prediction)
        scale.append({**row,'status':'conditional_pilot_fit','scaffold_OOF_covered':int(valid.sum())})
        if valid.sum()>=3:
            for name,values in [('within_assay_training_mean',mean_prediction),('RF_structure',prediction)]:
                taskmetrics.append({**row,'model':name,'evaluated_n':int(valid.sum()),'total_n':len(group),
                                    **measure(y[valid],values[valid],min(5,int(valid.sum())),higher=True)})
        for i,r in group.iterrows():
            taskrows.append({'measurement_id':r.measurement_id,'compound_key':r.compound_key,'assay_id':assay,
                             'scaffold':r.scaffold,'observed_p_activity':y[i],'oof_prediction':prediction[i],
                             'mean_baseline':mean_prediction[i],'status':'evaluated' if valid[i] else 'fold_train_too_small'})
        final=RandomForestRegressor(**PARAMS).fit(x,y)
        internal_predictions=final.predict(internal_x[x.columns])
        nearest=[max(DataStructs.BulkTanimotoSimilarity(fp,fps)) for fp in internal_fp]
        augmented['release_prior_'+assay]=internal_predictions
        augmented['release_similarity_'+assay]=nearest
        bundle={'model':final,'feature_columns':x.columns.tolist(),'assay_id':assay,'doi':group.doi.iloc[0],
                'organism':group.organism.iloc[0],'label':'p_activity_ATP_IC50_assay_specific',
                'measurement_ids':group.measurement_id.tolist(),'parameters':PARAMS,
                'source_QC':'conditional pilot; identity reconstruction not independently redrawn in this run',
                'internal_overlap_removed':True,'not_production':True}
        joblib.dump(bundle,modeldir/(assay+'.joblib'))
        models[assay]=bundle
    pd.DataFrame(taskmetrics).to_csv(output/'external_task_metrics.csv',index=False)
    pd.DataFrame(taskrows).to_csv(output/'external_oof_predictions.csv',index=False)
    pd.DataFrame(scale).to_csv(output/'external_task_training_scale.csv',index=False)
    if augmented.empty:
        raise ValueError('No eligible external tasks; audit results saved, no internal upgrade claimed')
    augmented.insert(0,'compound_id',internal.compound_id)
    augmented.to_csv(output/'new_external_features_internal.csv',index=False)
    # Fixed internal data, target, splits and hyperparameters: only added features differ.
    v3=joblib.load(project/'models/model_v3/model.joblib')
    base_x=internal[v3['feature_columns']]
    if knowledge_mode not in {'add','replace_atp'}:
        raise ValueError('Invalid knowledge strategy')
    removed=[c for c in base_x if c.startswith('prior_task_b_') or c in
             {'similarity_to_known_inhibitor','scaffold_seen_in_known_inhibitors'}] if knowledge_mode=='replace_atp' else []
    upgraded=pd.concat([base_x.drop(columns=removed),augmented.drop(columns='compound_id')],axis=1)
    y=internal.label_score.to_numpy(float)
    fold_ids=original_oof.fold_id.to_numpy()
    predictions={name:np.empty(len(y)) for name in ['v3_replayed_control','release_enhanced_shadow']}
    for fold in sorted(set(fold_ids)):
        test=np.flatnonzero(fold_ids==fold)
        train=np.flatnonzero(fold_ids!=fold)
        if set(internal.scaffold.iloc[test])&set(internal.scaffold.iloc[train]):
            raise ValueError('Internal scaffold leakage')
        for name,x in [('v3_replayed_control',base_x),('release_enhanced_shadow',upgraded)]:
            model=make_regressor().fit(x.iloc[train],y[train])
            predictions[name][test]=model.predict(x.iloc[test])
    difference=float(np.max(np.abs(predictions['v3_replayed_control']-original_oof.oof_prediction.to_numpy())))
    if difference>1e-8:
        raise ValueError(f'Control does not reproduce frozen v3 OOF ({difference}); no fair upgrade claim')
    comparisons=[]
    for name,pred in [('frozen_v3_saved_OOF',original_oof.oof_prediction.to_numpy()),*predictions.items()]:
        comparisons.append({'model':name,'n':len(y),'scaffold_groups':len(set(fold_ids)),
                            'label':'same_internal_static_MMGBSA_not_experimental_activity',**measure(y,pred)})
    pd.DataFrame(comparisons).to_csv(output/'internal_model_comparison.csv',index=False)
    oof=internal[['compound_id','canonical_smiles','scaffold']].copy()
    oof['fold_id']=fold_ids
    oof['observed_MMGBSA']=y
    for name,values in predictions.items():
        oof[name]=values
    oof.to_csv(output/'internal_oof_predictions.csv',index=False)
    shadow=make_regressor().fit(upgraded,y)
    importance=pd.DataFrame({'feature':upgraded.columns,'split_count':shadow.feature_importances_,
                             'gain':shadow.booster_.feature_importance(importance_type='gain'),
                             'feature_group':['new_release_knowledge' if c.startswith('release_') else 'preserved_v3_feature' for c in upgraded]})
    importance.sort_values('gain',ascending=False).to_csv(output/'feature_importance.csv',index=False)
    joblib.dump({'model':shadow,'feature_columns':upgraded.columns.tolist(),
                 'model_version':experiment_id,'purpose':'research_shadow_not_promoted',
                 'training_ids':internal.compound_id.tolist(),'label':'static_MMGBSA_not_activity'},modeldir/'internal_shadow.joblib')
    # Paired fold-cluster bootstrap: descriptive only, not a model-selection loop.
    rng=np.random.default_rng(20260826)
    differences=[]
    groups=sorted(set(fold_ids))
    for _ in range(2000):
        selected=rng.choice(groups,size=len(groups),replace=True)
        indices=np.concatenate([np.flatnonzero(fold_ids==f) for f in selected])
        base=np.sqrt(np.mean((y[indices]-predictions['v3_replayed_control'][indices])**2))
        new=np.sqrt(np.mean((y[indices]-predictions['release_enhanced_shadow'][indices])**2))
        differences.append(new-base)
    bootstrap={'metric':'RMSE(new)-RMSE(old), lower is better','fold_cluster_bootstrap_draws':2000,
               'percentile_95_interval':np.quantile(differences,[.025,.975]).tolist(),
               'interpretation':'exploratory on the same 17 candidates; not independent prospective validation'}
    write_json(output/'paired_fold_bootstrap.json',bootstrap)
    # Domain comparison uses both original ionic structures and standardized parents.
    old=pd.read_csv(project/'data/model_v3/chemical_space_analysis.csv')
    refs=data.drop_duplicates('canonical_smiles')
    ref_fps=fingerprints(refs.canonical_smiles)
    parent_refs=fingerprints(refs.canonical_smiles.map(identity_key))
    domain=[]
    for i,row in internal.iterrows():
        values=DataStructs.BulkTanimotoSimilarity(internal_fp[i],ref_fps)
        nearest=int(np.argmax(values))
        parent_fp=fingerprints([identity_key(row.canonical_smiles)])[0]
        old_row=old.loc[old.compound_id.eq(row.compound_id)].iloc[0]
        domain.append({'compound_id':row.compound_id,
                       'old_known_inhibitor_similarity':float(old_row.similarity_to_known_inhibitor),
                       'new_verified_claim_reference_similarity':float(values[nearest]),
                       'new_parent_standardized_similarity':max(DataStructs.BulkTanimotoSimilarity(parent_fp,parent_refs)),
                       'nearest_release_compound':refs.iloc[nearest].compound_name,
                       'nearest_source_doi':refs.iloc[nearest].doi,
                       'interpretation':'chemical proximity only; not confirmed activity or confidence probability'})
    pd.DataFrame(domain).to_csv(output/'chemical_space_change.csv',index=False)
    changed={p:hash_value for p,hash_value in frozen_before.items() if file_hash(project/p)!=hash_value}
    if changed:
        raise RuntimeError('Historical models changed')
    summary={'experiment_id':experiment_id,'release':str(release.relative_to(project)),
             'release_audit_sha256':file_hash(release/'independent_audit.json'),'external_rows':len(data),
             'external_internal_parent_overlap_excluded':int(overlap.sum()),'external_assay_models_fitted':len(models),
             'new_internal_feature_count':len(upgraded.columns)-len(base_x.columns),
             'new_release_features':len(augmented.columns)-1,'removed_legacy_features':removed,
             'knowledge_mode':knowledge_mode,'total_feature_count':len(upgraded.columns),
             'new_release_gain_fraction':float(importance.loc[importance.feature_group.eq('new_release_knowledge'),'gain'].sum()/max(importance.gain.sum(),1e-12)),
             'internal_samples':17,'original_scaffold_groups':11,'control_OOF_max_difference':difference,
             'metrics':comparisons,'paired_bootstrap':bootstrap,'historical_models_unchanged':not changed,
             'production_model_promoted':False,'decision_engine_changed':False,'internal_experimental_labels_added':0,
             'limitations':['Very small source-clustered assays; assay scores are never pooled as one label.',
                            'External scaffold OOF is within a paper, not independent-paper validation.',
                            'Internal OOF reuses the development 17; no untouched external internal-target benchmark.',
                            'Mass-to-molar conversion assumes reported compound form matches supplied molecular weight.',
                            'Source identity reconstruction claims require final human checking before production promotion.',
                            'Additional features alone do not establish better experiment selection.']}
    write_json(output/'experiment_summary.json',json_safe(summary))
    write_json(modeldir/'training_config.json',{'external_parameters':PARAMS,'internal_parameters':make_regressor().get_params(),
               'experiment':experiment_id,'release_hash':file_hash(release/'independent_audit.json'),
               'frozen_model_hashes':frozen_before,'training_policy':'assay_isolated_external_then_same_fold_internal_shadow'})
    write_json(modeldir/'feature_list.json',upgraded.columns.tolist())
    return summary


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--project-root',type=Path,default=Path(__file__).resolve().parents[1])
    parser.add_argument('--release',type=Path,required=True)
    parser.add_argument('--experiment-id',default='release_v1_shadow_001')
    parser.add_argument('--knowledge-mode',choices=['add','replace_atp'],default='add')
    args=parser.parse_args()
    print(json.dumps(pilot(args.project_root,args.release,args.experiment_id,args.knowledge_mode),ensure_ascii=False,indent=2))
