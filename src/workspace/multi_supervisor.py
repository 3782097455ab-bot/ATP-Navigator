"""Supervisor survives an orchestration disconnect and persists execution receipts."""
import json
import os
from pathlib import Path
import subprocess
import sys
PROJECT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(PROJECT/'src'));sys.path.insert(0,str(PROJECT/'workspace_local/tool_deps'))
from tools.base_adapter import child_environment
from workspace.state import write_json,file_hash,now


def main():
    path=Path(sys.argv[1]);m=json.loads(path.read_text(encoding='utf-8'));root=path.parent.resolve()
    if Path(m['cwd']).resolve()!=root: raise ValueError('Job root mismatch')
    rc=-1;error=None;result_hash=None;artifacts=[]
    try:
        try: import psutil
        except ImportError: psutil=None
        with (root/'stdout.txt').open('wb') as out,(root/'stderr.txt').open('wb') as err:
            p=subprocess.Popen(m['argv'],cwd=root,stdout=out,stderr=err,env=child_environment(),shell=False)
            write_json(root/'process.json',{'supervisor_pid':os.getpid(),'supervisor_created':psutil.Process().create_time() if psutil else None,
                                           'child_pid':p.pid,'child_created':psutil.Process(p.pid).create_time() if psutil else None})
            try: rc=p.wait(timeout=m['timeout_seconds'])
            except subprocess.TimeoutExpired:
                for child in (psutil.Process(p.pid).children(recursive=True) if psutil else []):
                    try: child.kill()
                    except psutil.NoSuchProcess: pass
                p.kill();p.wait();rc=-2;error='Job exceeded explicit timeout'
        result=root/'result.json'
        if result.is_file():
            result_hash=file_hash(result)
            for name in json.loads(result.read_text(encoding='utf-8'))['files']:
                item=(root/name).resolve()
                if not item.is_relative_to(root): raise ValueError('Output path escape')
                artifacts.append({'path':str(item),'sha256':file_hash(item)})
    except Exception as e: error=type(e).__name__+': '+str(e);rc=-1
    write_json(root/'receipt.json',{'return_code':rc,'error':error,'completed_at':now(),
                 'command_sha256':file_hash(path),'result_sha256':result_hash,'artifacts':artifacts})


if __name__=='__main__': main()
