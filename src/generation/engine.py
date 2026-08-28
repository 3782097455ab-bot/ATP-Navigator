"""Small, real and traceable Phase 16 molecule expansion workflow."""
from __future__ import annotations

import concurrent.futures
import hashlib
import importlib.util
import json
import math
import os
import shutil
import sys
from collections import Counter
from datetime import date
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from rdkit import Chem, DataStructs
from rdkit.Chem import Crippen, Descriptors, Lipinski, rdMolDescriptors
from rdkit.Chem.FilterCatalog import FilterCatalog, FilterCatalogParams
from rdkit.Chem.MolStandardize import rdMolStandardize
from rdkit.Chem.Scaffolds import MurckoScaffold
from rdkit.Chem.rdFingerprintGenerator import GetMorganGenerator

from .backends import RDKitRGroupGenerator, backend_status
from .registry import GeneratedCandidateRegistry, GeneratorRegistry, provenance_hash

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / "src"))
sys.path.insert(0, str(PROJECT / "workspace_local/tool_deps"))
from phase14_full_library_vina import _existing_result, _sha_text, _worker
from workspace.state import digest, file_hash, write_json


def _csv(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False, encoding="utf-8-sig")


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _fp(mol: Chem.Mol):
    return GetMorganGenerator(radius=2, fpSize=2048).GetFingerprint(mol)


def _similarity(fp, fps) -> tuple[float, int]:
    if not fps:
        return 0.0, -1
    values = DataStructs.BulkTanimotoSimilarity(fp, fps)
    index = int(np.argmax(values))
    return float(values[index]), index


def _catalog() -> FilterCatalog:
    params = FilterCatalogParams()
    params.AddCatalog(FilterCatalogParams.FilterCatalogs.PAINS_A)
    params.AddCatalog(FilterCatalogParams.FilterCatalogs.PAINS_B)
    params.AddCatalog(FilterCatalogParams.FilterCatalogs.PAINS_C)
    return FilterCatalog(params)


def _sa_like(mol: Chem.Mol) -> float:
    """Transparent 1-10 tractability proxy; not AiZynthFinder or experimental SA."""
    rings = rdMolDescriptors.CalcNumRings(mol)
    spiro = rdMolDescriptors.CalcNumSpiroAtoms(mol)
    bridge = rdMolDescriptors.CalcNumBridgeheadAtoms(mol)
    rot = Lipinski.NumRotatableBonds(mol)
    stereo = len(Chem.FindMolChiralCenters(mol, includeUnassigned=True))
    heavy = mol.GetNumHeavyAtoms()
    raw = 1.0 + 0.035 * max(heavy - 15, 0) + 0.12 * rot + 0.18 * rings + 0.4 * (spiro + bridge) + 0.1 * stereo
    return float(min(10.0, max(1.0, raw)))


