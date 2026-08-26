"""Real Schrödinger SDK adapter. Runtime products and protocols remain gated."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
PROJECT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(PROJECT/'src'))
from workspace.state import file_hash,write_json


def pinned(item):
    p=Path(item['path'])
    if file_hash(p)!=item['sha256']: raise ValueError('Commercial input hash mismatch')
    return p


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--request',required=True);r=json.loads(Path(ap.parse_args().request).read_text(encoding='utf-8'))
    from schrodinger import structure
    tool=r.get('tool_id_override',r['tool_id']);p=r['protocol'];cid=r['candidate_id'];files=[];evidence=[]
    if tool=='ligprep':
        ligand=pinned(r['ligand'])
        if p.get('ligprep_policy')!='native_version_defaults_i0_s1':
            raise ValueError('Explicit version-pinned LigPrep default policy required')
        # Preserves supplied ionization; no implicit Epik or salt/tautomer policy.
        cmd=[r['executable'],'-isd',str(ligand),'-osd','prepared.sdf','-i','0','-s','1','-WAIT','-LOCAL']
        expected='prepared.sdf'
    elif tool=='glide':
        ligand=pinned(r['ligand']);grid=pinned(p['grid']);precision=r.get('precision','SP')
        if precision not in {'HTVS','SP','XP'}: raise ValueError('Unsupported Glide precision')
        Path('dock.in').write_text('GRIDFILE '+json.dumps(str(grid))+'\nLIGANDFILE '+json.dumps(str(ligand))+'\nPRECISION '+precision+'\n',encoding='utf-8')
        cmd=[r['executable'],'dock.in','-WAIT','-LOCAL'];expected='dock_pv.maegz'
    elif tool=='prime_mmgbsa':
        pose=pinned(r['pose']);settings=p['mmgbsa']
        if settings['job_type'] not in {'ENERGY','REAL_MIN'}: raise ValueError('Unsupported explicit Prime job type')
        if settings['force_field']!='OPLS_2005': raise ValueError('This initial adapter supports explicit OPLS_2005 only')
        if settings.get('solvation_model')!='product_default' or settings.get('receptor_flexibility')!='frozen_receptor':
            raise ValueError('Only version-pinned product-default solvation and frozen receptor are implemented; other protocols blocked')
        cmd=[r['executable'],str(pose),'-jobname','prime','-job_type',settings['job_type'],
             '-prime_opt','OPLS_VERSION='+settings['force_field'],'-csv_output','yes','-WAIT','-RETRIES','0']
        expected='prime-out.maegz'
    elif tool=='qikprop':
        ligand=pinned(r['ligand']);cmd=[r['executable'],str(ligand),'-outname','properties','-noneut','-WAIT','-LOCAL'];expected='properties-out.mae'
    elif tool=='commercial_pose_qc':
        pose=pinned(r['pose']);sts=list(structure.StructureReader(str(pose)))
        if len(sts)<2 or not any('r_i_docking_score' in st.property for st in sts): raise ValueError('Poseviewer receptor/ligand missing')
        evidence=[{'evidence_type':'pose_qc','raw_value':{'status':'pass','scope':'poseviewer_structure_and_score_presence'},'unit':'qc_record'}]
        write_json('result.json',{'compound_id':cid,'evidence':evidence,'files':[]});return
    else: raise ValueError('Unsupported licensed adapter')
    write_json('native_command.json',cmd);subprocess.run(cmd,check=True)
    candidates=[Path(expected),Path(expected.replace('.maegz','.mae')),Path(expected.replace('.mae','.maegz'))]
    output=next((x for x in candidates if x.is_file()),None)
    if output is None: raise ValueError('Native output absent; inspect product/version, no simulated fallback')
    sts=list(structure.StructureReader(str(output)))
    if tool=='ligprep':
        if len(sts)!=1 or sts[0].title!=cid: raise ValueError('Ambiguous LigPrep identity/variant')
        evidence=[{'evidence_type':'commercial_ligand_preparation','raw_value':{'status':'completed','variants':1},'unit':'preparation_record'}]
    else:
        primary={'glide':'r_i_docking_score','prime_mmgbsa':'r_psp_MMGBSA_dG_Bind'}.get(tool)
        relevant=[st for st in sts if (primary in st.property if primary else any(k.startswith(('r_qp_','i_qp_')) for k in st.property))]
        if not relevant or any(st.title!=cid for st in relevant): raise ValueError('Missing/ambiguous output identity')
        st=min(relevant,key=lambda s:float(s.property[primary])) if primary else relevant[0]
        if primary:
            evidence=[{'evidence_type':('glide_xp_score' if r.get('precision')=='XP' else 'glide_score') if tool=='glide' else 'prime_mmgbsa','raw_value':float(st.property[primary]),
                       'unit':'Glide_score' if tool=='glide' else 'kcal/mol','provenance':{'pose_selection':'minimum_score'}}]
        else:
            if len(relevant)!=1: raise ValueError('QikProp variants need explicit selection')
            value={k:float(v) for k,v in st.property.items() if k.startswith(('r_qp_','i_qp_'))}
            evidence=[{'evidence_type':'qikprop_properties','raw_value':value,'unit':'native_property_bundle'}]
    files=[str(output),'native_command.json']
    write_json('result.json',{'compound_id':cid,'evidence':evidence,'files':files,'training':False})


if __name__=='__main__': main()
