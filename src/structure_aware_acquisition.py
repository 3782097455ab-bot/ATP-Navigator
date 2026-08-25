"""Refine the Phase 8 acquisition queue using extracted molecular structures.

The v1 descriptor-only queue remains untouched. This script creates a v2 queue
with exploitation, local chemical-space bridge, and scaffold exploration arms.
No activity or MM/GBSA value is inferred and no model is trained.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import tempfile
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from rdkit import Chem, DataStructs, rdBase
from rdkit.Chem import rdFingerprintGenerator


rdBase.DisableLog("rdApp.warning")
RADIUS = 2
FP_SIZE = 2048
ARM_COUNT = 20
WAVE1_PER_ARM = 8


def json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def atomic_csv(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8-sig", newline="", delete=False, dir=path.parent, suffix=".tmp"
    ) as handle:
        frame.to_csv(handle, index=False)
        temporary = Path(handle.name)
    temporary.replace(path)


def atomic_json(payload: Any, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", delete=False, dir=path.parent, suffix=".tmp"
    ) as handle:
        json.dump(json_safe(payload), handle, ensure_ascii=False, indent=2, allow_nan=False)
        temporary = Path(handle.name)
    temporary.replace(path)


def atomic_text(text: str, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", delete=False, dir=path.parent, suffix=".tmp"
    ) as handle:
        handle.write(text)
        temporary = Path(handle.name)
    temporary.replace(path)


def fingerprints(smiles: pd.Series) -> tuple[list[Chem.Mol], list[DataStructs.ExplicitBitVect]]:
    generator = rdFingerprintGenerator.GetMorganGenerator(radius=RADIUS, fpSize=FP_SIZE)
    molecules = [Chem.MolFromSmiles(value) for value in smiles.astype(str)]
    if any(mol is None for mol in molecules):
        raise ValueError("Invalid SMILES in structure-aware acquisition input")
    return molecules, [generator.GetFingerprint(mol) for mol in molecules]


def max_similarity(
    query_fps: list[DataStructs.ExplicitBitVect],
    reference_fps: list[DataStructs.ExplicitBitVect],
) -> tuple[np.ndarray, np.ndarray]:
    values = []
    indices = []
    for fp in query_fps:
        similarities = DataStructs.BulkTanimotoSimilarity(fp, reference_fps)
        index = int(np.argmax(similarities))
        values.append(float(similarities[index]))
        indices.append(index)
    return np.asarray(values), np.asarray(indices)


def unique_scaffold_top(frame: pd.DataFrame, count: int) -> pd.DataFrame:
    selected = []
    used_scaffolds: set[str] = set()
    for row in frame.itertuples(index=False):
        if row.scaffold in used_scaffolds:
            continue
        selected.append(row.canonical_id)
        used_scaffolds.add(row.scaffold)
        if len(selected) == count:
            break
    if len(selected) < count:
        for identifier in frame["canonical_id"]:
            if identifier not in selected:
                selected.append(identifier)
            if len(selected) == count:
                break
    return frame.set_index("canonical_id").loc[selected].reset_index()


def choose_exploration(
    remaining: pd.DataFrame,
    fp_map: dict[str, DataStructs.ExplicitBitVect],
    seed_fps: list[DataStructs.ExplicitBitVect],
    seed_scaffolds: set[str],
) -> pd.DataFrame:
    working = remaining.copy()
    working["docking_decile"] = pd.qcut(
        working["glide_docking_score"], q=10, labels=False, duplicates="drop"
    )
    selected_ids: list[str] = []
    selected_fps = list(seed_fps)
    selected_scaffolds = set(seed_scaffolds)
    for round_number in range(2):
        for decile in sorted(working["docking_decile"].dropna().unique()):
            candidates = working.loc[
                working["docking_decile"].eq(decile)
                & ~working["canonical_id"].isin(selected_ids)
            ].copy()
            unseen = candidates.loc[~candidates["scaffold"].isin(selected_scaffolds)]
            if not unseen.empty:
                candidates = unseen
            distances = []
            for identifier in candidates["canonical_id"]:
                maximum = max(DataStructs.BulkTanimotoSimilarity(fp_map[identifier], selected_fps))
                distances.append(1.0 - maximum)
            candidates["min_distance_to_selected"] = distances
            picked = candidates.sort_values(
                ["min_distance_to_selected", "exploitation_score", "canonical_id"],
                ascending=[False, False, True],
            ).iloc[0]
            selected_ids.append(picked["canonical_id"])
            selected_fps.append(fp_map[picked["canonical_id"]])
            selected_scaffolds.add(picked["scaffold"])
    return working.set_index("canonical_id").loc[selected_ids[:ARM_COUNT]].reset_index()


def select_v2(project_root: Path) -> tuple[pd.DataFrame, dict[str, Any]]:
    pool = pd.read_csv(project_root / "results/phase8_data_acquisition/htvs_pool_audit.csv")
    structures = pd.read_csv(project_root / "data/htvs_structures_v0_1.csv")
    internal = pd.read_csv(project_root / "data/model_v3/training_table.csv")
    pool["selection_eligible"] = pool["selection_eligible"].astype(str).str.lower().eq("true")
    pool["known_internal_overlap"] = pool["known_internal_overlap"].astype(str).str.lower().eq("true")
    structure_columns = [
        "canonical_id",
        "canonical_smiles",
        "scaffold",
        "molecular_formula",
        "formal_charge",
        "heavy_atom_count",
        "smiles_sha256",
    ]
    frame = pool.drop(columns=[column for column in structure_columns[1:] if column in pool.columns]).merge(
        structures[structure_columns], on="canonical_id", how="inner", validate="one_to_one"
    )
    frame = frame.loc[frame["selection_eligible"] & ~frame["known_internal_overlap"]].copy()

    _, fps = fingerprints(frame["canonical_smiles"])
    _, internal_fps = fingerprints(internal["canonical_smiles"])
    fp_map = dict(zip(frame["canonical_id"], fps))
    similarities, nearest_indices = max_similarity(fps, internal_fps)
    frame["max_similarity_to_internal"] = similarities
    frame["nearest_internal_compound_id"] = [internal.iloc[index]["compound_id"] for index in nearest_indices]
    internal_scaffolds = set(internal["scaffold"].astype(str))
    frame["scaffold_seen_in_internal"] = frame["scaffold"].astype(str).isin(internal_scaffolds)

    exploitation = frame.sort_values(
        ["exploitation_score", "glide_docking_score", "canonical_id"],
        ascending=[False, True, True],
    ).head(ARM_COUNT)
    exploitation_ids = set(exploitation["canonical_id"])

    bridge_candidates = frame.loc[~frame["canonical_id"].isin(exploitation_ids)].sort_values(
        ["max_similarity_to_internal", "exploitation_score", "canonical_id"],
        ascending=[False, False, True],
    )
    bridge = unique_scaffold_top(bridge_candidates, ARM_COUNT)
    bridge_ids = set(bridge["canonical_id"])

    remaining = frame.loc[
        ~frame["canonical_id"].isin(exploitation_ids | bridge_ids)
    ].copy()
    selected_seed_ids = list(exploitation["canonical_id"]) + list(bridge["canonical_id"])
    exploration = choose_exploration(
        remaining,
        fp_map,
        [*internal_fps, *[fp_map[value] for value in selected_seed_ids]],
        internal_scaffolds | set(exploitation["scaffold"]) | set(bridge["scaffold"]),
    )

    arms = []
    for name, objective, selected in [
        (
            "exploitation",
            "test whether strongest HTVS multi-score candidates retain favorable same-protocol MMGBSA",
            exploitation,
        ),
        (
            "local_structure_bridge",
            "connect the existing 17-candidate chemical series to nearby HTVS structures across distinct scaffolds",
            bridge,
        ),
        (
            "scaffold_score_exploration",
            "cover unseen scaffolds across docking-score deciles to reduce selection bias",
            exploration,
        ),
    ]:
        arm = selected.copy().reset_index(drop=True)
        arm["selection_arm_v2"] = name
        arm["selection_objective_v2"] = objective
        arm["arm_rank_v2"] = np.arange(1, len(arm) + 1)
        arm["wave_v2"] = np.where(arm["arm_rank_v2"].le(WAVE1_PER_ARM), 1, 2)
        arm["priority_v2"] = np.where(arm["wave_v2"].eq(1), "P0", "P1")
        arms.append(arm)
    queue = pd.concat(arms, ignore_index=True)
    order = {"exploitation": 0, "local_structure_bridge": 1, "scaffold_score_exploration": 2}
    queue["_arm_order"] = queue["selection_arm_v2"].map(order)
    queue = queue.sort_values(["wave_v2", "arm_rank_v2", "_arm_order"]).reset_index(drop=True)
    queue["acquisition_order_v2"] = np.arange(1, len(queue) + 1)
    queue["acquisition_id_v2"] = queue["acquisition_order_v2"].map(
        lambda value: f"ATP-ACQ2-{value:04d}"
    )
    queue["structure_status_v2"] = "extracted_and_rdkit_validated"
    queue["mmgbsa_label_status"] = "pending"
    queue["experimental_activity_status"] = "unknown"
    queue["next_required_action"] = "run frozen same-protocol MMGBSA using the supplied 3D Maestro-derived SDF pose"
    # Retain Phase 8.1 provenance without letting its pre-extraction status be
    # mistaken for the current, structure-validated state of the v2 queue.
    queue = queue.rename(
        columns={
            "acquisition_id": "phase8_v1_acquisition_id",
            "priority": "phase8_v1_priority",
            "wave": "phase8_v1_wave",
            "selection_arm": "phase8_v1_selection_arm",
            "structure_status": "phase8_v1_structure_status",
            "selected_for_phase8": "selected_in_phase8_v1",
        }
    )
    queue = queue.drop(columns=["_arm_order"], errors="ignore")

    old = pd.read_csv(project_root / "results/phase8_data_acquisition/mmgbsa_acquisition_queue.csv")
    old_ids = set(old["canonical_id"])
    new_ids = set(queue["canonical_id"])
    summary = {
        "eligible_structures": int(len(frame)),
        "internal_reference_structures": int(len(internal)),
        "queue_size": int(len(queue)),
        "queue_scaffolds": int(queue["scaffold"].nunique()),
        "p0_scaffolds": int(queue.loc[queue["wave_v2"].eq(1), "scaffold"].nunique()),
        "scaffolds_seen_in_internal": int(queue["scaffold_seen_in_internal"].sum()),
        "v1_v2_compound_overlap": int(len(old_ids & new_ids)),
        "v2_new_compounds": int(len(new_ids - old_ids)),
        "max_similarity_internal_min": float(queue["max_similarity_to_internal"].min()),
        "max_similarity_internal_median": float(queue["max_similarity_to_internal"].median()),
        "max_similarity_internal_max": float(queue["max_similarity_to_internal"].max()),
        "bridge_similarity_median": float(
            queue.loc[queue["selection_arm_v2"].eq("local_structure_bridge"), "max_similarity_to_internal"].median()
        ),
        "exploration_similarity_median": float(
            queue.loc[queue["selection_arm_v2"].eq("scaffold_score_exploration"), "max_similarity_to_internal"].median()
        ),
    }
    return queue, summary


def sdf_map(path: Path) -> dict[str, Chem.Mol]:
    result = {}
    supplier = Chem.SDMolSupplier(str(path), sanitize=True, removeHs=False)
    for mol in supplier:
        if mol is None:
            continue
        identifier = mol.GetProp("canonical_id") if mol.HasProp("canonical_id") else mol.GetProp("_Name")
        result[identifier] = Chem.Mol(mol)
    return result


def atomic_selected_sdf(queue: pd.DataFrame, molecule_map: dict[str, Chem.Mol], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    writer = Chem.SDWriter(str(temporary))
    try:
        for row in queue.itertuples(index=False):
            mol = Chem.Mol(molecule_map[row.canonical_id])
            mol.SetProp("_Name", row.acquisition_id_v2)
            for column in [
                "acquisition_id_v2",
                "canonical_id",
                "compound_code",
                "title",
                "variant",
                "selection_arm_v2",
                "priority_v2",
                "canonical_smiles",
                "scaffold",
            ]:
                mol.SetProp(column, str(getattr(row, column)))
            writer.write(mol)
    finally:
        writer.close()
    temporary.replace(path)


def return_template(queue: pd.DataFrame) -> pd.DataFrame:
    result = queue[
        [
            "acquisition_id_v2",
            "canonical_id",
            "compound_code",
            "title",
            "variant",
            "canonical_smiles",
            "scaffold",
            "priority_v2",
            "wave_v2",
            "selection_arm_v2",
            "source_file",
        ]
    ].copy()
    result["structure_collection_file"] = "results/phase8_data_acquisition/selected_structures_v0_2.sdf"
    result["structure_record_name"] = result["acquisition_id_v2"]
    for column in [
        "structure_qc_status",
        "mmgbsa_protocol_id",
        "protein_structure_id",
        "software_version",
        "mmgbsa_dg_bind_kcal_mol",
        "calculation_status",
        "calculation_date",
        "operator",
        "notes",
    ]:
        result[column] = ""
    return result


def comparison(project_root: Path, queue: pd.DataFrame) -> pd.DataFrame:
    old = pd.read_csv(project_root / "results/phase8_data_acquisition/mmgbsa_acquisition_queue.csv")
    old_structure = pd.read_csv(project_root / "data/htvs_structures_v0_1.csv")[["canonical_id", "scaffold"]]
    old = old.merge(old_structure, on="canonical_id", how="left", validate="one_to_one")
    return pd.DataFrame(
        [
            {
                "queue_version": "v1_descriptor_only",
                "candidates": len(old),
                "unique_scaffolds": old["scaffold"].nunique(),
                "selection_basis": "Docking/QuickProp only; no structures available at creation time",
                "recommended_status": "preserved_audit_baseline",
            },
            {
                "queue_version": "v2_structure_aware",
                "candidates": len(queue),
                "unique_scaffolds": queue["scaffold"].nunique(),
                "selection_basis": "Morgan2048 + scaffold + Docking score + internal-17 bridge",
                "recommended_status": "current_recommended_queue",
            },
        ]
    )


def report(summary: dict[str, Any]) -> str:
    return f"""# Phase 8 Structure-aware Acquisition Report

