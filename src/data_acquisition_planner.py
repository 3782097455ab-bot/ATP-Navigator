"""ATP-Navigator Phase 8: data acquisition intelligence.

This module does not train or modify any model. It converts the traceable HTVS
pose table into a reproducible queue for structure export and same-protocol
MM/GBSA calculation. Missing structures and experimental values remain blank.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import tempfile
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.preprocessing import RobustScaler


RANDOM_SEED = 42
EXPLOITATION_COUNT = 20
DIVERSITY_COUNT = 20
CALIBRATION_COUNT = 20
WAVE1_PER_ARM = 8

TRACE_COLUMNS = [
    "canonical_id",
    "compound_code",
    "title",
    "variant",
    "pose_index",
    "source_file",
]

SELECTION_FEATURES = [
    "glide_docking_score",
    "glide_emodel",
    "glide_energy",
    "glide_evdw",
    "glide_ecoul",
    "glide_ligand_efficiency",
    "glide_ligand_efficiency_sa",
    "glide_ligand_efficiency_ln",
    "quickprop_mol_mw",
    "quickprop_psa",
    "quickprop_qplogpo_w",
    "quickprop_qplogs",
    "quickprop_qplogherg",
    "quickprop_percenthumanoralabsorption",
    "quickprop_qppcaco",
    "quickprop_qppmdck",
    "quickprop_accpthb",
    "quickprop_donorhb",
    "quickprop_rotor",
    "quickprop_stars",
]


def json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, Path):
        return str(value)
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


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def numeric(frame: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    result = frame.copy()
    for column in columns:
        result[column] = pd.to_numeric(result[column], errors="coerce")
    return result


def best_pose_pool(docking: pd.DataFrame, project_root: Path) -> pd.DataFrame:
    numeric_columns = [column for column in docking.columns if column.startswith(("glide_", "quickprop_"))]
    docking = numeric(docking, numeric_columns)
    docking["pose_index"] = pd.to_numeric(docking["pose_index"], errors="coerce").astype("Int64")
    docking = docking.loc[docking["canonical_id"].fillna("").astype(str).str.len().gt(0)].copy()
    docking["_best_order"] = docking["glide_docking_score"].fillna(np.inf)
    docking = docking.sort_values(
        ["canonical_id", "_best_order", "glide_emodel", "pose_index"],
        na_position="last",
        kind="stable",
    )
    best = docking.groupby("canonical_id", as_index=False).first()
    counts = docking.groupby("canonical_id", as_index=False).agg(
        pose_count=("pose_index", "size"),
        variant_count=("variant", "nunique"),
        source_file_count=("source_file", "nunique"),
    )
    best = best.drop(columns=["_best_order"]).merge(counts, on="canonical_id", validate="one_to_one")
    workspace = project_root.parent
    best["source_file_exists"] = best["source_file"].map(
        lambda value: bool(value) and (workspace / str(value)).exists()
    )
    return best


def known_internal_tokens(project_root: Path) -> tuple[set[str], set[str]]:
    internal = pd.read_csv(project_root / "data/model_v3/training_table.csv")
    mapping = pd.read_csv(project_root / "data/compound_mapping_v1.csv")
    internal_ids = set(internal["compound_id"].astype(str))
    aliases = mapping.loc[mapping["canonical_id"].astype(str).isin(internal_ids), "original_name"]
    tokens = set(aliases.dropna().astype(str).str.strip()) | internal_ids
    return internal_ids, tokens


def annotate_pool(pool: pd.DataFrame, project_root: Path) -> pd.DataFrame:
    _, known_tokens = known_internal_tokens(project_root)
    molecules = pd.read_csv(project_root / "data/molecules.csv")
    smiles_map = molecules.set_index("canonical_id")["smiles"].fillna("").to_dict()
    pool = pool.copy()
    identity_fields = ["canonical_id", "compound_code", "title", "variant"]
    pool["known_internal_overlap"] = pool[identity_fields].astype(str).apply(
        lambda row: any(value.strip() in known_tokens for value in row), axis=1
    )
    pool["smiles"] = pool["canonical_id"].map(smiles_map).fillna("")
    pool["structure_status"] = np.where(
        pool["smiles"].astype(str).str.len().gt(0),
        "smiles_available",
        "pending_export_from_source_pose",
    )
    feature_columns = [column for column in SELECTION_FEATURES if column in pool.columns]
    pool["feature_completeness"] = pool[feature_columns].notna().mean(axis=1)
    pool["trace_complete"] = pool[TRACE_COLUMNS].notna().all(axis=1) & pool["source_file_exists"]
    pool["selection_eligible"] = (
        ~pool["known_internal_overlap"]
        & pool["trace_complete"]
        & pool["glide_docking_score"].notna()
        & pool["glide_emodel"].notna()
        & pool["glide_ligand_efficiency"].notna()
        & pool["feature_completeness"].ge(0.90)
    )
    pool["docking_priority"] = pool["glide_docking_score"].rank(ascending=False, pct=True)
    pool["emodel_priority"] = pool["glide_emodel"].rank(ascending=False, pct=True)
    pool["ligand_efficiency_priority"] = pool["glide_ligand_efficiency"].rank(
        ascending=False, pct=True
    )
    pool["exploitation_score"] = (
        0.50 * pool["docking_priority"]
        + 0.30 * pool["emodel_priority"]
        + 0.20 * pool["ligand_efficiency_priority"]
    )
    return pool


def scaled_feature_matrix(pool: pd.DataFrame) -> tuple[np.ndarray, list[str]]:
    columns = [column for column in SELECTION_FEATURES if column in pool.columns]
    x = pool[columns].astype(float).copy()
    x = x.fillna(x.median(numeric_only=True))
    scaled = RobustScaler(quantile_range=(10.0, 90.0)).fit_transform(x)
    scaled = np.clip(scaled, -5.0, 5.0)
    return scaled, columns


def greedy_maximin(matrix: np.ndarray, candidate_indices: list[int], seed_indices: list[int], count: int) -> list[int]:
    available = list(candidate_indices)
    selected = list(seed_indices)
    chosen: list[int] = []
    while available and len(chosen) < count:
        reference = matrix[selected] if selected else matrix[available[:1]]
        distances = []
        for index in available:
            squared = np.sum((reference - matrix[index]) ** 2, axis=1)
            distances.append(float(np.sqrt(np.min(squared))))
        best_position = int(np.argmax(distances))
        picked = available.pop(best_position)
        chosen.append(picked)
        selected.append(picked)
    return chosen


def select_queue(pool: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    eligible = pool.loc[pool["selection_eligible"]].copy()
    if len(eligible) < EXPLOITATION_COUNT + DIVERSITY_COUNT + CALIBRATION_COUNT:
        raise ValueError(f"Only {len(eligible)} eligible compounds; at least 60 are required")

    exploitation = eligible.sort_values(
        ["exploitation_score", "glide_docking_score", "canonical_id"],
        ascending=[False, True, True],
        kind="stable",
    ).head(EXPLOITATION_COUNT)
    exploitation_ids = set(exploitation["canonical_id"])

    matrix, diversity_features = scaled_feature_matrix(pool)
    index_by_id = {identifier: idx for idx, identifier in enumerate(pool["canonical_id"])}
    eligible_indices = [index_by_id[value] for value in eligible["canonical_id"] if value not in exploitation_ids]
    seed_indices = [index_by_id[value] for value in exploitation["canonical_id"]]
    diversity_indices = greedy_maximin(matrix, eligible_indices, seed_indices, DIVERSITY_COUNT)
    diversity = pool.iloc[diversity_indices].copy()
    diversity_ids = set(diversity["canonical_id"])

    remaining = eligible.loc[
        ~eligible["canonical_id"].isin(exploitation_ids | diversity_ids)
    ].copy()
    remaining["docking_decile"] = pd.qcut(
        remaining["glide_docking_score"], q=10, labels=False, duplicates="drop"
    )
    calibration_parts = []
    for decile in sorted(remaining["docking_decile"].dropna().unique()):
        group = remaining.loc[remaining["docking_decile"].eq(decile)].copy()
        median = group["glide_docking_score"].median()
        group["distance_to_decile_median"] = (group["glide_docking_score"] - median).abs()
        calibration_parts.append(
            group.sort_values(
                ["distance_to_decile_median", "feature_completeness", "canonical_id"],
                ascending=[True, False, True],
            ).head(2)
        )
    calibration = pd.concat(calibration_parts, ignore_index=True).head(CALIBRATION_COUNT)
    if len(calibration) < CALIBRATION_COUNT:
        already = set(calibration["canonical_id"])
        fill = remaining.loc[~remaining["canonical_id"].isin(already)].copy()
        global_median = remaining["glide_docking_score"].median()
        fill["distance_to_decile_median"] = (fill["glide_docking_score"] - global_median).abs()
        calibration = pd.concat(
            [calibration, fill.sort_values("distance_to_decile_median").head(CALIBRATION_COUNT - len(calibration))],
            ignore_index=True,
        )

    arms = []
    for name, objective, frame in [
        (
            "exploitation",
            "test whether strongest HTVS multi-score candidates retain favorable same-protocol MMGBSA",
            exploitation,
        ),
        (
            "descriptor_diversity",
            "expand physicochemical and docking-feature coverage before SMILES/scaffold extraction",
            diversity,
        ),
        (
            "score_calibration",
            "add medium and weak docking controls to reduce Top-candidate selection bias",
            calibration,
        ),
    ]:
        arm = frame.copy().reset_index(drop=True)
        arm["selection_arm"] = name
        arm["selection_objective"] = objective
        arm["arm_rank"] = np.arange(1, len(arm) + 1)
        arm["wave"] = np.where(arm["arm_rank"].le(WAVE1_PER_ARM), 1, 2)
        arm["priority"] = np.where(arm["wave"].eq(1), "P0", "P1")
        arms.append(arm)
    queue = pd.concat(arms, ignore_index=True)
    arm_order = {"exploitation": 0, "descriptor_diversity": 1, "score_calibration": 2}
    queue["_arm_order"] = queue["selection_arm"].map(arm_order)
    queue = queue.sort_values(["wave", "arm_rank", "_arm_order"]).reset_index(drop=True)
    queue["acquisition_order"] = np.arange(1, len(queue) + 1)
    queue["acquisition_id"] = queue["acquisition_order"].map(lambda value: f"ATP-ACQ-{value:04d}")
    queue["next_required_action"] = (
        "export exact selected pose to SDF/SMILES; verify identity; then run frozen same-protocol MMGBSA"
    )
    queue["mmgbsa_label_status"] = "pending"
    queue["experimental_activity_status"] = "unknown"
    queue = queue.drop(columns=["_arm_order"], errors="ignore")
    return queue, diversity_features


def queue_columns() -> list[str]:
    return [
        "acquisition_id",
        "acquisition_order",
        "priority",
        "wave",
        "selection_arm",
        "arm_rank",
        "selection_objective",
        "canonical_id",
        "compound_code",
        "title",
        "variant",
        "pose_index",
        "source_file",
        "source_file_exists",
        "pose_count",
        "variant_count",
        "smiles",
        "structure_status",
        "feature_completeness",
        "glide_docking_score",
        "glide_emodel",
        "glide_energy",
        "glide_ligand_efficiency",
        "docking_priority",
        "emodel_priority",
        "ligand_efficiency_priority",
        "exploitation_score",
        "quickprop_mol_mw",
        "quickprop_psa",
        "quickprop_qplogpo_w",
        "quickprop_qplogs",
        "quickprop_qplogherg",
        "quickprop_percenthumanoralabsorption",
        "quickprop_stars",
        "known_internal_overlap",
        "next_required_action",
        "mmgbsa_label_status",
        "experimental_activity_status",
    ]


def mmgbsa_template(queue: pd.DataFrame) -> pd.DataFrame:
    result = queue[
        [
            "acquisition_id",
            "canonical_id",
            "compound_code",
            "title",
            "variant",
            "pose_index",
            "source_file",
            "priority",
            "wave",
            "selection_arm",
        ]
    ].copy()
    for column in [
        "exported_structure_file",
        "canonical_smiles",
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


def experimental_template(project_root: Path) -> pd.DataFrame:
    training = pd.read_csv(project_root / "data/model_v3/training_table.csv")
    ranking = pd.read_csv(project_root / "results/final_candidate_ranking.csv")
    alias = ranking.set_index("compound_id")["historical_alias"].to_dict()
    result = training[["compound_id", "canonical_smiles", "scaffold"]].copy()
    result.insert(1, "historical_alias", result["compound_id"].map(alias).fillna(""))
    result["organism"] = "Acinetobacter baumannii"
    for column in [
        "strain",
        "target",
        "target_protein_id",
        "assay_type",
        "activity_type",
        "activity_value",
        "comparator",
        "lower_bound",
        "upper_bound",
        "unit",
        "replicate_id",
        "assay_protocol_id",
        "experimental_date",
        "operator",
        "reference",
        "qc_status",
        "notes",
    ]:
        result[column] = ""
    result["evidence_type"] = "experimental_pending"
    return result


def data_requirements() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "priority": 1,
                "data_asset": "same-protocol internal MMGBSA expansion",
                "current_usable_scale": "17 internal candidates",
                "recommended_next_batch": "24 P0, then 36 P1",
                "required_fields": "compound_id, exported structure, protocol_id, dG Bind, status, date",
                "why_it_matters": "directly expands the actual Task C label instead of adding distant proxy features",
                "acceptance_gate": "same protein/preparation/protocol; traceable pose; no failed calculations as numeric labels",
            },
            {
                "priority": 2,
                "data_asset": "HTVS structure identity export",
                "current_usable_scale": "0/1633 HTVS IDs have SMILES in molecules.csv",
                "recommended_next_batch": "all 60 queued candidates first",
                "required_fields": "canonical_id, exact pose, SDF, canonical SMILES, source_file, title, variant",
                "why_it_matters": "unlocks Morgan fingerprints, scaffold splits, structural diversity and duplicate control",
                "acceptance_gate": "RDKit-readable structure and exact source-pose traceability",
            },
            {
                "priority": 3,
                "data_asset": "internal candidate biological validation",
                "current_usable_scale": "0 confirmed MIC/ATP-enzyme labels for current 17",
                "recommended_next_batch": "17 candidates under one frozen assay protocol",
                "required_fields": "strain, target, assay, value/comparator, unit, replicate, protocol_id, QC",
                "why_it_matters": "creates the first real bridge from computational ranking to biological relevance",
                "acceptance_gate": "replicates and controls; censored values retained as bounds; toxicity kept separate",
            },
            {
                "priority": 4,
                "data_asset": "near-space A. baumannii ATP synthase inhibitors",
                "current_usable_scale": "0 exact structures and 0 scaffolds overlap with internal 17",
                "recommended_next_batch": "30-50 analogs across active, medium and inactive outcomes",
                "required_fields": "SMILES, subunit/construct, strain, assay, activity, unit, reference, source level",
                "why_it_matters": "reduces the chemical-space and target-protocol domain shift seen in v4-alpha",
                "acceptance_gate": "single endpoint/unit strata; scaffold-aware deduplication; original-source review",
            },
            {
                "priority": 5,
                "data_asset": "frozen independent validation set",
                "current_usable_scale": "0 evaluable independent candidates",
                "recommended_next_batch": "at least 30 compounds from unseen scaffolds when available",
                "required_fields": "complete scoring inputs plus homogeneous experimental endpoint",
                "why_it_matters": "separates real generalization from repeated tuning on the same 17 candidates",
                "acceptance_gate": "frozen before model selection; no structure/source overlap with training",
            },
        ]
    )


def report_text(summary: dict[str, Any]) -> str:
    return f"""# Phase 8 Data Strengthening Plan

