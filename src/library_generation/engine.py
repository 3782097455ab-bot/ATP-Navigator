"""Versioned, deterministic and resumable reconstruction of an IN-2 derivative library.

This module deliberately reuses the reviewed Phase16 RDKit graph attachment and
provenance hash primitives.  It does not reproduce or claim equivalence to the
unavailable historical Auto_Enum library.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
import os
import time
import tracemalloc
from collections import Counter
from datetime import datetime, timezone
from itertools import combinations
from pathlib import Path
from typing import Iterator

import pandas as pd
from rdkit import Chem, rdBase
from rdkit.Chem import Crippen, Descriptors, Lipinski, rdMolDescriptors
from rdkit.Chem.FilterCatalog import FilterCatalog, FilterCatalogParams
from rdkit.Chem.MolStandardize import rdMolStandardize

from generation.backends import RDKitRGroupGenerator
from generation.registry import provenance_hash
from workspace.state import digest, file_hash, write_json


STABLE_LIBRARY_FIELDS = [
    "compound_id", "parent_id", "canonical_smiles", "inchikey", "generation_method",
    "attachment_site", "reaction_smarts", "building_block_id", "building_block_smiles",
    "generator_config", "seed", "provenance_hash",
]

OUTPUT_FIELDS = STABLE_LIBRARY_FIELDS + [
    "timestamp", "design_index", "substitution_depth", "sanitization_status",
    "desalting_status", "valence_status", "molecular_weight", "clogp", "tpsa",
    "hbd", "hba", "rotatable_bonds", "lipinski_pass", "veber_pass",
    "pains_warnings", "reactive_warnings", "warning_count", "qc_status",
    "rejection_reason",
]

REACTIVE_SMARTS = {
    "alkyl_halide": "[CX4][Cl,Br,I]",
    "aldehyde": "[CX3H1](=O)[#6]",
    "isocyanate": "N=C=O",
    "epoxide": "C1OC1",
    "michael_acceptor": "[C,c]=[C,c][C,S](=O)[O,N,C]",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _atomic_csv(rows: list[dict], path: Path, fields: list[str] = OUTPUT_FIELDS) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    os.replace(temporary, path)


def _stable_rows_hash(rows: Iterator[dict]) -> str:
    hasher = hashlib.sha256()
    for row in sorted(rows, key=lambda item: (item["canonical_smiles"], item["compound_id"])):
        payload = {field: row.get(field, "") for field in STABLE_LIBRARY_FIELDS}
        hasher.update(json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))
        hasher.update(b"\n")
    return hasher.hexdigest()


class ReconstructedLibraryGenerator:
    """Generate deterministic single/double aromatic-site IN-2 analogues."""

    def __init__(self, project: str | Path, config_path: str | Path):
        self.project = Path(project).resolve()
        path = Path(config_path)
        self.config_path = path if path.is_absolute() else self.project / path
        self.config = json.loads(self.config_path.read_text(encoding="utf-8"))
        self.blocks_path = self.project / self.config["building_block_library"]
        self.templates_path = self.project / self.config["reaction_templates"]
        self.blocks = pd.read_csv(self.blocks_path, keep_default_na=False).to_dict("records")
        self.templates = json.loads(self.templates_path.read_text(encoding="utf-8"))
        template = next(item for item in self.templates["templates"]
                        if item["template_id"] == self.config["reaction_template_id"])
        self.reaction_smarts = template["reaction_smarts"]
        self._validate_inputs()
        self.parent = self._parent()
        self.parent_mol = Chem.MolFromSmiles(self.parent["canonical_smiles"])
        self.sites = [atom.GetIdx() for atom in self.parent_mol.GetAtoms()
                      if atom.GetIsAromatic() and atom.GetAtomicNum() == 6 and atom.GetTotalNumHs() > 0]
        self.site_pairs = list(combinations(self.sites, 2))
        self.total_designs = len(self.sites) * len(self.blocks) + len(self.site_pairs) * len(self.blocks) ** 2
        dependent = {
            "config": self.config,
            "building_blocks_sha256": file_hash(self.blocks_path),
            "reaction_templates_sha256": file_hash(self.templates_path),
            "parent_structure_sha256": self.parent["structure_hash"],
            "rdkit": rdBase.rdkitVersion,
        }
        self.config_hash = digest(dependent)
        self.offset, self.step = self._permutation_parameters(self.total_designs)
        self.pains_catalog = self._pains_catalog()
        self.reactive_patterns = {name: Chem.MolFromSmarts(smarts) for name, smarts in REACTIVE_SMARTS.items()}

    def _validate_inputs(self) -> None:
        required = {"generator_id", "generator_version", "library_classification", "parent_id",
                    "building_block_library_version", "random_seed", "substitution_depths"}
        missing = required - self.config.keys()
        if missing:
            raise ValueError(f"configuration_missing_fields:{sorted(missing)}")
        if self.config["library_classification"] != "reconstructed reproducible derivative library":
            raise ValueError("library_classification_must_be_reconstructed")
        if self.config.get("historical_library_equivalence") is not False:
            raise ValueError("historical_library_equivalence_must_be_false")
        if not self.blocks:
            raise ValueError("empty_building_block_library")
        for block in self.blocks:
            mol = Chem.MolFromSmiles(block["smiles"], sanitize=False)
            dummies = [atom for atom in mol.GetAtoms() if atom.GetAtomicNum() == 0] if mol else []
            if len(dummies) != 1 or dummies[0].GetDegree() != 1:
                raise ValueError(f"invalid_building_block:{block['building_block_id']}")

    def _parent(self) -> dict:
        source = self.project / self.config["parent_source"]
        frame = pd.read_csv(source, dtype=str, keep_default_na=False)
        row = frame.loc[frame["compound_id"].eq(self.config["parent_id"])]
        if row.empty:
            raise ValueError("configured_parent_not_found")
        record = row.iloc[0]
        mol = Chem.MolFromSmiles(record["SMILES"])
        if mol is None:
            raise ValueError("configured_parent_invalid")
        canonical = Chem.MolToSmiles(mol, canonical=True, isomericSmiles=True)
        return {"parent_id": record["compound_id"], "alias": record.get("historical_alias", ""),
                "canonical_smiles": canonical, "structure_hash": hashlib.sha256(canonical.encode()).hexdigest(),
                "source": str(self.config["parent_source"]), "identity_status": record.get("identity_status", "unknown")}

    @staticmethod
    def _pains_catalog() -> FilterCatalog:
        params = FilterCatalogParams()
        params.AddCatalog(FilterCatalogParams.FilterCatalogs.PAINS_A)
        params.AddCatalog(FilterCatalogParams.FilterCatalogs.PAINS_B)
        params.AddCatalog(FilterCatalogParams.FilterCatalogs.PAINS_C)
        return FilterCatalog(params)

    def _permutation_parameters(self, size: int) -> tuple[int, int]:
        material = f"{self.config['random_seed']}|{self.config_hash}"
        token = hashlib.sha256(material.encode()).digest()
        offset = int.from_bytes(token[:8], "big") % size
        step = max(1, int.from_bytes(token[8:16], "big") % size)
        while math.gcd(step, size) != 1:
            step = (step + 1) % size or 1
        return offset, step

    def _design(self, permutation_position: int) -> dict:
        index = (self.offset + self.step * permutation_position) % self.total_designs
        block_count = len(self.blocks)
        singles = len(self.sites) * block_count
        if index < singles:
            site = self.sites[index // block_count]
            block = self.blocks[index % block_count]
            return {"design_index": index, "sites": [site], "blocks": [block]}
        relative = index - singles
        per_pair = block_count ** 2
        pair = self.site_pairs[relative // per_pair]
        block_code = relative % per_pair
        return {"design_index": index, "sites": list(pair),
                "blocks": [self.blocks[block_code // block_count], self.blocks[block_code % block_count]]}

    def _generate_product(self, design: dict) -> Chem.Mol:
        product = Chem.Mol(self.parent_mol)
        for site, block in zip(design["sites"], design["blocks"]):
            product = RDKitRGroupGenerator._attach(product, site, block["smiles"])
        return product

    def _record(self, design: dict, run_timestamp: str, seen: set[str]) -> dict:
        site_text = ";".join(map(str, design["sites"]))
        block_ids = ";".join(block["building_block_id"] for block in design["blocks"])
        block_smiles = ";".join(block["smiles"] for block in design["blocks"])
        base = {
            "parent_id": self.parent["parent_id"], "generation_method": "scaffold_preserving_R_group_enumeration",
            "attachment_site": site_text, "reaction_smarts": self.reaction_smarts,
            "building_block_id": block_ids, "building_block_smiles": block_smiles,
            "generator_config": self.config_hash, "seed": self.config["random_seed"],
            "timestamp": run_timestamp, "design_index": design["design_index"],
            "substitution_depth": len(design["sites"]), "qc_status": "rejected", "rejection_reason": "",
        }
        try:
            product = self._generate_product(design)
            Chem.SanitizeMol(product)
            raw_canonical = Chem.MolToSmiles(product, canonical=True, isomericSmiles=True)
            base["sanitization_status"] = "pass"
        except Exception as error:
            base.update({"sanitization_status": "failed", "desalting_status": "not_run", "valence_status": "failed",
                         "rejection_reason": f"generation_or_sanitization_failed:{type(error).__name__}"})
            return base
        try:
            parent = rdMolStandardize.FragmentParent(product)
            canonical = Chem.MolToSmiles(parent, canonical=True, isomericSmiles=True)
            product = Chem.MolFromSmiles(canonical)
            if product is None:
                raise ValueError("canonical_structure_unreadable")
            Chem.SanitizeMol(product)
            base.update({"desalting_status": "unchanged" if canonical == raw_canonical else "fragment_parent_applied",
                         "valence_status": "pass", "canonical_smiles": canonical})
        except Exception as error:
            base.update({"desalting_status": "failed", "valence_status": "failed",
                         "rejection_reason": f"standardization_or_valence_failed:{type(error).__name__}"})
            return base
        if canonical == self.parent["canonical_smiles"]:
            base["rejection_reason"] = "parent_duplicate"
            return base
        if canonical in seen:
            base["rejection_reason"] = "generated_duplicate"
            return base
        atoms = {atom.GetAtomicNum() for atom in product.GetAtoms()}
        allowed = set(self.config["hard_filters"]["allowed_atomic_numbers"])
        if not atoms.issubset(allowed):
            base["rejection_reason"] = "disallowed_element"
            return base
        mw = Descriptors.MolWt(product)
        charge = Chem.GetFormalCharge(product)
        if mw > float(self.config["hard_filters"]["maximum_molecular_weight"]):
            base["rejection_reason"] = "hard_molecular_weight_limit"
            return base
        if abs(charge) > int(self.config["hard_filters"]["maximum_absolute_formal_charge"]):
            base["rejection_reason"] = "hard_formal_charge_limit"
            return base
        clogp = Crippen.MolLogP(product)
        tpsa = rdMolDescriptors.CalcTPSA(product)
        hbd, hba = Lipinski.NumHDonors(product), Lipinski.NumHAcceptors(product)
        rotatable = Lipinski.NumRotatableBonds(product)
        lip = self.config["rule_filters"]["lipinski"]
        veb = self.config["rule_filters"]["veber"]
        lipinski_pass = mw <= lip["maximum_mw"] and clogp <= lip["maximum_clogp"] and hbd <= lip["maximum_hbd"] and hba <= lip["maximum_hba"]
        veber_pass = rotatable <= veb["maximum_rotatable_bonds"] and tpsa <= veb["maximum_tpsa"]
        pains = sorted(match.GetDescription() for match in self.pains_catalog.GetMatches(product))
        reactive = sorted(name for name, pattern in self.reactive_patterns.items() if pattern and product.HasSubstructMatch(pattern))
        if lip["enforce"] and not lipinski_pass:
            base["rejection_reason"] = "lipinski_rule_failed"
            return base
        if veb["enforce"] and not veber_pass:
            base["rejection_reason"] = "veber_rule_failed"
            return base
        if self.config["rule_filters"]["pains"]["enforce"] and pains:
            base["rejection_reason"] = "pains_filter_failed"
            return base
        if self.config["rule_filters"]["reactive_warnings"]["enforce"] and reactive:
            base["rejection_reason"] = "reactive_filter_failed"
            return base
        stable = {
            "parent_id": self.parent["parent_id"], "canonical_smiles": canonical,
            "inchikey": Chem.MolToInchiKey(product), "generation_method": base["generation_method"],
            "attachment_site": site_text, "reaction_smarts": self.reaction_smarts,
            "building_block_id": block_ids, "building_block_smiles": block_smiles,
            "generator_config": self.config_hash, "seed": self.config["random_seed"],
        }
        candidate_id = "ATP-RDL-" + hashlib.sha256(canonical.encode()).hexdigest()[:16].upper()
        payload = {**stable, "compound_id": candidate_id, "generator_version": self.config["generator_version"],
                   "building_block_library_version": self.config["building_block_library_version"],
                   "parent_structure_hash": self.parent["structure_hash"]}
        base.update({"compound_id": candidate_id, **stable, "provenance_hash": provenance_hash(payload),
                     "molecular_weight": round(mw, 6), "clogp": round(clogp, 6), "tpsa": round(tpsa, 6),
                     "hbd": hbd, "hba": hba, "rotatable_bonds": rotatable,
                     "lipinski_pass": lipinski_pass, "veber_pass": veber_pass,
                     "pains_warnings": "|".join(pains), "reactive_warnings": "|".join(reactive),
                     "warning_count": len(pains) + len(reactive) + int(not lipinski_pass) + int(not veber_pass),
                     "qc_status": "accepted", "rejection_reason": ""})
        seen.add(canonical)
        return base

    def _run_dir(self, run_id: str) -> Path:
        return self.project / "workspace_local" / "library_generation" / run_id

    def _load_checkpoint(self, run_dir: Path) -> tuple[dict | None, set[str]]:
        path = run_dir / "checkpoint.json"
        if not path.is_file():
            return None, set()
        checkpoint = json.loads(path.read_text(encoding="utf-8"))
        if checkpoint["config_hash"] != self.config_hash or checkpoint["parent_structure_hash"] != self.parent["structure_hash"]:
            raise ValueError("checkpoint_input_mismatch")
        seen: set[str] = set()
        parts = sorted((run_dir / "chunks").glob("part_*.csv"))
        expected_names = [f"part_{index:06d}.csv" for index in range(len(parts))]
        if [part.name for part in parts] != expected_names:
            raise ValueError("checkpoint_chunk_sequence_gap")
        observed_raw = observed_accepted = observed_rejected = 0
        for part in parts:
            frame = pd.read_csv(part, dtype=str, keep_default_na=False)
            accepted = frame["qc_status"].eq("accepted")
            observed_raw += len(frame)
            observed_accepted += int(accepted.sum())
            observed_rejected += int((~accepted).sum())
            seen.update(frame.loc[accepted, "canonical_smiles"])
        if observed_raw < checkpoint["raw_processed"]:
            raise ValueError("checkpoint_ahead_of_durable_chunks")
        if observed_raw > checkpoint["raw_processed"]:
            # A process may stop after the atomic chunk rename but before the
            # checkpoint rename.  Contiguous durable chunks are authoritative.
            checkpoint.update({"raw_processed": observed_raw, "next_permutation_position": observed_raw,
                               "accepted": observed_accepted, "rejected": observed_rejected,
                               "next_chunk": len(parts), "status": "recovered_from_durable_chunks",
                               "updated_at": _utc_now()})
            write_json(path, checkpoint)
        if len(seen) != checkpoint["accepted"] or observed_rejected != checkpoint["rejected"]:
            raise ValueError("checkpoint_chunk_count_mismatch")
        return checkpoint, seen

    def generate(self, target_unique: int, run_id: str, stop_after_processed: int | None = None) -> dict:
        if target_unique < 1 or target_unique > self.total_designs:
            raise ValueError(f"target_unique must be 1-{self.total_designs}")
        run_dir = self._run_dir(run_id)
        chunks = run_dir / "chunks"
        chunks.mkdir(parents=True, exist_ok=True)
        checkpoint, seen = self._load_checkpoint(run_dir)
        if checkpoint and checkpoint["target_unique"] != target_unique:
            raise ValueError("checkpoint_target_mismatch")
        state = checkpoint or {
            "schema_version": "library_checkpoint_v1", "run_id": run_id, "target_unique": target_unique,
            "config_hash": self.config_hash, "parent_structure_hash": self.parent["structure_hash"],
            "next_permutation_position": 0, "raw_processed": 0, "accepted": 0, "rejected": 0,
            "next_chunk": 0, "run_timestamp": _utc_now(), "status": "running",
            "elapsed_seconds_total": 0.0, "peak_python_memory_mb": 0.0,
        }
        if state["status"] == "completed":
            manifest_path = run_dir / "manifest.json"
            if manifest_path.is_file():
                return json.loads(manifest_path.read_text(encoding="utf-8"))
            return self._finalize(run_dir, state, 0.0, float(state.get("peak_python_memory_mb", 0.0)))
        start_time = time.perf_counter()
        tracemalloc.start()
        buffer: list[dict] = []
        stop_at = state["raw_processed"] + stop_after_processed if stop_after_processed else None

        def flush() -> None:
            nonlocal buffer
            if not buffer:
                return
            _atomic_csv(buffer, chunks / f"part_{state['next_chunk']:06d}.csv")
            state["next_chunk"] += 1
            buffer = []
            state["updated_at"] = _utc_now()
            write_json(run_dir / "checkpoint.json", state)

        while state["accepted"] < target_unique and state["next_permutation_position"] < self.total_designs:
            design = self._design(state["next_permutation_position"])
            record = self._record(design, state["run_timestamp"], seen)
            buffer.append(record)
            state["next_permutation_position"] += 1
            state["raw_processed"] += 1
            if record["qc_status"] == "accepted":
                state["accepted"] += 1
            else:
                state["rejected"] += 1
            if len(buffer) >= int(self.config["chunk_size"]):
                flush()
            if stop_at is not None and state["raw_processed"] >= stop_at:
                flush()
                state["status"] = "paused_checkpoint"
                invocation_elapsed = time.perf_counter() - start_time
                current, peak = tracemalloc.get_traced_memory(); tracemalloc.stop()
                state["elapsed_seconds_total"] = float(state.get("elapsed_seconds_total", 0.0)) + invocation_elapsed
                state["peak_python_memory_mb"] = max(float(state.get("peak_python_memory_mb", 0.0)), peak / 1024 / 1024)
                state["updated_at"] = _utc_now()
                write_json(run_dir / "checkpoint.json", state)
                return {**state, "elapsed_seconds_this_invocation": invocation_elapsed}
        flush()
        if state["accepted"] < target_unique:
            state["status"] = "design_space_exhausted"
        else:
            state["status"] = "completed"
        state["updated_at"] = _utc_now()
        current, peak = tracemalloc.get_traced_memory(); tracemalloc.stop()
        invocation_elapsed = time.perf_counter() - start_time
        state["elapsed_seconds_total"] = float(state.get("elapsed_seconds_total", 0.0)) + invocation_elapsed
        state["peak_python_memory_mb"] = max(float(state.get("peak_python_memory_mb", 0.0)), peak / 1024 / 1024)
        write_json(run_dir / "checkpoint.json", state)
        return self._finalize(run_dir, state, invocation_elapsed, state["peak_python_memory_mb"])

    def _finalize(self, run_dir: Path, state: dict, elapsed: float, peak_mb: float) -> dict:
        frames = [pd.read_csv(path, keep_default_na=False) for path in sorted((run_dir / "chunks").glob("part_*.csv"))]
        all_rows = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=OUTPUT_FIELDS)
        accepted = all_rows.loc[all_rows["qc_status"].eq("accepted")].copy()
        rejected = all_rows.loc[all_rows["qc_status"].eq("rejected")].copy()
        accepted = accepted.sort_values(["canonical_smiles", "compound_id"]).reset_index(drop=True)
        rejected = rejected.sort_values(["design_index"]).reset_index(drop=True)
        _atomic_csv(accepted.to_dict("records"), run_dir / "library.csv")
        _atomic_csv(rejected.to_dict("records"), run_dir / "rejections.csv")
        library_hash = _stable_rows_hash(accepted.to_dict("records"))
        rejection_counts = Counter(rejected["rejection_reason"].astype(str)) if len(rejected) else Counter()
        counts = {
            "design_space": self.total_designs, "raw_processed": int(state["raw_processed"]),
            "accepted_unique": len(accepted), "rejected": len(rejected),
            "rejection_reasons": dict(sorted(rejection_counts.items())),
            "lipinski_pass": int(accepted["lipinski_pass"].astype(str).str.lower().eq("true").sum()),
            "veber_pass": int(accepted["veber_pass"].astype(str).str.lower().eq("true").sum()),
            "pains_warning_structures": int(accepted["pains_warnings"].astype(str).ne("").sum()),
            "reactive_warning_structures": int(accepted["reactive_warnings"].astype(str).ne("").sum()),
        }
        write_json(run_dir / "stage_counts.json", counts)
        manifest = {
            "run_id": state["run_id"], "status": state["status"], "classification": self.config["library_classification"],
            "historical_library_equivalence": False, "target_unique": state["target_unique"],
            "config_path": str(self.config_path.relative_to(self.project)).replace("\\", "/"),
            "config_hash": self.config_hash, "library_hash": library_hash,
            "parent": self.parent, "attachment_sites": self.sites, "reaction_smarts": self.reaction_smarts,
            "building_block_library_version": self.config["building_block_library_version"],
            "building_block_count": len(self.blocks), "generator_version": self.config["generator_version"],
            "rdkit_version": rdBase.rdkitVersion, "random_seed": self.config["random_seed"],
            "deduplication": self.config["deduplication_key"], "sanitization": self.config["sanitization"],
            "counts": counts, "elapsed_seconds_this_invocation": elapsed,
            "elapsed_seconds_total": float(state.get("elapsed_seconds_total", elapsed)), "peak_python_memory_mb": peak_mb,
            "library_file": str((run_dir / "library.csv").relative_to(self.project)).replace("\\", "/"),
            "rejections_file": str((run_dir / "rejections.csv").relative_to(self.project)).replace("\\", "/"),
            "checkpoint_file": str((run_dir / "checkpoint.json").relative_to(self.project)).replace("\\", "/"),
            "completed_at": _utc_now(), "scientific_boundary": self.config["scientific_boundary"],
        }
        write_json(run_dir / "manifest.json", manifest)
        return manifest

    def verify_library(self, run_id: str) -> dict:
        run_dir = self._run_dir(run_id)
        manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
        frame = pd.read_csv(run_dir / "library.csv", keep_default_na=False)
        actual = _stable_rows_hash(frame.to_dict("records"))
        provenance_complete = bool(len(frame) and frame["provenance_hash"].str.fullmatch(r"[0-9a-f]{64}").all())
        unique = not frame["canonical_smiles"].duplicated().any() and not frame["inchikey"].duplicated().any()
        result = {"run_id": run_id, "rows": len(frame), "manifest_library_hash": manifest["library_hash"],
                  "recomputed_library_hash": actual, "hash_match": actual == manifest["library_hash"],
                  "canonical_and_inchikey_unique": unique, "provenance_complete": provenance_complete}
        write_json(run_dir / "verification.json", result)
        return result