日期：2026-08-25  
状态：v2数据获取队列已建立；未训练或修改模型

## 为什么重做队列

v1建立时HTVS结构尚未提取，只能用Docking/QuickProp连续特征近似多样性。现在1,633个compound均已有RDKit canonical SMILES、Morgan fingerprint和scaffold，因此保留v1作审计对照，新增v2作为当前推荐队列。

## v2三臂设计

1. `exploitation` 20个：保持多评分最优候选；
2. `local_structure_bridge` 20个：选择与内部17候选最接近、同时尽量不同scaffold的结构，修复v4-alpha的化学空间断层；
3. `scaffold_score_exploration` 20个：在10个Docking分位层各取2个结构远离已选集合的scaffold，提供中弱分数和结构负对照。

P0仍为24个，每臂8个；P1为36个，每臂12个。

## 实际结果

- v2候选：{summary['queue_size']}；unique scaffolds：{summary['queue_scaffolds']}；P0 scaffolds：{summary['p0_scaffolds']}；
- v1/v2重叠：{summary['v1_v2_compound_overlap']}；v2新增候选：{summary['v2_new_compounds']}；
- v2到内部17候选最大Morgan相似度中位数：{summary['max_similarity_internal_median']:.3f}；
- bridge臂相似度中位数：{summary['bridge_similarity_median']:.3f}；
- exploration臂相似度中位数：{summary['exploration_similarity_median']:.3f}。