日期：2026-08-24  
状态：数据获取规划已运行；未训练或修改任何模型

## 1. 为什么当前模型不能继续只靠算法变强

- 内部Task C只有17个静态MM/GBSA标签，任何复杂模型都会受到高维小样本限制；
- 现有外部Task B与内部17候选没有精确结构或scaffold重叠，Morgan最近邻相似度也很低；
- MIC、ATP target activity和MM/GBSA属于不同任务，不能通过混合标签制造样本量；
- 当前HTVS库有{summary['pose_rows']:,}个pose和{summary['pool_compounds']:,}个compound ID，但`molecules.csv`中可直接连接的HTVS SMILES为{summary['pool_smiles_available']}；
- 所以当前最高价值动作是补内部同协议标签并导出结构，而不是继续增加模型复杂度。

## 2. 本阶段建立的数据增益队列

- 可追溯且达到选择门槛的HTVS候选：{summary['eligible_compounds']:,}；
- 排除已知内部候选映射：{summary['known_internal_overlap']}；
- P0首批：24个，由8个exploitation、8个descriptor diversity、8个score calibration组成；
- P1扩展批：36个，三组各12个；
- 总队列：60个，全部保留source file、title、variant、pose index和原始Docking/QuickProp证据。

三个selection arm不是三种活性标签：

