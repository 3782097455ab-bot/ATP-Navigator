"""Download pinned official Vina and isolated preparation dependencies, not system installation."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import urllib.request

PROJECT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PROJECT/'src'))
from workspace.state import write_json


def fetch(url):
    with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'ATP-Navigator-tool-setup'}),timeout=40) as response:
        return response.read()


def main():
    root=PROJECT/'workspace_local/tools/vina-1.2.7'
    root.mkdir(parents=True,exist_ok=True)
    metadata=json.loads(fetch('https://api.github.com/repos/ccsb-scripps/AutoDock-Vina/releases/tags/v1.2.7'))
    asset=next(a for a in metadata['assets'] if a['name']=='vina_1.2.7_win.exe')
    dest=root/asset['name']
    if not dest.exists():
        raw=fetch(asset['browser_download_url'])
        expected=asset.get('digest')
        actual='sha256:'+hashlib.sha256(raw).hexdigest()
        if expected and expected!=actual: raise ValueError('Official release checksum mismatch')
        dest.write_bytes(raw)
    else:
        actual='sha256:'+hashlib.sha256(dest.read_bytes()).hexdigest()
        if asset.get('digest') and actual!=asset['digest']: raise ValueError('Local executable mismatch')
    write_json(root/'download_provenance.json',{'url':asset['browser_download_url'],'sha256':actual,'official_digest':asset.get('digest')})
    deps=PROJECT/'workspace_local/tool_deps'
    if not (deps/'meeko').is_dir():
        subprocess.run([sys.executable,'-m','pip','install','--target',str(deps),'--no-deps','meeko==0.7.1','gemmi==0.7.3','psutil==7.2.2'],check=True)
    print(json.dumps({'vina':str(dest),'dependencies':str(deps),'training':False}))


if __name__=='__main__': main()
