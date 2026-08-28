"""Generator API and real backend capability adapters."""
from __future__ import annotations

import importlib.util
import os
import shutil
from abc import ABC, abstractmethod
from pathlib import Path

from rdkit import Chem, rdBase
from rdkit.Chem.Scaffolds import MurckoScaffold


class GeneratorAPI(ABC):
    generator_id = "abstract"
    version = "unknown"

    @abstractmethod
    def generate(self, seed: dict, target: int) -> list[dict]: ...

    def validate(self, smiles: str) -> bool:
        mol = Chem.MolFromSmiles(smiles)
        return mol is not None

    def canonicalize(self, smiles: str) -> str:
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            raise ValueError("invalid_smiles")
        return Chem.MolToSmiles(mol, canonical=True, isomericSmiles=True)

    def deduplicate(self, rows: list[dict]) -> list[dict]:
        seen, output = set(), []
        for row in rows:
            try:
                key = self.canonicalize(row["raw_smiles"])
            except ValueError:
                output.append(row)
                continue
            if key not in seen:
                seen.add(key); output.append(row)
        return output

    def get_provenance(self, row: dict) -> dict:
        return {key: row[key] for key in ["generation_method", "generator_version", "reaction_or_operation",
                                          "building_block_id", "building_block_smiles", "attachment_atom_index"] if key in row}

    def get_parent_mapping(self, row: dict) -> dict:
        return {"parent_candidate_id": row["parent_candidate_id"], "parent_structure_hash": row["parent_structure_hash"]}


class RDKitRGroupGenerator(GeneratorAPI):
    generator_id = "rdkit_rgroup_enumeration"
    version = rdBase.rdkitVersion

    def __init__(self, config: dict):
        self.config = config

    @staticmethod
    def _attach(parent: Chem.Mol, atom_index: int, block_smiles: str) -> Chem.Mol:
        block = Chem.MolFromSmiles(block_smiles, sanitize=False)
        if block is None:
            raise ValueError("invalid_building_block")
        dummy = next((atom for atom in block.GetAtoms() if atom.GetAtomicNum() == 0), None)
        if dummy is None or dummy.GetDegree() != 1:
            raise ValueError("building_block_requires_one_dummy")
        neighbor = dummy.GetNeighbors()[0]
        combo = Chem.CombineMols(parent, block)
        editable = Chem.RWMol(combo)
        offset = parent.GetNumAtoms()
        dummy_index = offset + dummy.GetIdx()
        neighbor_index = offset + neighbor.GetIdx()
        editable.AddBond(atom_index, neighbor_index, Chem.BondType.SINGLE)
        editable.RemoveAtom(dummy_index)
        product = editable.GetMol()
        Chem.SanitizeMol(product)
        return product

    def generate(self, seed: dict, target: int) -> list[dict]:
        parent = Chem.MolFromSmiles(seed["canonical_smiles"])
        if parent is None:
            raise ValueError("invalid_seed")
        sites = [atom.GetIdx() for atom in parent.GetAtoms()
                 if atom.GetIsAromatic() and atom.GetAtomicNum() == 6 and atom.GetTotalNumHs() > 0]
        if not sites:
            raise ValueError("no_aromatic_CH_attachment_site")
        rows = []
        blocks = self.config["building_blocks"]
        for site in sites:
            for block in blocks:
                if len(rows) >= target:
                    return rows
                record = {"parent_candidate_id": seed["candidate_id"],
                          "parent_structure_hash": seed["structure_hash"],
                          "generation_method": "scaffold_preserving_R_group_enumeration",
                          "generator_version": self.version,
                          "reaction_or_operation": self.config["reaction_template_id"],
                          "reaction_smarts": self.config["reaction_smarts"],
                          "building_block_id": block["id"], "building_block_smiles": block["smiles"],
                          "attachment_atom_index": site}
                try:
                    product = self._attach(parent, site, block["smiles"])
                    record["raw_smiles"] = Chem.MolToSmiles(product, isomericSmiles=True)
                    record["generation_error"] = ""
                except Exception as error:
                    record["raw_smiles"] = ""; record["generation_error"] = f"{type(error).__name__}:{error}"
                rows.append(record)
        return rows


def backend_status(project: Path) -> dict:
    crem_module = importlib.util.find_spec("crem") is not None
    crem_db = os.environ.get("CREM_FRAGMENT_DB", "")
    if not crem_module:
        crem = {"generator_id": "crem", "version": "unknown", "status": "unavailable", "reason": "python_module_not_found",
                "supported_modes": ["mutate", "grow"], "generated": 0}
    elif not crem_db or not Path(crem_db).is_file():
        crem = {"generator_id": "crem", "version": "installed", "status": "configuration_missing",
                "reason": "CREM_FRAGMENT_DB_missing", "supported_modes": ["mutate", "grow"], "generated": 0}
    else:
        crem = {"generator_id": "crem", "version": "installed", "status": "configuration_missing",
                "reason": "fragment_db_present_but_backend_protocol_not_reviewed", "supported_modes": ["mutate", "grow"], "generated": 0}

    reinvent_exe = shutil.which("reinvent") or shutil.which("reinvent4")
    reinvent_module = importlib.util.find_spec("reinvent") is not None or importlib.util.find_spec("reinvent4") is not None
    prior = os.environ.get("REINVENT4_PRIOR", "")
    if not (reinvent_exe or reinvent_module):
        reinvent = {"generator_id": "reinvent4_shadow", "version": "unknown", "status": "unavailable",
                    "reason": "executable_and_module_not_found", "preferred_modes": ["scaffold_decoration", "mol2mol"], "generated": 0}
    elif not prior or not Path(prior).is_file():
        reinvent = {"generator_id": "reinvent4_shadow", "version": "detected", "status": "unavailable",
                    "reason": "prior_or_model_missing", "preferred_modes": ["scaffold_decoration", "mol2mol"], "generated": 0}
    else:
        reinvent = {"generator_id": "reinvent4_shadow", "version": "detected", "status": "unavailable",
                    "reason": "environment_found_but_run_protocol_not_certified", "preferred_modes": ["scaffold_decoration", "mol2mol"], "generated": 0}
    return {"rdkit_rgroup_enumeration": {"generator_id": "rdkit_rgroup_enumeration", "version": rdBase.rdkitVersion,
                                          "status": "available", "reason": "RDKit graph enumeration verified"},
            "crem": crem, "reinvent4_shadow": reinvent}


def murcko(smiles: str) -> str:
    mol = Chem.MolFromSmiles(smiles)
    return MurckoScaffold.MurckoScaffoldSmiles(mol=mol) if mol is not None else ""