1. `exploitation`：检验HTVS多评分最优分子能否在同协议MM/GBSA中保持优势；
2. `descriptor_diversity`：在缺少SMILES前，用Docking/QuickProp连续特征扩展理化覆盖；
3. `score_calibration`：主动加入中等和较弱Docking分子，避免训练集只包含Top hits。

## 3. 强制执行顺序

1. 从`source_file`按title/variant/pose导出精确SDF；
2. 生成canonical SMILES并做结构QC、重复检查和身份回写；
3. 对P0 24个分子执行与现有17候选完全一致的静态MM/GBSA协议；
4. 审计失败/缺失计算，不把失败任务写成数值；
5. P0通过后再运行P1 36个；
6. 标签达到至少41个内部样本后才进入下一轮模型实验；达到77个时再进行正式scaffold benchmark。

上述41和77分别代表当前17+P0 24、当前17+全部队列60，是数据批次里程碑，不是性能保证。

## 4. 湿实验最高价值数据

如果只能做一类实验，优先为当前17候选建立同一protocol下的鲍曼不动杆菌ATP synthase功能/酶抑制数据；其次是同菌株MIC；毒性必须保持独立端点。

实验记录必须包含strain、target construct、assay type、unit、replicate、上下限、protocol ID和QC。未完成结果保持空值或`unknown`。

