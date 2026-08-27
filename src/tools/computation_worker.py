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


def pdbqt_atoms(path, first_model=True):
    atoms=[]
    for line in Path(path).read_text(encoding='utf-8',errors='strict').splitlines():
        if first_model and line.startswith('ENDMDL'):
            break
        if not line.startswith(('ATOM','HETATM')):
            continue
        try:
            xyz=[float(line[30:38]),float(line[38:46]),float(line[46:54])]
        except (ValueError,IndexError) as error:
            raise ValueError('Malformed PDBQT coordinates') from error
        atom_type=line.split()[-1]
        atoms.append({'xyz':xyz,'atom_type':atom_type,'heavy':not atom_type.upper().startswith('H')})
    if not atoms:
        raise ValueError('No atoms in PDBQT')
    if not all(math.isfinite(value) for atom in atoms for value in atom['xyz']):
        raise ValueError('Nonfinite PDBQT coordinates')
    return atoms


def historical_pose_atoms(path):
    atoms=[]
    for line in Path(path).read_text(encoding='utf-8',errors='strict').splitlines():
        # The frozen ATP-Ref complex stores IN-2 as the only HETATM/UNK residue.
        # Protein ATOM records are intentionally excluded from this pose metric.
        if not line.startswith('HETATM'):
            continue
        element=line[76:78].strip().upper() or line[12:16].strip()[0].upper()
        if element=='H':
            continue
        try:
            xyz=[float(line[30:38]),float(line[38:46]),float(line[46:54])]
        except (ValueError,IndexError) as error:
            raise ValueError('Malformed historical reference coordinates') from error
        atoms.append(xyz)
    if not atoms or not all(math.isfinite(v) for xyz in atoms for v in xyz):
        raise ValueError('Historical reference pose has no finite heavy atoms')
    return atoms


def centroid(points):
    return [sum(point[i] for point in points)/len(points) for i in range(3)]


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
                 'protonation':'preserve_input','salt_handling':'preserve_input','pH_enumeration':False,
                 'canonical_smiles':Chem.MolToSmiles(Chem.RemoveHs(mol))},'unit':'preparation_record'}]
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
             '--scoring','vina','--seed',str(p['seed']),'--cpu',str(p.get('cpu',1)),
             '--exhaustiveness',str(p['exhaustiveness']),'--num_modes',str(p['num_modes']),
             '--energy_range',str(p['energy_range'])]
        for i,axis in enumerate('xyz'):
            cmd += ['--center_'+axis,str(p['box']['center'][i]),'--size_'+axis,str(p['box']['size'][i])]
        write_json('native_command.json',cmd)
        subprocess.run(cmd,check=True,env=child_environment())
        parsed=parse_vina_pose('pose.pdbqt')
        if not -100.0 <= parsed['affinity'] <= 100.0:
            raise ValueError('Vina affinity outside conservative parser sanity range')
        pose_hash=file_hash('pose.pdbqt');files=['pose.pdbqt','native_command.json']
        provenance={'scoring_function':'vina','pose_selection':'first_ranked_pose','pose_rank':1,
                    'tool_id':'autodock_vina','tool_family':'vina','evidence_role':'parallel_computational_evidence',
                    'receptor_hash':r['receptor']['sha256'],'ligand_hash':r['ligand']['sha256'],
                    'output_pose_hash':pose_hash,'canonical_smiles':r['smiles']}
        evidence=[
            {'evidence_type':'vina_affinity','raw_value':parsed['affinity'],'unit':'kcal/mol','provenance':provenance},
            {'evidence_type':'docking','raw_value':{'raw_affinity':parsed['affinity'],'pose_rank':1,
              'pose_count':parsed['pose_count'],'canonical_smiles':r['smiles']},
             'unit':'docking_result_bundle','provenance':provenance},
        ]
    elif stage=='pose_qc':
        pose=check_file(r['pose']);ligand=check_file(r['ligand']);parsed=parse_vina_pose(pose)
        pose_atoms=pdbqt_atoms(pose);input_atoms=pdbqt_atoms(ligand,first_model=False)
        pose_heavy=[a['xyz'] for a in pose_atoms if a['heavy']];input_heavy=[a for a in input_atoms if a['heavy']]
        if len(pose_atoms)!=len(input_atoms) or len(pose_heavy)!=len(input_heavy):
            raise ValueError('Ligand atom integrity mismatch between prepared input and first Vina pose')
        box=r['protocol']['box'];pose_centroid=centroid(pose_heavy)
        if any(abs(pose_centroid[i]-box['center'][i])>box['size'][i]/2 for i in range(3)):
            raise ValueError('Pose centroid outside declared docking box')
        qc={'status':'pass','atom_count':len(pose_atoms),'heavy_atom_count':len(pose_heavy),
            'input_atom_count':len(input_atoms),'pose_count':parsed['pose_count'],'top_affinity':parsed['affinity'],
            'score_sanity':'finite_and_within_minus100_to_plus100_kcal_per_mol','pose_centroid':pose_centroid,
            'box_center':box['center'],'box_size':box['size'],'pose_centroid_inside_box':True,
            'parser':'tools.vina_adapter.parse_vina_pose',
            'scope':'protocol_and_file_QC_not_binding_or_activity_validation'}
        reference=r.get('reference_pose')
        if reference:
            ref=check_file(reference);ref_atoms=historical_pose_atoms(ref);ref_centroid=centroid(ref_atoms)
            qc['historical_reference']={'reference_hash':reference['sha256'],'heavy_atom_count':len(ref_atoms),
                'centroid':ref_centroid,'centroid_distance_angstrom':math.dist(pose_centroid,ref_centroid),
                'metric_scope':'protocol-comparison metric only; not biological validation'}
        evidence=[{'evidence_type':'pose_qc','raw_value':qc,'unit':'qc_record',
                   'provenance':{'tool_id':'autodock_vina','tool_family':'vina','pose_hash':r['pose']['sha256'],
                                 'ligand_hash':r['ligand']['sha256']}}]
    else:
        raise ValueError('Unimplemented stage: '+stage)
    write_json('result.json',{'compound_id':r['candidate_id'],'evidence':evidence,'files':files,'training':False})


if __name__=='__main__': main()
