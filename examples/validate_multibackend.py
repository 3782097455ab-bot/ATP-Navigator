"""Real smoke execution + historical replay. Never train or manufacture ATP outcomes."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import urllib.request
import uuid
import pandas as pd
from rdkit import Chem

PROJECT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(PROJECT/'src'))
from workspace.state import write_json,file_hash
from tools.tool_registry import discover
from workspace.multi_workflow import MultiBackendWorkspace
from workspace.multi_evidence import enriched


def download(url,destination):
    if not destination.exists():
        with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'ATP-Navigator-software-smoke'}),timeout=40) as r:
            destination.write_bytes(r.read())
    return {'url':url,'path':str(destination),'sha256':file_hash(destination)}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--skip-tests',action='store_true');args=parser.parse_args()
    token=uuid.uuid4().hex[:8];output=PROJECT/'results/multibackend'/('validation_'+token);output.mkdir(parents=True,exist_ok=False)
    frozen=json.loads((PROJECT/'results/phase12/internal_17_run2/execution_summary.json').read_text(encoding='utf-8'))['model_hashes']
    if not args.skip_tests:
        print('Running all regression tests',flush=True)
        test=subprocess.run([sys.executable,'-m','unittest','discover','-s','tests','-v'],cwd=PROJECT,capture_output=True)
        (output/'test_stdout.txt').write_bytes(test.stdout);(output/'test_stderr.txt').write_bytes(test.stderr)
        if test.returncode: print(test.stderr.decode(errors='replace'));raise RuntimeError('Regression tests failed: '+str(output))
    print('Probing tools and licenses',flush=True)
    caps=discover(PROJECT,output/'system_capabilities.json');write_json(PROJECT/'results/system_capabilities.json',caps)
    engine=MultiBackendWorkspace(PROJECT,capabilities=caps);state=engine.state
    reference=PROJECT/'workspace_local/official_vina_smoke';reference.mkdir(exist_ok=True)
    base='https://raw.githubusercontent.com/ccsb-scripps/AutoDock-Vina/v1.2.7/example/basic_docking/'
    receptor=download(base+'solution/1iep_receptor.pdbqt',reference/'1iep_receptor.pdbqt')
    ligand=download(base+'data/1iep_ligand.sdf',reference/'1iep_ligand.sdf')
    write_json(output/'official_smoke_sources.json',{'receptor':receptor,'ligand':ligand,'scope':'1IEP software test, not ATP synthase evidence'})
    mol=next(m for m in Chem.SDMolSupplier(str(reference/'1iep_ligand.sdf')) if m)
    library=output/'official_smoke_library.csv';pd.DataFrame([{'compound_id':'OFFICIAL_1IEP_IMATINIB','SMILES':Chem.MolToSmiles(mol)}]).to_csv(library,index=False)
    protocol={'protocol_id':'official_vina_1iep_software_smoke_v1','protocol_kind':'new_protocol','scope':'software_smoke_only',
              'target_reference':'1IEP','confirmation':'official_tutorial_smoke_only','receptor':{'path':receptor['path'],'sha256':receptor['sha256']},
              'receptor_preparation':'official_prepared_pdbqt','box':{'center':[15.190,53.903,16.917],'size':[20.,20.,20.]},
              'seed':42,'exhaustiveness':8,'ligand_preparation':'ETKDGv3_MMFF_preserve_input','historical_equivalence':False}
    smoke=engine.create('official_vina_smoke_'+token,library,'Docking最多1个，MMGBSA最多0个，最终实验预算0','open_toolchain',protocol)
    print('Executing actual official Vina software smoke: '+smoke['run_id'],flush=True)
    smoke_result=engine.resume(smoke['run_id'],confirm=True)
    write_json(output/'vina_smoke_result.json',smoke_result)
    before_attempts={j['job_id']:j['attempt'] for j in smoke_result['jobs']};before_evidence=smoke_result['evidence_count']
    cached=engine.resume(smoke['run_id'])
    cache_pass=before_attempts=={j['job_id']:j['attempt'] for j in cached['jobs']} and before_evidence==cached['evidence_count']
    print('Running 3 ATP candidates with unconfirmed historical protocol (expected truthful blocks)',flush=True)
    historical=PROJECT/'results/phase12/internal_17_run2/candidate_library.csv'
    three=output/'atp_three_structure_only.csv';pd.read_csv(historical).head(3)[['compound_id','SMILES']].to_csv(three,index=False)
    atp=engine.create('ab_atp_three_'+token,three,'Docking最多3个，MMGBSA最多3个，最终实验预算2','commercial_full')
    atp_result=engine.resume(atp['run_id'],confirm=True);write_json(output/'atp_three_result.json',atp_result)
    atp_open=engine.create('ab_atp_open_three_'+token,three,'Docking最多3个，MMGBSA最多3个，最终实验预算2','open_toolchain')
    atp_open_result=engine.resume(atp_open['run_id'],confirm=True);write_json(output/'atp_open_three_result.json',atp_open_result)
    print('Replaying 17 historical candidates via decision_only; not new docking',flush=True)
    replay_protocol={'protocol_id':'historical_internal17_multibackend_replay_v1','protocol_kind':'historical_protocol',
                     'target_reference':'7P3W','confirmation':'historical_replay_only','historical_grid_status':'missing',
                     'historical_equivalence':'not_asserted','seed':42}
    replay=engine.create('ab_atp_replay_'+token,historical,'最终实验预算6','decision_only',replay_protocol,
                         {'source_tool':'glide','source_batch':'frozen_internal17_curated_collection_actual_original_batch_unknown',
                          'mmgbsa_tool':'prime_mmgbsa','source_reference':'data/model_v3/training_table.csv','historical_protocol_incomplete':True})
    replay_result=engine.resume(replay['run_id'],confirm=True);write_json(output/'historical_17_result.json',replay_result)
    answer=engine.chat_workspace.chat(atp['session_id'],'现在还缺什么证据？');write_json(output/'research_session_evidence_answer.json',answer)
    allhash=all(file_hash(PROJECT/p)==h for p,h in frozen.items())
    ev=enriched(state,smoke_result['project_id']);vina=[r for r in ev if r['evidence_type']=='vina_affinity']
    summary={'validation_id':token,'output':str(output),'frozen_model_count':len(frozen),'all_24_hashes_unchanged':allhash,
              'cache_resume_pass':cache_pass,'actual_vina_affinity_records':len(vina),'vina_computed_affinity':[r['value'] for r in vina],
              'vina_scope':'Official 1IEP one-compound software smoke only, not ATP/7P3W validation',
              'atp_three_full_chain_completed':False,'reason':'Check concrete jobs: no approved historical grid/new protocol; checkout unavailable',
              'historical_17_panel_size':replay_result['decision']['panel_size'],
              'new_evidence_by_project':{r['project_id']:r['evidence_count'] for r in [smoke_result,atp_result,atp_open_result,replay_result]},
              'new_training':False,'experimental_feedback':'empty','runs':{k:r['run_id'] for k,r in [('vina',smoke),('atp3',atp),('atp_open3',atp_open),('historical17',replay)]}}
    write_json(output/'validation_summary.json',summary);print(json.dumps(summary,ensure_ascii=False,indent=2),flush=True)
    if not allhash or not cache_pass: raise RuntimeError('Integrity/cache checks failed')


if __name__=='__main__': main()
