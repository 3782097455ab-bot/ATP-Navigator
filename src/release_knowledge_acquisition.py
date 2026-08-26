"""Use corrected external structures to prioritize *future calculations*, not experiments.

This transparent retrieval/acquisition rule does not alter the frozen final score.
Every similarity is computed by RDKit; no activity or new docking value is made up.
"""
import argparse
from pathlib import Path
import pandas as pd
from rdkit import DataStructs
from release_v1_pilot import fingerprints
from release_v1_audit import identity_key
from workspace.state import State,file_hash,write_json,encode


def run(project,release,output,budget=40):
    project,release,output=Path(project),Path(release),Path(output)
    if budget<0:
        raise ValueError('Nonnegative budget required')
    output.mkdir(parents=True,exist_ok=False)
    path=project/'data/htvs_structures_v0_1.csv'
    library=pd.read_csv(path)
    refs=pd.read_csv(release/'pilot_eligible_measurements.csv').drop_duplicates('compound_key').reset_index(drop=True)
    library=library.loc[library.extraction_status.eq('complete')&library.structure_join_status.eq('matched')].copy()
    reference_fps=fingerprints(refs.canonical_smiles)
    parent_fps=fingerprints(refs.canonical_smiles.map(identity_key))
    dock_rank=library.glide_docking_score.rank(method='average',ascending=True)
    library['docking_rank_utility']=1-(dock_rank-1)/max(len(library)-1,1)
    rows=[]
    for i,row in library.iterrows():
        fp=fingerprints([row.canonical_smiles])[0]
        values=DataStructs.BulkTanimotoSimilarity(fp,reference_fps)
        closest=max(range(len(values)),key=values.__getitem__)
        parent=fingerprints([identity_key(row.canonical_smiles)])[0]
        rows.append({'compound_id':row.canonical_id,'compound_code':row.compound_code,'canonical_smiles':row.canonical_smiles,
                     'scaffold':row.scaffold,'historical_HTVS_score':row.glide_docking_score,
                     'docking_rank_utility':row.docking_rank_utility,'reference_similarity':values[closest],
                     'parent_reference_similarity':max(DataStructs.BulkTanimotoSimilarity(parent,parent_fps)),
                     'reference_compound':refs.iloc[closest].compound_name,'reference_key':refs.iloc[closest].compound_key,
                     'reference_doi':refs.iloc[closest].doi,'source_file':row.source_file})
    frame=pd.DataFrame(rows)
    pending=frame.to_dict('records')
    selected=[]
    scaffolds=set()
    weights={'historical_docking_rank':.50,'source_reference_similarity':.35,'new_scaffold':.15}
    while pending and len(selected)<budget:
        def score(row):
            return .50*row['docking_rank_utility']+.35*row['reference_similarity']+.15*int(bool(row['scaffold'] and row['scaffold'] not in scaffolds))
        best=sorted(pending,key=lambda r:(-score(r),r['compound_id']))[0]
        priority=score(best)
        pending.remove(best)
        selected.append({**best,'acquisition_rank':len(selected)+1,'acquisition_score':priority,
                         'stage_gate':'blocked_pending_XP_prepared_complex_license_and_protocol',
                         'is_experimental_recommendation':False,'executed':False,
                         'reason':'Historical HTVS rank + actual Morgan similarity to corrected source structures + greedy scaffold diversity; not activity probability'})
        scaffolds.add(best['scaffold'])
    frame.to_csv(output/'htvs_reference_space.csv',index=False)
    pd.DataFrame(selected).to_csv(output/'provisional_mmgbsa_queue.csv',index=False)
    original=set(frame.nsmallest(min(budget,len(frame)),'historical_HTVS_score').compound_id)
    chosen={r['compound_id'] for r in selected}
    summary={'library_size':len(frame),'reference_structures':len(refs),'budget':budget,'proposed':len(selected),
             'same_as_docking_top_budget':len(original&chosen),'different_from_docking_top_budget':len(chosen-original),
             'selected_scaffolds':len(scaffolds),'mean_nearest_similarity':float(frame.reference_similarity.mean()),
             'max_nearest_similarity':float(frame.reference_similarity.max()),
             'similarity_bins':{str(threshold):int(frame.reference_similarity.ge(threshold).sum()) for threshold in [.3,.4,.5,.7,.9]},
             'weights':weights,'source_hashes':{'htvs':file_hash(path),'release':file_hash(release/'pilot_eligible_measurements.csv')},
             'status':'provisional_calculation_acquisition_only','computations_submitted':0,
             'decision_engine_changed':False,'performance_improvement_evaluated':False}
    state=State(project)
    state.project_id('atp_synthase')
    batch=state.batch('atp_synthase',{'kind':'knowledge_acquisition_analysis','mmgbsa_budget':budget,'confirmed_execution':False})
    with state.connect() as db:
        db.execute('UPDATE calculation_batch SET plan=?,actual=? WHERE batch_id=?',
                   (encode({'candidates':[r['compound_id'] for r in selected],'artifact':state.artifact(output/'provisional_mmgbsa_queue.csv')}),
                    encode({'calculations_executed':0,'status':'analysis_only'}),batch))
    summary['shared_state_batch_id']=batch
    write_json(output/'acquisition_summary.json',summary)
    return summary


if __name__=='__main__':
    import json
    parser=argparse.ArgumentParser()
    parser.add_argument('--project-root',type=Path,default=Path(__file__).resolve().parents[1])
    parser.add_argument('--release',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--budget',type=int,default=40)
    args=parser.parse_args()
    print(json.dumps(run(args.project_root,args.release,args.output,args.budget),ensure_ascii=False,indent=2))
