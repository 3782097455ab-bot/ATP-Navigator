"""Actual RDKit worker, no commercial/experimental predictions. Runs in a child process."""
import argparse
import csv
import json
from pathlib import Path
from rdkit import Chem, rdBase
from rdkit.Chem import Descriptors, Lipinski, rdFingerprintGenerator, rdMolDescriptors, Crippen
from rdkit.Chem.Scaffolds import MurckoScaffold


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input',required=True)
    parser.add_argument('--output',required=True)
    args = parser.parse_args()
    generator = rdFingerprintGenerator.GetMorganGenerator(radius=2,fpSize=1024,includeChirality=True)
    rows = []
    with open(args.input,encoding='utf-8-sig',newline='') as stream:
        for row in csv.DictReader(stream):
            compound, smiles = row['compound_id'],row['SMILES']
            mol = Chem.MolFromSmiles(smiles)
            result = {'compound_id':compound,'input_smiles':smiles,'structure_status':'invalid',
                      'canonical_smiles':'unknown','scaffold':'unknown','morgan1024':'unknown','tool_version':rdBase.rdkitVersion}
            if mol is not None:
                result.update(structure_status='valid',canonical_smiles=Chem.MolToSmiles(mol),
                              scaffold=MurckoScaffold.MurckoScaffoldSmiles(mol=mol,includeChirality=True),
                              morgan1024=generator.GetFingerprint(mol).ToBitString(),
                              MW=Descriptors.MolWt(mol),LogP=Crippen.MolLogP(mol),TPSA=rdMolDescriptors.CalcTPSA(mol),
                              HBD=Lipinski.NumHDonors(mol),HBA=Lipinski.NumHAcceptors(mol),
                              rotatable_bonds=Lipinski.NumRotatableBonds(mol),heavy_atoms=mol.GetNumHeavyAtoms(),
                              atom_count=mol.GetNumAtoms(),ring_count=rdMolDescriptors.CalcNumRings(mol),
                              aromatic_rings=rdMolDescriptors.CalcNumAromaticRings(mol))
            rows.append(result)
    if not rows:
        raise ValueError('Empty candidate library')
    keys = sorted(set().union(*(r.keys() for r in rows)))
    with open(args.output,'x',encoding='utf-8',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=keys)
        writer.writeheader()
        writer.writerows(rows)
    print(json.dumps({'processed':len(rows),'valid':sum(r['structure_status']=='valid' for r in rows),'tool_version':rdBase.rdkitVersion}))


if __name__ == '__main__':
    main()