## 5. 当前限制

- HTVS候选当前没有SMILES，因此本队列的多样性是descriptor-space diversity，不是Morgan/scaffold diversity；
- 队列是数据获取优先级，不是候选活性排名或新药发现结论；
- MM/GBSA是计算标签，不能替代MIC或ATP enzyme实验；
- 是否执行60个MM/GBSA取决于实际计算资源，但应保持P0/P1顺序和同协议要求。

## 6. 可执行产物

- `results/phase8_data_acquisition/mmgbsa_acquisition_queue.csv`
- `results/phase8_data_acquisition/htvs_pool_audit.csv`
- `results/phase8_data_acquisition/data_requirements_priority.csv`
- `data/templates/phase8_mmgbsa_return_template.csv`
- `data/templates/phase8_experimental_activity_template.csv`
- `src/data_acquisition_planner.py`
"""


def run(project_root: Path) -> dict[str, Any]:
    project_root = project_root.resolve()
    input_path = project_root / "data/docking_features_v0_2.csv"
    results_dir = project_root / "results/phase8_data_acquisition"
    templates_dir = project_root / "data/templates"
    docking = pd.read_csv(input_path)
    pool = annotate_pool(best_pose_pool(docking, project_root), project_root)
    queue, diversity_features = select_queue(pool)
    queue = queue[queue_columns()]
    requirements = data_requirements()

    pool["selected_for_phase8"] = pool["canonical_id"].isin(set(queue["canonical_id"]))
    selection_map = queue.set_index("canonical_id")[["acquisition_id", "priority", "wave", "selection_arm"]]
    pool = pool.merge(selection_map, on="canonical_id", how="left", validate="one_to_one")

    summary = {
        "phase": "Phase 8 Data Acquisition Intelligence",
        "model_change": "none",
        "input_file": "data/docking_features_v0_2.csv",
        "input_sha256": sha256(input_path),
        "pose_rows": int(len(docking)),
        "pool_compounds": int(pool["canonical_id"].nunique()),
        "source_files": int(docking["source_file"].nunique()),
        "source_file_exists": int(pool["source_file_exists"].sum()),
        "pool_smiles_available": int(pool["smiles"].astype(str).str.len().gt(0).sum()),
        "known_internal_overlap": int(pool["known_internal_overlap"].sum()),
        "eligible_compounds": int(pool["selection_eligible"].sum()),
        "queue_size": int(len(queue)),
        "wave1_size": int(queue["wave"].eq(1).sum()),
        "wave2_size": int(queue["wave"].eq(2).sum()),
        "selection_arms": queue["selection_arm"].value_counts().to_dict(),
        "diversity_basis": diversity_features,
        "label_policy": "all MMGBSA and experimental fields remain blank until returned by the real workflow",
        "next_training_gate": "no retraining before P0 structure QC and same-protocol MMGBSA labels are audited",
    }

    atomic_csv(queue, results_dir / "mmgbsa_acquisition_queue.csv")
    atomic_csv(pool.sort_values("canonical_id"), results_dir / "htvs_pool_audit.csv")
    atomic_csv(requirements, results_dir / "data_requirements_priority.csv")
    atomic_csv(mmgbsa_template(queue), templates_dir / "phase8_mmgbsa_return_template.csv")
    atomic_csv(experimental_template(project_root), templates_dir / "phase8_experimental_activity_template.csv")
    atomic_json(summary, results_dir / "acquisition_summary.json")
    atomic_text(report_text(summary), project_root / "docs/Phase8_Data_Strengthening_Plan.md")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    print(json.dumps(json_safe(run(args.project_root)), ensure_ascii=False, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
