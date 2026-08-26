"""Single real computation in an isolated job directory; no invented energies."""
import argparse
import json
import math
from pathlib import Path
import subprocess
import sys

PROJECT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(PROJECT/'src'))
sys.path.insert(0,str(PROJECT/'workspace_local/tool_deps'))
from workspace.state import write_json,file_hash
from tools.base_adapter import child_environment
from tools.vina_adapter import validate_box,parse_vina_pose


def check_file(item):
    path=Path(item['path'])
    if not path.is_file() or file_hash(path)!=item['sha256']:
        raise ValueError('Input artifact missing or hash mismatch')
    return path


def molecule(smiles):
    from rdkit import Chem
    mol=Chem.MolFromSmiles(smiles)
    if mol is None: raise ValueError('Invalid SMILES')
    return mol


def descriptors(mol):
    from rdkit.Chem import Descriptors,Lipinski,Crippen,rdMolDescriptors
    return {'MW':Descriptors.MolWt(mol),'LogP':Crippen.MolLogP(mol),'TPSA':rdMolDescriptors.CalcTPSA(mol),
            'HBD':Lipinski.NumHDonors(mol),'HBA':Lipinski.NumHAcceptors(mol),
            'rotatable_bonds':Lipinski.NumRotatableBonds(mol),'heavy_atoms':mol.GetNumHeavyAtoms(),
            'ring_count':rdMolDescriptors.CalcNumRings(mol),'aromatic_rings':rdMolDescriptors.CalcNumAromaticRings(mol)}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--request',required=True); args=parser.parse_args()
    r=json.loads(Path(args.request).read_text(encoding='utf-8'));stage=r['stage'];files=[];evidence=[]
    from rdkit import Chem,rdBase
    if stage in {'structure_qc','properties','ligand_preparation'}:
        mol=molecule(r['smiles'])
    if stage=='structure_qc':
        from rdkit.Chem import rdFingerprintGenerator
        from rdkit.Chem.Scaffolds import MurckoScaffold
        value={'structure_status':'valid','canonical_smiles':Chem.MolToSmiles(mol),
               'scaffold':MurckoScaffold.MurckoScaffoldSmiles(mol=mol),
               'morgan1024':rdFingerprintGenerator.GetMorganGenerator(radius=2,fpSize=1024,includeChirality=True).GetFingerprint(mol).ToBitString()}
        evidence=[{'evidence_type':'structure_qc','raw_value':value,'unit':'structure_bundle'}]
    elif stage=='properties':
        evidence=[{'evidence_type':'rdkit_properties','raw_value':descriptors(mol),'unit':'descriptor_bundle_not_ADMET'}]
    elif stage=='ligand_preparation':
        from rdkit.Chem import AllChem
        mol=Chem.AddHs(mol)
        params=AllChem.ETKDGv3();params.randomSeed=r['protocol']['seed'];params.numThreads=1
        if AllChem.EmbedMolecule(mol,params)!=0: raise ValueError('3D embedding failed')
        if not AllChem.MMFFHasAllMoleculeParams(mol): raise ValueError('MMFF parameters missing; no silent forcefield switch')
        status=AllChem.MMFFOptimizeMolecule(mol,maxIters=1000)
        if status!=0: raise ValueError('MMFF geometry did not converge')
        mol.SetProp('_Name',r['candidate_id'])
        writer=Chem.SDWriter('ligand.sdf');writer.write(mol);writer.close();files=['ligand.sdf']
        if r['backend']=='open_toolchain':
            from meeko import MoleculePreparation,PDBQTWriterLegacy
            setups=MoleculePreparation().prepare(mol)
            if len(setups)!=1: raise ValueError('Multiple preparation variants require explicit selection')
            text,ok,error=PDBQTWriterLegacy.write_string(setups[0])
            if not ok: raise ValueError(error)
            Path('ligand.pdbqt').write_text(text,encoding='utf-8');files.append('ligand.pdbqt')
        evidence=[{'evidence_type':'ligand_preparation','raw_value':{'geometry':'ETKDGv3_MMFF',
                 'protonation':'preserve_input','salt_handling':'preserve_input','pH_enumeration':False},'unit':'preparation_record'}]
    elif stage=='receptor_preparation':
        source=check_file(r['receptor'])
        if source.suffix.lower()=='.pdbqt':
            text=source.read_text(encoding='utf-8')
            if not any(x.startswith(('ATOM','HETATM')) for x in text.splitlines()): raise ValueError('Empty receptor')
            Path('receptor.pdbqt').write_bytes(source.read_bytes())
        else:
            if r['protocol'].get('receptor_preparation')!='meeko_preprotonated_pdb':
                raise ValueError('Raw PDB requires a confirmed preparation protocol and protonation; no guessed repair')
            cmd=[sys.executable,'-m','meeko.cli.mk_prepare_receptor','--read_pdb',str(source),'-o','receptor','-p']
            env=child_environment();env['PYTHONPATH']=str(PROJECT/'workspace_local/tool_deps')
            subprocess.run(cmd,check=True,env=env)
        files=['receptor.pdbqt']
        evidence=[{'evidence_type':'receptor_preparation','raw_value':{'source_sha256':r['receptor']['sha256']},'unit':'preparation_record'}]
    elif stage=='docking':
        ligand=check_file(r['ligand']);receptor=check_file(r['receptor']);p=r['protocol'];validate_box(p['box'])
        cmd=[r['executable'],'--receptor',str(receptor),'--ligand',str(ligand),'--out','pose.pdbqt',
             '--scoring','vina','--seed',str(p['seed']),'--cpu','1','--exhaustiveness',str(p['exhaustiveness']),'--num_modes','3']
        for i,axis in enumerate('xyz'):
            cmd += ['--center_'+axis,str(p['box']['center'][i]),'--size_'+axis,str(p['box']['size'][i])]
        write_json('native_command.json',cmd)
        subprocess.run(cmd,check=True,env=child_environment())
        parsed=parse_vina_pose('pose.pdbqt');files=['pose.pdbqt','native_command.json']
        evidence=[{'evidence_type':'vina_affinity','raw_value':parsed['affinity'],'unit':'kcal/mol',
                   'provenance':{'scoring_function':'vina','pose_selection':'first_ranked_pose'}}]
    elif stage=='pose_qc':
        pose=check_file(r['pose']);parsed=parse_vina_pose(pose);atoms=[]
        for line in pose.read_text(encoding='utf-8').splitlines():
            if line.startswith('ENDMDL'): break
            if line.startswith(('ATOM','HETATM')): atoms.append([float(line[30:38]),float(line[38:46]),float(line[46:54])])
        if not atoms or not all(math.isfinite(x) for a in atoms for x in a): raise ValueError('Invalid pose coordinates')
        box=r['protocol']['box'];centroid=[sum(a[i] for a in atoms)/len(atoms) for i in range(3)]
        if any(abs(centroid[i]-box['center'][i])>box['size'][i]/2 for i in range(3)):
            raise ValueError('Pose centroid outside declared docking box')
        evidence=[{'evidence_type':'pose_qc','raw_value':{'status':'pass','atom_count':len(atoms),
                   'scope':'finite_coordinates_and_box_centroid_only_not_binding_validation'},'unit':'qc_record'}]
    else:
        raise ValueError('Unimplemented stage: '+stage)
    write_json('result.json',{'compound_id':r['candidate_id'],'evidence':evidence,'files':files,'training':False})


if __name__=='__main__': main()
