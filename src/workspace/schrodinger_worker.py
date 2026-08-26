"""Run inside the licensed Schrödinger Python environment. Not tested locally:
no Schrödinger installation is present. No grid generation and no ligand prep.
Only approved, hash-pinned inputs; one compound per job, best pose explicitly.
"""
import argparse
import csv
import hashlib
import json
import shutil
import subprocess
from pathlib import Path


def sha(path):
    h=hashlib.sha256()
    with open(path,'rb') as stream:
        for chunk in iter(lambda:stream.read(1048576),b''):
            h.update(chunk)
    return h.hexdigest()


def main():
    args=argparse.ArgumentParser()
    args.add_argument('--manifest',required=True)
    opts=args.parse_args()
    manifest=json.loads(Path(opts.manifest).read_text(encoding='utf-8'))
    from schrodinger import structure
    tool,compound=manifest['tool_id'],manifest['candidate_id']
    source=Path(manifest['prepared_input']['path'])
    if sha(source)!=manifest['prepared_input']['sha256']:
        raise ValueError('Input hash changed')
    ligand=Path('ligand'+''.join(source.suffixes))
    shutil.copyfile(source,ligand)
    # Identity is not guessed from a similarly named file.
    titles=[str(st.title) for st in structure.StructureReader(str(ligand))]
    if compound not in titles or any(t!=compound for t in titles[(1 if tool=='prime_mmgbsa' else 0):]):
        raise ValueError('Prepared input title must explicitly match the candidate ID')
    executable=manifest['executable']
    if tool=='glide':
        grid=manifest['grid']
        if sha(grid['path'])!=grid['sha256']:
            raise ValueError('Readonly grid hash changed')
        text='GRIDFILE '+json.dumps(grid['path'])+'\nLIGANDFILE '+json.dumps(str(ligand))+'\nPRECISION '+manifest['stage']+'\n'
        Path('dock.in').write_text(text,encoding='utf-8')
        command=[executable,'dock.in','-WAIT','-LOCAL']
        primary='r_i_docking_score'
        outputs=['dock_pv.maegz','dock_lib.maegz','dock_pv.mae','dock_lib.mae']
    elif tool=='prime_mmgbsa':
        command=[executable,str(ligand),'-WAIT','-LOCAL']+manifest.get('cli_arguments',[])
        primary='r_psp_MMGBSA_dG_Bind'
        outputs=['ligand-out.maegz','ligand-out.mae']
    elif tool=='qikprop':
        command=[executable,str(ligand),'-outname','result','-WAIT','-LOCAL']
        primary=None
        outputs=['result-out.maegz','result-out.mae','result-out.sdf']
    else:
        raise ValueError('Unsupported commercial adapter')
    Path('actual_native_command.json').write_text(json.dumps(command),encoding='utf-8')
    process=subprocess.run(command,shell=False)
    if process.returncode:
        raise SystemExit(process.returncode)
    paths=[Path(p) for p in outputs if Path(p).is_file()]
    if not paths:
        raise RuntimeError('Expected native result artifact absent; adapter/version needs inspection')
    records=[]
    for path in paths[:1]:
        for st in structure.StructureReader(str(path)):
            properties=dict(st.property)
            if primary and primary not in properties:
                continue
            if not primary and not any(k.startswith(('r_qp_','i_qp_')) for k in properties):
                continue
            if str(st.title)!=compound:
                raise ValueError('Output identity differs from job candidate')
            records.append({'compound_id':compound,**properties})
    if not records:
        raise RuntimeError('Native result has no recognized candidate properties')
    selected=min(records,key=lambda r:float(r[primary])) if primary else records[0]
    if not primary and len(records)>1:
        raise ValueError('QikProp multiple variants require a confirmed preparation selection')
    with open('result.csv','x',encoding='utf-8',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=sorted(selected))
        writer.writeheader()
        writer.writerow(selected)
    Path('native_artifacts.json').write_text(json.dumps({'files':[str(p) for p in paths],
                                                      'pose_selection':'minimum_'+primary if primary else 'single_input_variant'}),encoding='utf-8')


if __name__=='__main__':
    main()