class MoleculeExpansionEngine:
    def __init__(self, project: str | Path):
        self.project = Path(project).resolve()
        self.output = self.project / "results/phase16"
        self.runtime = self.project / "workspace_local/phase16_vina"
        self.config_path = self.project / "configs/generation_phase16.json"
        self.config = json.loads(self.config_path.read_text(encoding="utf-8"))

    def _seeds(self) -> list[dict]:
        manifest = pd.read_csv(self.project / "configs/projects/ab_atp_synthase/vina_7p3w_v1/candidate_identity_manifest.csv", dtype=str)
        in2 = manifest.loc[manifest["historical_alias"].eq("IN-2")].iloc[0]
        ranking = pd.read_csv(self.project / "results/ranking_output.csv", dtype=str)
        hit3 = ranking.loc[ranking["historical_alias"].eq("Hit3")].iloc[0]
        seeds = [
            {"candidate_id": in2.compound_id, "historical_alias": "IN-2", "canonical_smiles": Chem.MolToSmiles(Chem.MolFromSmiles(in2.SMILES)),
             "source": "confirmed_reference_pose", "htvs_identity": "not_claimed"},
            {"candidate_id": hit3.compound_id, "historical_alias": "Hit3", "canonical_smiles": Chem.MolToSmiles(Chem.MolFromSmiles(hit3.smiles)),
             "source": "internal_historical_structure", "htvs_identity": "unresolved"},
        ]
        for seed in seeds:
            seed["structure_hash"] = _hash_text(seed["canonical_smiles"])
            seed["murcko_scaffold"] = MurckoScaffold.MurckoScaffoldSmilesFromSmiles(seed["canonical_smiles"])
        return seeds

    def _capabilities(self) -> dict:
        registry = GeneratorRegistry()
        values = backend_status(self.project)
        for record in values.values():
            registry.register(record)
        payload = registry.as_dict()
        payload["simulation_used"] = False
        payload["phase16_backend_policy"] = "unavailable backends generate zero molecules"
        write_json(self.output / "generator_backend_status.json", payload)
        return payload

    def _qc(self, raw: list[dict], seeds: list[dict]) -> tuple[pd.DataFrame, pd.DataFrame]:
        historical = pd.read_csv(self.project / "data/htvs_structures_v0_1.csv")
        historical_smiles = set(historical["canonical_smiles"].astype(str))
        parent_smiles = {seed["canonical_smiles"] for seed in seeds}
        catalog = _catalog(); registry = GeneratedCandidateRegistry(); qc_rows = []; seen = set()
        for index, row in enumerate(raw, 1):
            qc = {"raw_generation_id": f"RAW-{index:05d}", **row, "qc_status": "rejected", "rejection_reason": ""}
            if row.get("generation_error") or not row.get("raw_smiles"):
                qc["rejection_reason"] = row.get("generation_error") or "empty_structure"; qc_rows.append(qc); continue
            mol = Chem.MolFromSmiles(row["raw_smiles"])
            if mol is None:
                qc["rejection_reason"] = "rdkit_sanitization_failed"; qc_rows.append(qc); continue
            try:
                Chem.SanitizeMol(mol)
                parent = rdMolStandardize.FragmentParent(mol)
                canonical = Chem.MolToSmiles(parent, canonical=True, isomericSmiles=True)
                mol = Chem.MolFromSmiles(canonical)
            except Exception as error:
                qc["rejection_reason"] = f"standardization_failed:{type(error).__name__}"; qc_rows.append(qc); continue
            if canonical in parent_smiles:
                qc["rejection_reason"] = "parent_duplicate"; qc_rows.append(qc); continue
            if canonical in historical_smiles:
                qc["rejection_reason"] = "historical_htvs1633_duplicate"; qc_rows.append(qc); continue
            if canonical in seen:
                qc["rejection_reason"] = "generated_duplicate"; qc_rows.append(qc); continue
            seen.add(canonical)
            inchikey = Chem.MolToInchiKey(mol); scaffold = MurckoScaffold.MurckoScaffoldSmiles(mol=mol)
            candidate_id = "ATP-GEN-" + _hash_text(canonical)[:12].upper()
            parent_seed = next(seed for seed in seeds if seed["candidate_id"] == row["parent_candidate_id"])
            pains = [entry.GetDescription() for entry in catalog.GetMatches(mol)]
            mw = Descriptors.MolWt(mol); logp = Crippen.MolLogP(mol); tpsa = rdMolDescriptors.CalcTPSA(mol)
            warnings = []
            if pains: warnings.append("PAINS:" + "|".join(pains))
            if mw > 650: warnings.append("high_MW")
            if abs(Chem.GetFormalCharge(mol)) > 2: warnings.append("high_formal_charge")
            if logp > 6: warnings.append("high_cLogP")
            payload = {"parent_candidate_id": row["parent_candidate_id"], "parent_structure_hash": row["parent_structure_hash"],
                       "generation_method": row["generation_method"], "generator_version": row["generator_version"],
                       "generator_config": self.config["version"], "random_seed": self.config["random_seed"],
                       "reaction_or_operation": row["reaction_or_operation"], "reaction_smarts": row["reaction_smarts"],
                       "building_block_id": row["building_block_id"], "building_block_smiles": row["building_block_smiles"],
                       "attachment_atom_index": row["attachment_atom_index"], "canonical_smiles": canonical,
                       "inchikey": inchikey, "murcko_scaffold": scaffold}
            record = {"generated_candidate_id": candidate_id, **payload, "generation_timestamp": str(date.today()),
                      "provenance_hash": provenance_hash(payload), "parent_alias": parent_seed["historical_alias"],
                      "parent_source": parent_seed["source"], "parent_htvs_identity": parent_seed["htvs_identity"],
                      "MW": mw, "cLogP": logp, "TPSA": tpsa, "HBD": Lipinski.NumHDonors(mol),
                      "HBA": Lipinski.NumHAcceptors(mol), "rotatable_bonds": Lipinski.NumRotatableBonds(mol),
                      "formal_charge": Chem.GetFormalCharge(mol), "ring_count": rdMolDescriptors.CalcNumRings(mol),
                      "fractionCSP3": rdMolDescriptors.CalcFractionCSP3(mol), "pains_alerts": "|".join(pains),
                      "structural_warnings": ";".join(warnings), "warning_count": len(warnings),
                      "sa_like_proxy": _sa_like(mol), "scaffold_retention": scaffold == parent_seed["murcko_scaffold"]}
            registry.add(record)
            qc.update({"qc_status": "accepted", "rejection_reason": "", "generated_candidate_id": candidate_id,
                       "canonical_smiles": canonical, "warning_count": len(warnings)})
            qc_rows.append(qc)
        return registry.frame(), pd.DataFrame(qc_rows)

    def _chemical_space(self, registry: pd.DataFrame, seeds: list[dict]) -> tuple[pd.DataFrame, dict]:
        historical = pd.read_csv(self.project / "data/htvs_structures_v0_1.csv")
        hist_mols = [Chem.MolFromSmiles(value) for value in historical["canonical_smiles"]]
        hist_fps = [_fp(mol) for mol in hist_mols]
        hist_ids = historical["canonical_id"].astype(str).tolist()
        seed_map = {seed["candidate_id"]: seed for seed in seeds}
        gen_mols = [Chem.MolFromSmiles(value) for value in registry["canonical_smiles"]]
        gen_fps = [_fp(mol) for mol in gen_mols]
        rows = []
        for i, row in enumerate(registry.to_dict("records")):
            parent_fp = _fp(Chem.MolFromSmiles(seed_map[row["parent_candidate_id"]]["canonical_smiles"]))
            parent_similarity = DataStructs.TanimotoSimilarity(gen_fps[i], parent_fp)
            nearest, index = _similarity(gen_fps[i], hist_fps)
            other = [fp for j, fp in enumerate(gen_fps) if j != i]
            gen_nearest, _ = _similarity(gen_fps[i], other)
            rows.append({"generated_candidate_id": row["generated_candidate_id"],
                         "parent_candidate_id": row["parent_candidate_id"],
                         "parent_similarity": parent_similarity, "novelty_vs_parent": 1-parent_similarity,
                         "nearest_htvs1633_id": hist_ids[index], "nearest_neighbor_similarity": nearest,
                         "novelty_vs_htvs1633": 1-nearest, "nearest_generated_similarity": gen_nearest,
                         "internal_diversity_contribution": 1-gen_nearest,
                         "murcko_scaffold": row["murcko_scaffold"], "scaffold_retention": row["scaffold_retention"]})
        frame = pd.DataFrame(rows)
        pairwise = []
        for i in range(len(gen_fps)):
            pairwise.extend(DataStructs.BulkTanimotoSimilarity(gen_fps[i], gen_fps[i+1:]))
        metrics = {"validity": 1.0, "uniqueness": 1.0,
                   "mean_novelty_vs_parent": float(frame["novelty_vs_parent"].mean()),
                   "mean_novelty_vs_htvs1633": float(frame["novelty_vs_htvs1633"].mean()),
                   "mean_pairwise_similarity": float(np.mean(pairwise)) if pairwise else 1.0,
                   "internal_diversity": float(1-np.mean(pairwise)) if pairwise else 0.0,
                   "unique_scaffolds": int(frame["murcko_scaffold"].nunique()),
                   "scaffold_diversity": float(frame["murcko_scaffold"].nunique()/len(frame)),
                   "scaffold_retention": float(frame["scaffold_retention"].mean()),
                   "generator_collapse": bool((1-np.mean(pairwise) < .15) or (frame["nearest_generated_similarity"].ge(.95).mean() > .8))}
        return frame, metrics

    def _screen(self, registry: pd.DataFrame, space: pd.DataFrame) -> pd.DataFrame:
        frame = registry.merge(space, on=["generated_candidate_id", "parent_candidate_id", "murcko_scaffold", "scaffold_retention"])
        tractability = (1 - (frame["sa_like_proxy"]-1)/9).clip(0, 1)
        warning_free = 1/(1+frame["warning_count"])
        w = self.config["screening_weights"]
        frame["property_tractability"] = tractability
        frame["cheap_screening_score"] = (w["validity"] + w["tractability"]*tractability
            + w["novelty"]*frame["novelty_vs_htvs1633"] + w["diversity"]*frame["internal_diversity_contribution"]
            + w["scaffold_retention"]*frame["scaffold_retention"].astype(float) + w["warning_free"]*warning_free)
        # Preserve both seeds, then greedily favor score and structural diversity.
        selected = []
        for _, group in frame.groupby("parent_candidate_id"):
            selected.extend(group.nlargest(10, "cheap_screening_score")["generated_candidate_id"])
        selected = list(dict.fromkeys(selected))
        candidates = frame.sort_values("cheap_screening_score", ascending=False)
        fps = {row.generated_candidate_id: _fp(Chem.MolFromSmiles(row.canonical_smiles)) for row in frame.itertuples()}
        while len(selected) < min(self.config["vina_pool_size"], len(frame)):
            remaining = candidates.loc[~candidates["generated_candidate_id"].isin(selected)].head(300)
            best_id, best_value = None, -1.0
            chosen_fps = [fps[item] for item in selected]
            for row in remaining.itertuples():
                max_similarity = max(DataStructs.BulkTanimotoSimilarity(fps[row.generated_candidate_id], chosen_fps))
                value = 0.65*row.cheap_screening_score + 0.35*(1-max_similarity)
                if value > best_value:
                    best_id, best_value = row.generated_candidate_id, value
            selected.append(best_id)
        pool = frame.loc[frame["generated_candidate_id"].isin(selected)].copy()
        pool["screening_pool_rank"] = pool["cheap_screening_score"].rank(method="first", ascending=False).astype(int)
        return pool.sort_values("screening_pool_rank")

    def prepare(self) -> dict:
        self.output.mkdir(parents=True, exist_ok=True); self.runtime.mkdir(parents=True, exist_ok=True)
        caps = self._capabilities(); seeds = self._seeds(); generator = RDKitRGroupGenerator(self.config)
        raw = []
        for seed in seeds:
            raw.extend(generator.generate(seed, self.config["raw_target_per_seed"]))
        registry, qc = self._qc(raw, seeds)
        if len(registry) > self.config["max_unique_valid"]:
            raise ValueError("unique valid generation exceeds configured Phase 16 cap")
        space, metrics = self._chemical_space(registry, seeds)
        valid_mask = qc["qc_status"].eq("accepted") | qc["rejection_reason"].eq("generated_duplicate")
        valid_total = int(valid_mask.sum())
        metrics["validity"] = float(valid_total / len(raw)) if raw else 0.0
        metrics["uniqueness"] = float(len(registry) / valid_total) if valid_total else 0.0
        pool = self._screen(registry, space)
        _csv(registry, self.output / "generated_candidate_registry.csv")
        _csv(qc, self.output / "generation_qc.csv")
        lineage = registry[["parent_candidate_id", "generated_candidate_id", "generation_method", "reaction_or_operation",
                            "building_block_id", "attachment_atom_index", "provenance_hash"]].copy()
        lineage.insert(0, "lineage_depth", 1); _csv(lineage, self.output / "generation_lineage.csv")
        _csv(space, self.output / "generated_chemical_space.csv")
        _csv(pool, self.output / "generated_screening_pool.csv")
        benchmark_rows = []
        accepted_by_parent = registry.groupby("parent_candidate_id").size().to_dict()
        raw_by_parent = Counter(row["parent_candidate_id"] for row in raw)
        for seed in seeds:
            raw_count=raw_by_parent.get(seed["candidate_id"],0)
            valid_count=int((qc["parent_candidate_id"].eq(seed["candidate_id"]) & valid_mask).sum())
            unique_count=accepted_by_parent.get(seed["candidate_id"],0)
            benchmark_rows.append({"backend": "rdkit_rgroup_enumeration", "seed": seed["historical_alias"],
                "raw":raw_count,"valid":valid_count,"unique":unique_count,
                "validity":valid_count/raw_count if raw_count else np.nan,"uniqueness":unique_count/valid_count if valid_count else np.nan,
                "novelty_vs_htvs1633": float(space.loc[space["parent_candidate_id"].eq(seed["candidate_id"]),"novelty_vs_htvs1633"].mean()),
                "internal_diversity": metrics["internal_diversity"], "scaffold_diversity": metrics["scaffold_diversity"],
                "scaffold_retention": float(space.loc[space["parent_candidate_id"].eq(seed["candidate_id"]),"scaffold_retention"].mean()),
                "property_warning_rate": float(registry.loc[registry["parent_candidate_id"].eq(seed["candidate_id"]),"warning_count"].gt(0).mean()),
                "vina_execution_success": np.nan,"status":"available","reason":"real RDKit enumeration"})
        for name in ["crem", "reinvent4_shadow"]:
            status = next(row for row in caps["backends"] if row["generator_id"] == name)
            benchmark_rows.append({"backend": name, "seed": "not_run", "raw": 0, "valid": 0, "unique": 0,
                "validity":np.nan,"uniqueness":np.nan,"novelty_vs_htvs1633": np.nan, "internal_diversity": np.nan, "scaffold_diversity": np.nan,
                "scaffold_retention": np.nan, "property_warning_rate": np.nan, "vina_execution_success": np.nan,
                "status": status["status"], "reason": status["reason"]})
        _csv(pd.DataFrame(benchmark_rows), self.output / "generator_benchmark.csv")
        summary = {"raw": len(raw), "valid_unique": len(registry), "rejected": int(qc["qc_status"].eq("rejected").sum()),
                   "historical_duplicates": int(qc["rejection_reason"].eq("historical_htvs1633_duplicate").sum()),
                   "screening_pool": len(pool), "metrics": metrics, "seeds": seeds, "backends": caps,
                   "training": False}
        write_json(self.output / "generation_prepare_summary.json", summary)
        return summary

    def vina(self, workers: int | None = None) -> dict:
        pool = pd.read_csv(self.output / "generated_screening_pool.csv")
        protocol = json.loads((self.project / "configs/projects/ab_atp_synthase/vina_7p3w_v1/vina_protocol.json").read_text())
        receptor = self.project / "workspace_local/artifacts/e5e92ede1b1d000b00a7e5dbe3f3b02f0df0cd63b47dd8a421eeb8bddb1083ed/receptor.pdbqt"
        vina = self.project / "workspace_local/tools/vina-1.2.7/vina_1.2.7_win.exe"
        if file_hash(receptor) != "e5e92ede1b1d000b00a7e5dbe3f3b02f0df0cd63b47dd8a421eeb8bddb1083ed": raise ValueError("receptor hash changed")
        if file_hash(vina) != "e0c4b2715e0c1a74f6e92d0f3be0328ac97542eafbc111e6b1efad897a73cce5": raise ValueError("Vina hash changed")
        protocol_hash = digest(protocol); tasks=[]
        for row in pool.to_dict("records"):
            structure_hash = _hash_text(row["canonical_smiles"])
            signature = _sha_text({"generated_candidate_id":row["generated_candidate_id"],"structure_hash":structure_hash,
                                   "protocol_hash":protocol_hash,"tool_hash":file_hash(vina),"receptor_hash":file_hash(receptor)})
            folder = self.runtime / "jobs" / signature[:2] / signature
            tasks.append({"compound_id":row["generated_candidate_id"],"smiles":row["canonical_smiles"],"signature":signature,
                          "folder":str(folder),"protocol":protocol,"vina":str(vina),"receptor":str(receptor),
                          "timeout":1800,"retry_failed":False,"attempt":1})
        results=[]; pending=[]
        for task in tasks:
            cached=_existing_result(task)
            (results if cached else pending).append(cached or task)
        max_workers = min(int(workers or self.config["vina_max_workers"]), 12)
        for start in range(0,len(pending),20):
            batch=pending[start:start+20]
            with concurrent.futures.ProcessPoolExecutor(max_workers=max_workers) as pool_executor:
                batch_results=list(pool_executor.map(_worker,batch))
            for item in batch_results: item["folder"]=next(t["folder"] for t in batch if t["compound_id"]==item["compound_id"])
            results.extend(batch_results)
            _csv(pd.DataFrame(results), self.output / "generated_vina_checkpoint.csv")
        by_id={r["compound_id"]:r for r in results}
        rows=[]; pose_folder=self.output/"poses"; pose_folder.mkdir(parents=True,exist_ok=True)
        for task in tasks:
            result=by_id.get(task["compound_id"])
            if result is None:
                path=Path(task["folder"])/"result.json"
                if path.is_file(): result=json.loads(path.read_text())
            if result is None: continue
            exported_pose=""
            if result.get("status")=="success":
                source_pose=Path(result.get("folder",task["folder"]))/"pose.pdbqt"
                target_pose=pose_folder/f"{result['compound_id']}_vina_7p3w_v1.pdbqt"
                shutil.copyfile(source_pose,target_pose)
                if file_hash(target_pose)!=result.get("pose_sha256"): raise ValueError("exported generated pose hash mismatch")
                exported_pose=str(target_pose.relative_to(self.project))
            rows.append({"generated_candidate_id":result["compound_id"],"status":result["status"],
                "vina_affinity":result.get("vina_affinity"),"pose_qc":result.get("pose_qc"),"pose_count":result.get("pose_count"),
                "failure_category":result.get("failure_category",""),"failure_reason":result.get("failure_reason",""),
                "protocol_id":"vina_7p3w_v1","protocol_hash":protocol_hash,"receptor_hash":file_hash(receptor),
                "tool_hash":file_hash(vina),"ligand_hash":result.get("ligand_sha256"),"pose_hash":result.get("pose_sha256"),
                "job_signature":result["signature"],"cached":result.get("cached",False),"pose_path":exported_pose,
                "job_folder":result.get("folder",task["folder"])})
        frame=pd.DataFrame(rows); _csv(frame,self.output/"generated_vina_results.csv")
        summary={"total":len(tasks),"success":int(frame["status"].eq("success").sum()),"failed":int(frame["status"].eq("failed").sum()),
                 "workers":max_workers,"protocol_id":"vina_7p3w_v1","protocol_hash":protocol_hash,"receptor_hash":file_hash(receptor),
                 "tool_hash":file_hash(vina),"historical_registry_mixed":False}
        write_json(self.output/"generated_vina_summary.json",summary); return summary

    def finalize(self) -> dict:
        registry=pd.read_csv(self.output/"generated_candidate_registry.csv"); space=pd.read_csv(self.output/"generated_chemical_space.csv")
        pool=pd.read_csv(self.output/"generated_screening_pool.csv"); vina=pd.read_csv(self.output/"generated_vina_results.csv")
        frame=pool.merge(vina,on="generated_candidate_id",how="left")
        success=frame.loc[frame["status"].eq("success")].copy()
        success["vina_rank_within_generated_pool"]=success["vina_affinity"].rank(method="min",ascending=True).astype(int)
        success["vina_component"]=1-(success["vina_rank_within_generated_pool"]-1)/max(len(success)-1,1)
        warning_free=1/(1+success["warning_count"]); w=self.config["acquisition_weights"]
        success["generated_candidate_score"]=(w["vina"]*success["vina_component"]+w["tractability"]*success["property_tractability"]
            +w["novelty"]*success["novelty_vs_htvs1633"]+w["diversity"]*success["internal_diversity_contribution"]
            +w["warning_free"]*warning_free+w["scaffold_retention"]*success["scaffold_retention"].astype(float))
        parent_results=json.loads((self.project/"results/phase13/validation_5_results.json").read_text())
        success["parent_vina_affinity"]=success["parent_candidate_id"].map({k:v["affinity"] for k,v in parent_results.items()})
        success["vina_delta_vs_parent"]=success["vina_affinity"]-success["parent_vina_affinity"]
        success["acquisition_priority"]=success["generated_candidate_score"].rank(method="first",ascending=False).astype(int)
        panel=success.nsmallest(self.config["acquisition_panel_size"],"acquisition_priority").copy()
        panel["recommended_next_evidence"]="reviewed same-protocol MM/GBSA"
        panel["interpretation"]="generated-pool evidence priority; not biological activity"
        _csv(panel,self.output/"generated_acquisition_panel_v1.csv")
        benchmark=pd.read_csv(self.output/"generator_benchmark.csv")
        mask=benchmark["backend"].eq("rdkit_rgroup_enumeration")
        benchmark.loc[mask,"vina_execution_success"]=float(vina["status"].eq("success").mean())
        _csv(benchmark,self.output/"generator_benchmark.csv")
        aizynth_detected=bool(shutil.which("aizynthcli") or importlib.util.find_spec("aizynthfinder"))
        aizynth_config=os.environ.get("AIZYNTHFINDER_CONFIG","")
        if not aizynth_detected:
            aizynth={"status":"unavailable","reason":"executable_and_python_module_not_found","retrosynthesis_runs":0}
        elif not aizynth_config or not Path(aizynth_config).is_file():
            aizynth={"status":"configuration_missing","reason":"model_stock_configuration_missing","retrosynthesis_runs":0}
        else:
            aizynth={"status":"configuration_missing","reason":"environment_detected_but_retrosynthesis_protocol_not_reviewed","retrosynthesis_runs":0}
        synthesis={"aizynthfinder":aizynth,"sa_like_proxy":"calculated for all valid generated candidates",
                    "scope":"tractability heuristic; not synthesis feasibility proof","blocking":False}
        write_json(self.output/"synthesis_feasibility_status.json",synthesis)
        self._plots(registry,space,vina,benchmark)
        prepare=json.loads((self.output/"generation_prepare_summary.json").read_text())
        summary={"phase":"Phase 16","raw":prepare["raw"],"valid_unique":prepare["valid_unique"],
                 "historical_duplicates":prepare["historical_duplicates"],"chemical_space":prepare["metrics"],
                 "vina":json.loads((self.output/"generated_vina_summary.json").read_text()),"acquisition_panel":len(panel),
                 "synthesis":synthesis,"training":False,"biological_activity_claim":False}
        write_json(self.output/"phase16_summary.json",summary); return summary

    def _plots(self,registry,space,vina,benchmark):
        folder=self.output/"figures";folder.mkdir(parents=True,exist_ok=True)
        def save(name,title,xlabel,values,bins=25):
            plt.figure(figsize=(6,4));plt.hist(values,bins=bins);plt.title(title);plt.xlabel(xlabel);plt.ylabel("Count");plt.tight_layout();plt.savefig(folder/name,dpi=180);plt.close()
        save("parent_generated_similarity.png","Generated-parent similarity","Tanimoto",space["parent_similarity"])
        save("historical_similarity_distribution.png","Nearest HTVS-1633 similarity","Tanimoto",space["nearest_neighbor_similarity"])
        save("vina_distribution.png","Generated-pool Vina distribution","Vina affinity (kcal/mol)",vina.loc[vina["status"].eq("success"),"vina_affinity"])
        counts=registry["murcko_scaffold"].value_counts().head(20);plt.figure(figsize=(8,4));counts.plot.bar();plt.title("Generated scaffold distribution");plt.tight_layout();plt.savefig(folder/"scaffold_distribution.png",dpi=180);plt.close()
        funnel=[len(pd.read_csv(self.output/"generation_qc.csv")),len(registry),len(pd.read_csv(self.output/"generated_screening_pool.csv")),int(vina["status"].eq("success").sum()),self.config["acquisition_panel_size"]]
        plt.figure(figsize=(7,4));plt.bar(["raw","valid unique","Vina pool","Vina success","acquisition"],funnel);plt.title("Generation funnel");plt.tight_layout();plt.savefig(folder/"generation_funnel.png",dpi=180);plt.close()
        available=benchmark.loc[benchmark["raw"].gt(0)];plt.figure(figsize=(6,4));plt.bar(available["seed"],available["unique"]);plt.title("Generator comparison (real backend only)");plt.ylabel("Unique valid");plt.tight_layout();plt.savefig(folder/"generator_comparison.png",dpi=180);plt.close()