## 当前推荐执行

使用`mmgbsa_acquisition_queue_v2.csv`和`p0_structures_v0_2.sdf`运行首批24个同协议MM/GBSA。v1文件不删除、不覆盖，但不再作为首选执行队列。

## 边界

- Morgan/scaffold只用于数据获取设计，不是活性标签；
- SDF来自原始Docking pose，不代表已完成新的MM/GBSA；
- 所有返回模板中的MM/GBSA值仍为空；
- 下一轮模型训练必须等待P0真实计算结果和protocol QC。
"""


def run(project_root: Path) -> dict[str, Any]:
    project_root = project_root.resolve()
    results_dir = project_root / "results/phase8_data_acquisition"
    queue, summary = select_v2(project_root)
    molecule_map = sdf_map(project_root / "data/htvs_best_pose_structures_v0_1.sdf")
    if not set(queue["canonical_id"]).issubset(molecule_map):
        raise ValueError("Missing 3D structures for v2 queue")
    atomic_csv(queue, results_dir / "mmgbsa_acquisition_queue_v2.csv")
    atomic_selected_sdf(queue, molecule_map, results_dir / "selected_structures_v0_2.sdf")
    atomic_selected_sdf(
        queue.loc[queue["wave_v2"].eq(1)],
        molecule_map,
        results_dir / "p0_structures_v0_2.sdf",
    )
    atomic_csv(return_template(queue), project_root / "data/templates/phase8_mmgbsa_return_template_v2.csv")
    atomic_csv(comparison(project_root, queue), results_dir / "queue_v1_v2_comparison.csv")
    summary.update(
        {
            "phase": "Phase 8.2 Structure-aware Acquisition",
            "model_change": "none",
            "fingerprint": {"type": "Morgan", "radius": RADIUS, "bits": FP_SIZE},
            "labels_created": 0,
            "recommended_queue": "results/phase8_data_acquisition/mmgbsa_acquisition_queue_v2.csv",
        }
    )
    atomic_json(summary, results_dir / "structure_aware_acquisition_summary.json")
    atomic_text(report(summary), project_root / "docs/Phase8_Structure_Aware_Acquisition_Report.md")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    print(json.dumps(json_safe(run(args.project_root)), ensure_ascii=False, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
