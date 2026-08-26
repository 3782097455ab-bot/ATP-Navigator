"""Reconcile real saved runs without redocking, run final tests, verify frozen artifacts."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import uuid
import pandas as pd
PROJECT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(PROJECT/'src'))
from workspace.multi_workflow import MultiBackendWorkspace
from workspace.workflow_service import WorkflowService
from tools.tool_registry import discover
from workspace.state import write_json,file_hash


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--validation',type=Path,required=True);ap.add_argument('--capabilities',type=Path);args=ap.parse_args()
    source=json.loads((args.validation/'validation_summary.json').read_text(encoding='utf-8'))
    output=PROJECT/'results/multibackend'/('final_checks_'+uuid.uuid4().hex[:8]);output.mkdir(exist_ok=False)
    print('Final regression suite',flush=True)
    p=subprocess.run([sys.executable,'-m','unittest','discover','-s','tests','-v'],cwd=PROJECT,capture_output=True)
    (output/'test_stdout.txt').write_bytes(p.stdout);(output/'test_stderr.txt').write_bytes(p.stderr)
    if p.returncode: print(p.stderr.decode(errors='replace'));raise RuntimeError('Tests failed '+str(output))
    print('Final product-specific checkout probes',flush=True)
    caps=json.loads(args.capabilities.read_text(encoding='utf-8')) if args.capabilities else discover(PROJECT)
    write_json(output/'system_capabilities.json',caps);write_json(PROJECT/'results/system_capabilities.json',caps)
    engine=MultiBackendWorkspace(PROJECT);results={};attempts_unchanged={}
    for name,run_id in source['runs'].items():
        print('Resume saved run '+name,flush=True)
        before=engine.status(run_id);result=engine.resume(run_id)
        attempts_unchanged[name]={j['job_id']:j['attempt'] for j in before['jobs']}=={j['job_id']:j['attempt'] for j in result['jobs']}
        results[name]=result;write_json(output/(name+'_resumed.json'),result)
    again=engine.resume(source['runs']['vina'])
    stable=again['evidence_count']==results['vina']['evidence_count'] and again['decision']['decision_run_id']==results['vina']['decision']['decision_run_id']
    old=json.loads((PROJECT/'results/phase12/internal_17_run2/execution_summary.json').read_text(encoding='utf-8'))['model_hashes']
    original=pd.read_csv(PROJECT/'results/phase12/internal_17_run2/decision/final_navigation_report.csv').set_index('compound_id')
    current=pd.read_csv(Path(results['historical17']['decision']['path'])/'final_navigation_report.csv').set_index('compound_id')
    difference=(original.final_score-current.final_score).abs().max()
    session=engine.get_run(source['runs']['atp3'])['session_id']
    answer=engine.chat_workspace.chat(session,'为什么还不能排名1633个？');write_json(output/'chat_registry_answer.json',answer)
    service=WorkflowService(PROJECT)
    api={endpoint:service.request('GET','/projects/'+results['historical17']['project_id']+'/'+endpoint) for endpoint in ['candidates','jobs','evidence','decisions','experiments']}
    write_json(output/'api_shared_state_check.json',{'counts':{k:len(v) for k,v in api.items() if isinstance(v,list)},'experiments':api['experiments']})
    checks={'all_24_models_unchanged':len(old)==24 and all(file_hash(PROJECT/p)==h for p,h in old.items()),
            'no_reexecution_on_resume':all(attempts_unchanged.values()),'stable_cache_and_decision':stable,
            'historical_scores_unchanged':bool(difference<1e-10),'historical_panel_six':results['historical17']['decision']['panel_size']==6,
            'real_vina_completed':any(j['tool_id']=='vina' and j['status']=='completed' for j in results['vina']['jobs']),
            'no_ATP_new_docking_fabricated':not any(j['tool_id'] in {'vina','glide','prime_mmgbsa','qikprop'} and j['status']=='completed' for k in ['atp3','atp_open3'] for j in results[k]['jobs']),
            'chat_reads_registry':answer['source']=='shared_Evidence_Registry','feedback_empty':results['historical17']['decision']['feedback']['status']=='empty'}
    summary={'checks':checks,'all_passed':all(checks.values()),'historical_final_score_max_difference':float(difference),
             'evidence_counts':{k:v['evidence_count'] for k,v in results.items()},'original_validation':str(args.validation),
             'final_output':str(output),'run_ids':source['runs'],'training':False}
    write_json(output/'final_acceptance.json',summary);print(json.dumps(summary,ensure_ascii=False,indent=2),flush=True)
    if not summary['all_passed']: raise RuntimeError('Acceptance invariant failed')


if __name__=='__main__': main()
