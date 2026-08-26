"""Confirmed computation workflow. No training, model replacement, or invented results."""
import argparse
import json
from dataclasses import asdict
from pathlib import Path
from workspace.planner import parse_intent
from workspace.orchestrator import ComputationalWorkspace


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project-root',type=Path,default=Path(__file__).resolve().parents[1])
    parser.add_argument('--project',default='atp_synthase')
    parser.add_argument('--intent')
    parser.add_argument('--resume-batch',help='Reconcile a saved calculation batch from durable process receipts; no automatic retry')
    parser.add_argument('--library',choices=['internal','htvs'],default='internal')
    parser.add_argument('--input',type=Path)
    parser.add_argument('--session',help='Resume the same Phase11 session/state; no parallel conversation DB')
    parser.add_argument('--protocol',type=Path,help='Explicit researcher-confirmed, hash-pinned protocol; absent means audited historical unknowns')
    parser.add_argument('--knowledge-dir',type=Path)
    parser.add_argument('--output',type=Path)
    parser.add_argument('--yes',action='store_true',help='Confirm the printed intent; does NOT approve an unknown protocol or license')
    args=parser.parse_args()
    if args.resume_batch:
        result=ComputationalWorkspace(args.project_root).recover_batch(args.resume_batch)
        print(json.dumps(result,ensure_ascii=False,indent=2))
        return 0
    if not args.intent:
        parser.error('--intent or --resume-batch is required')
    print(json.dumps({'intent':asdict(parse_intent(args.intent)),'library':args.library,
                      'warning':'Default library is 17 historical internal candidates. Select --library htvs for 1633. Unknown protocol/license blocks commercial jobs.'},ensure_ascii=False,indent=2),flush=True)
    confirmed=args.yes
    if not confirmed:
        try:
            confirmed=input('确认创建并执行可用任务？输入 yes：').strip().lower()=='yes'
        except EOFError:
            confirmed=False
    if not confirmed:
        print('Cancelled before creating jobs.')
        return 0
    result=ComputationalWorkspace(args.project_root).run(args.project,args.intent,args.library,args.input,args.session,args.protocol,
                                                       args.knowledge_dir,True,args.output)
    print(json.dumps({k:result[k] for k in ['batch_id','candidate_count','tool_execution_completed',
                    'commercial_execution_completed','blocked_jobs','failed_jobs','historical_model_hashes_unchanged','output_directory']},ensure_ascii=False,indent=2))
    return 0


if __name__=='__main__':
    raise SystemExit(main())
