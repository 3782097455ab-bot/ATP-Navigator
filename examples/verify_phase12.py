"""Run all tests and audit the actual saved execution artifacts (no training)."""
import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
import pandas as pd

PROJECT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PROJECT/'src'))
from workspace.state import file_hash,write_json


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--internal',type=Path,required=True)
    parser.add_argument('--htvs',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=False)
    process=subprocess.run([sys.executable,'-m','unittest','discover','-s',str(PROJECT/'tests'),'-v'],
                           capture_output=True,text=True,encoding='utf-8',errors='replace',cwd=PROJECT)
    (args.output/'test_stdout.txt').write_text(process.stdout,encoding='utf-8')
    (args.output/'test_stderr.txt').write_text(process.stderr,encoding='utf-8')
    checks={'all_tests_passed':process.returncode==0}
    summaries={}
    for key,folder,n in [('internal',args.internal,17),('htvs',args.htvs,1633)]:
        summary=json.loads((folder/'execution_summary.json').read_text(encoding='utf-8'))
        summaries[key]={k:summary[k] for k in ['batch_id','candidate_count','blocked_jobs','commercial_execution_completed','failed_jobs']}
        checks[key+'_sample_count']=summary['candidate_count']==n
        checks[key+'_models_unchanged']=all((PROJECT/p).is_file() and file_hash(PROJECT/p)==expected for p,expected in summary['model_hashes'].items())
        table=pd.read_csv(folder/'decision/final_navigation_report.csv')
        checks[key+'_experiments_unknown']=all(table[c].fillna('unknown').eq('unknown').all() for c in
            ['experimental_ATP_inhibition','experimental_MIC','experimental_toxicity'] if c in table)
        checks[key+'_feedback_empty']=summary['decision']['feedback']['status']=='empty'
        checks[key+'_prospective_metrics_unavailable']=summary['decision']['feedback']['prospective_metrics']=='not_available'
        checks[key+'_no_commercial_values_fabricated']=summary['commercial_execution_completed']==0
        jobs=pd.read_csv(folder/'calculation_jobs.csv',keep_default_na=False)
        checks[key+'_blocked_jobs_have_no_results']=jobs.loc[jobs.status.eq('blocked'),'output_artifacts'].eq('[]').all().item()
        if key=='htvs':
            checks['htvs_final_scores_unknown']=pd.to_numeric(table.final_score,errors='coerce').isna().all().item()
            checks['htvs_no_panel_fabricated']=summary['decision']['experimental_panel_count']==0
    # Exact preservation comparison against the previously frozen Phase10 demo.
    reference=PROJECT/'results/demo/final_navigation_report.csv'
    left=pd.read_csv(reference).set_index('compound_id')
    right=pd.read_csv(args.internal/'decision/final_navigation_report.csv').set_index('compound_id')
    differences={c:float((left[c]-right[c]).abs().max()) for c in ['model_score','final_score','rank']}
    checks['phase10_internal_ranking_preserved']=all(v<1e-10 for v in differences.values())
    frozen=['models','src/input_processor.py','src/navigator_pipeline.py','src/decision_engine.py',
            'src/experimental_feedback.py','src/feedback_evaluator.py','configs/research_profiles.json','scoring_config.json']
    diff=subprocess.run(['git','-c','safe.directory='+PROJECT.as_posix(),'diff','--exit-code','481faed','--',*frozen],cwd=PROJECT,capture_output=True)
    checks['phase11_frozen_code_config_models_unchanged']=diff.returncode==0
    result={'checks':checks,'all_passed':all(checks.values()),'runs':summaries,'ranking_max_absolute_difference':differences,
            'test_return_code':process.returncode,'test_log_sha256':file_hash(args.output/'test_stderr.txt'),
            'phase11_checkpoint':'481faed9ebec6df09143fe34a98b181426ac800d',
            'scope':'software/execution integrity, not biological efficacy or ranking performance'}
    write_json(args.output/'verification.json',result)
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return 0 if result['all_passed'] else 1


if __name__=='__main__':
    raise SystemExit(main())
