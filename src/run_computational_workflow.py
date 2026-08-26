"""Plan first, explicitly confirm expensive execution, resume by durable run id."""
import argparse
import json
from pathlib import Path
from workspace.multi_workflow import MultiBackendWorkspace
from tools.tool_registry import discover
from workspace.state import write_json,now


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project-root',type=Path,default=Path(__file__).resolve().parents[1])
    sub=parser.add_subparsers(dest='action',required=True)
    inspect=sub.add_parser('inspect')
    plan=sub.add_parser('plan');plan.add_argument('--project',required=True);plan.add_argument('--input',type=Path,required=True)
    plan.add_argument('--intent',required=True);plan.add_argument('--mode',choices=['decision_only','open_toolchain','commercial_full'],default='decision_only')
    plan.add_argument('--protocol',type=Path);plan.add_argument('--source-metadata',type=Path)
    resume=sub.add_parser('resume');resume.add_argument('run_id');resume.add_argument('--confirm',action='store_true');resume.add_argument('--retry-failed',action='store_true')
    status=sub.add_parser('status');status.add_argument('run_id')
    args=parser.parse_args()
    if args.action=='inspect':
        folder=args.project_root/'results/multibackend'/('capabilities_'+now().replace(':','').replace('+','_'))
        data=discover(args.project_root,folder/'system_capabilities.json')
        write_json(args.project_root/'results/system_capabilities.json',data)
        print(json.dumps(data,ensure_ascii=False,indent=2));return
    engine=MultiBackendWorkspace(args.project_root)
    if args.action=='plan':
        result=engine.create(args.project,args.input,args.intent,args.mode,
            json.loads(args.protocol.read_text(encoding='utf-8')) if args.protocol else None,
            json.loads(args.source_metadata.read_text(encoding='utf-8')) if args.source_metadata else None)
    elif args.action=='resume': result=engine.resume(args.run_id,args.confirm,args.retry_failed)
    else: result=engine.status(args.run_id)
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__': main()
