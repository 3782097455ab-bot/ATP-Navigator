"""Independent supervisor: persists process identity and completion receipt on disk."""
import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from workspace.state import write_json, now, file_hash


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--manifest',required=True)
    args=parser.parse_args()
    path=Path(args.manifest)
    manifest=json.loads(path.read_text(encoding='utf-8'))
    root=Path(manifest['cwd']).resolve()
    if root!=path.parent.resolve():
        raise ValueError('Job directory mismatch')
    rc=-1
    error=None
    try:
        with (root/'stdout.txt').open('wb') as out,(root/'stderr.txt').open('wb') as err:
            child=subprocess.Popen(manifest['argv'],cwd=root,stdout=out,stderr=err,shell=False)
            write_json(root/'process.json',{'supervisor_pid':os.getpid(),'child_pid':child.pid,'started_at':now()})
            rc=child.wait()
    except Exception as exc:
        error=type(exc).__name__+': '+str(exc)
    outputs=[]
    for name in manifest['expected_outputs']:
        output=(root/name).resolve()
        if not output.is_relative_to(root):
            raise ValueError('Output escapes job directory')
        if output.is_file():
            outputs.append({'path':str(output),'sha256':file_hash(output)})
    write_json(root/'receipt.json',{'return_code':rc,'error':error,'completed_at':now(),
                                   'command_sha256':file_hash(path),'outputs':outputs})


if __name__=='__main__':
    main()
