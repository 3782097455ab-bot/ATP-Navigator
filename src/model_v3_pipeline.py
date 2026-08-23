"""ATP-Navigator Model v3: feature-enhanced, external-knowledge ranking.

The internal supervised task remains ranking 17 identity-confirmed candidates
against the same-protocol static MM/GBSA computational label. Static MM/GBSA
is never used as an input feature. MD/MMGBSA and MD interaction summaries are
exported as evidence, but are excluded from training because they cover only
IN-2 and Hit3 (only Hit3 belongs to the 17-candidate training set).

All outputs are additive and versioned under data/model_v3, models/model_v3,
results/model_v3, and docs/Model_v3_Report.md. Existing baselines are read-only
comparators.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any

if os.name == "nt":
    os.environ.setdefault("WINDIR", os.environ.get("SystemRoot", r"C:\Windows"))

import joblib
import lightgbm as lgb
import numpy as np
import pandas as pd
from rdkit import Chem, DataStructs, rdBase
from rdkit.Chem import Crippen, Descriptors, Lipinski, rdFingerprintGenerator, rdMolDescriptors
from rdkit.Chem.Scaffolds import MurckoScaffold
from scipy import __version__ as scipy_version
from sklearn.model_selection import LeaveOneGroupOut

from model_v2_pipeline import MODEL_VERSION as MODEL_V2_VERSION
from model_v2_pipeline import make_regressor, ranking_metrics, sha256


rdBase.DisableLog("rdApp.warning")

MODEL_VERSION = "ATP-Navigator_Model_v3.0"
RANDOM_SEED = 42
TOP_K = 5
EXACT_NUMBER = re.compile(r"^-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?$")

MORGAN_COLUMNS = [f"morgan1024_{index:04d}" for index in range(1024)]
ENHANCED_DESCRIPTOR_COLUMNS = [
    "desc_mol_wt",
    "desc_exact_mol_wt",
    "desc_logp",
    "desc_tpsa",
    "desc_hbd",
    "desc_hba",
    "desc_rotatable_bonds",
    "desc_aromatic_ring_count",
    "desc_aliphatic_ring_count",
    "desc_saturated_ring_count",
    "desc_ring_count",
    "desc_heavy_atom_count",
    "desc_total_atom_count",
    "desc_fraction_csp3",
    "desc_formal_charge",
    "desc_molar_refractivity",
]
SIMILARITY_COLUMNS = [
    "similarity_to_known_inhibitor",
    "scaffold_seen_in_known_inhibitors",
]

MD_SOURCE_RELATIVE = {
    "SYS-MD-IN2-001": Path("作图/作图/1-阳性化合物和蛋白的MD/图-3/IN-2.csv"),
    "SYS-MD-HIT-001": Path("作图/作图/1-阳性化合物和蛋白的MD/图-3/Hit.csv"),
}


def atomic_write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", delete=False, dir=path.parent, suffix=".tmp"
    ) as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2, allow_nan=False)
        temporary = Path(handle.name)
    temporary.replace(path)


def canonicalize(smiles: str) -> tuple[str, str, Chem.Mol]:
    mol = Chem.MolFromSmiles(str(smiles))
    if mol is None:
        raise ValueError(f"RDKit could not parse SMILES: {smiles}")
    canonical = Chem.MolToSmiles(mol, canonical=True, isomericSmiles=True)
    scaffold = MurckoScaffold.MurckoScaffoldSmiles(mol=mol, includeChirality=True)
    return canonical, scaffold or canonical, mol


def descriptor_row(mol: Chem.Mol) -> dict[str, float]:
    with_hydrogens = Chem.AddHs(mol)
    return {
        "desc_mol_wt": float(Descriptors.MolWt(mol)),
        "desc_exact_mol_wt": float(Descriptors.ExactMolWt(mol)),
        "desc_logp": float(Crippen.MolLogP(mol)),
        "desc_tpsa": float(rdMolDescriptors.CalcTPSA(mol)),
        "desc_hbd": float(Lipinski.NumHDonors(mol)),
        "desc_hba": float(Lipinski.NumHAcceptors(mol)),
        "desc_rotatable_bonds": float(Lipinski.NumRotatableBonds(mol)),
        "desc_aromatic_ring_count": float(rdMolDescriptors.CalcNumAromaticRings(mol)),
        "desc_aliphatic_ring_count": float(rdMolDescriptors.CalcNumAliphaticRings(mol)),
        "desc_saturated_ring_count": float(rdMolDescriptors.CalcNumSaturatedRings(mol)),
        "desc_ring_count": float(rdMolDescriptors.CalcNumRings(mol)),
        "desc_heavy_atom_count": float(mol.GetNumHeavyAtoms()),
        "desc_total_atom_count": float(with_hydrogens.GetNumAtoms()),
        "desc_fraction_csp3": float(rdMolDescriptors.CalcFractionCSP3(mol)),
        "desc_formal_charge": float(Chem.GetFormalCharge(mol)),
        "desc_molar_refractivity": float(Crippen.MolMR(mol)),
    }


def direct_atp_reference_set(dataset: pd.DataFrame) -> pd.DataFrame:
    layer = dataset["dataset_layer"].eq("layer_2_atp_synthase_specific")
    target = dataset["target"].str.contains("ATP synthase", case=False, na=False)
    direct_activity = (
        dataset["activity_type"].str.contains("ATP synthesis", case=False, na=False)
        | dataset["activity_type"].eq("IC50")
    )
    traceable = ~dataset["label_confidence"].str.startswith("low_", na=False)
    exact_positive = dataset["activity_value"].map(
        lambda value: bool(EXACT_NUMBER.fullmatch(str(value))) and float(value) > 0
    )
    selected = dataset.loc[layer & target & direct_activity & traceable & exact_positive].copy()

    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    for record in selected.itertuples(index=False):
        try:
            canonical, scaffold, _ = canonicalize(record.canonical_smiles)
        except ValueError:
            continue
        if canonical in seen:
            continue
        seen.add(canonical)
        rows.append(
            {
                "reference_compound_id": record.compound_id,
                "canonical_smiles": canonical,
                "scaffold": scaffold,
                "activity_type": record.activity_type,
                "unit": record.unit,
                "data_source": record.data_source,
                "reference": record.reference,
                "label_confidence": record.label_confidence,
            }
        )
    output = pd.DataFrame(rows)
    if output.empty:
        raise ValueError("No traceable direct ATP-synthase inhibitor reference structures were found")
    return output


def chemical_space_table(samples: pd.DataFrame, dataset: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    generator = rdFingerprintGenerator.GetMorganGenerator(
        radius=2, fpSize=1024, includeChirality=True
    )
    references = direct_atp_reference_set(dataset)
    reference_fingerprints = []
    for smiles in references["canonical_smiles"]:
        _, _, mol = canonicalize(smiles)
        reference_fingerprints.append(generator.GetFingerprint(mol))
    known_scaffolds = set(references["scaffold"])

    rows: list[dict[str, Any]] = []
    canonical_internal = []
    for record in samples.itertuples(index=False):
        canonical, scaffold, mol = canonicalize(record.canonical_smiles)
        canonical_internal.append(canonical)
        fingerprint = generator.GetFingerprint(mol)
        similarities = np.asarray(
            DataStructs.BulkTanimotoSimilarity(fingerprint, reference_fingerprints), dtype=float
        )
        nearest_index = int(np.argmax(similarities))
        nearest = references.iloc[nearest_index]
        rows.append(
            {
                "compound_id": record.compound_id,
                "canonical_smiles": canonical,
                "scaffold": scaffold,
                "internal_scaffold_size": 0,
                "scaffold_seen_in_known_inhibitors": int(scaffold in known_scaffolds),
                "similarity_to_known_inhibitor": float(similarities[nearest_index]),
                "nearest_known_inhibitor_id": nearest["reference_compound_id"],
                "nearest_reference_activity_type": nearest["activity_type"],
                "nearest_reference_unit": nearest["unit"],
                "nearest_reference_source": nearest["data_source"],
                "similarity_metric": "Morgan radius=2, 1024 bit, chirality=True; Tanimoto",
                "reference_set_size": len(references),
                "reference_evidence": "source-traceable external direct ATP assay; not internally confirmed",
            }
        )
    output = pd.DataFrame(rows)
    scaffold_sizes = output.groupby("scaffold")["compound_id"].transform("size")
    output["internal_scaffold_size"] = scaffold_sizes.astype(int)
    if len(set(canonical_internal)) != len(canonical_internal):
        raise ValueError("Internal samples are not unique by RDKit canonical SMILES")
    return output, references


def interaction_column_name(interaction_type: str, suffix: str) -> str:
    slug = interaction_type.lower().replace("-", "_").replace(" ", "_")
    return f"md_{slug}_{suffix}"


def md_summary(source_path: Path, source_label: str) -> dict[str, Any]:
    if not source_path.exists():
        return {
            "md_mmgbsa_status": "source_not_available",
            "md_mmgbsa_source": source_label,
        }
    frame = pd.read_csv(source_path, low_memory=False)
    column = "r_psp_MMGBSA_dG_Bind"
    if column not in frame.columns:
        return {
            "md_mmgbsa_status": "required_column_missing",
            "md_mmgbsa_source": source_label,
        }
    values = pd.to_numeric(frame[column], errors="coerce").dropna()
    if values.empty:
        return {
            "md_mmgbsa_status": "no_numeric_values",
            "md_mmgbsa_source": source_label,
        }
    return {
        "md_mmgbsa_status": "available_case_evidence",
        "md_mmgbsa_frame_count": int(len(values)),
        "md_mmgbsa_mean": float(values.mean()),
        "md_mmgbsa_sd": float(values.std(ddof=1)),
        "md_mmgbsa_median": float(values.median()),
        "md_mmgbsa_q25": float(values.quantile(0.25)),
        "md_mmgbsa_q75": float(values.quantile(0.75)),
        "md_mmgbsa_min": float(values.min()),
        "md_mmgbsa_max": float(values.max()),
        "md_mmgbsa_source": source_label,
    }


def binding_feature_table(project_root: Path, workspace_root: Path, samples: pd.DataFrame) -> pd.DataFrame:
    molecules = pd.read_csv(project_root / "data" / "molecules.csv", dtype=str, keep_default_na=False)
    mappings = pd.read_csv(
        project_root / "data" / "compound_mapping_v1.csv", dtype=str, keep_default_na=False
    )
    systems = pd.read_csv(project_root / "data" / "systems.csv", dtype=str, keep_default_na=False)
    interaction_audit = json.loads(
        (project_root / "results" / "phase4_interaction_audit.json").read_text(encoding="utf-8")
    )

    base_columns = [
        "compound_id",
        "historical_alias",
        "canonical_smiles",
        "glide_docking_score",
        "glide_emodel",
        "glide_ligand_efficiency",
        "label_score",
        "feature_source",
        "label_source",
        "label_protocol",
    ]
    rows_by_id: dict[str, dict[str, Any]] = {}
    for row in samples[base_columns].to_dict(orient="records"):
        row["static_mmgbsa_dg_bind"] = float(row.pop("label_score"))
        row["docking_feature_source"] = row.pop("feature_source")
        row["static_mmgbsa_source"] = row.pop("label_source")
        row["static_mmgbsa_protocol"] = row.pop("label_protocol")
        row["static_mmgbsa_role"] = "training_label_only"
        row["is_internal_training_candidate"] = True
        rows_by_id[row["compound_id"]] = row

    reference_id = "ATP-SMI-1EDF03AEDEF9"
    if reference_id not in rows_by_id:
        reference = molecules.loc[molecules["canonical_id"].eq(reference_id)]
        if len(reference):
            rows_by_id[reference_id] = {
                "compound_id": reference_id,
                "historical_alias": "IN-2",
                "canonical_smiles": reference.iloc[0]["smiles"],
                "glide_docking_score": np.nan,
                "glide_emodel": np.nan,
                "glide_ligand_efficiency": np.nan,
                "static_mmgbsa_dg_bind": np.nan,
                "static_mmgbsa_role": "not_available",
                "is_internal_training_candidate": False,
            }

    alias_to_canonical = {
        record.original_name: record.canonical_id
        for record in mappings.itertuples(index=False)
        if record.confidence == "confirmed"
    }
    for system in systems.itertuples(index=False):
        canonical_id = alias_to_canonical.get(system.ligand_id, "")
        if not canonical_id or canonical_id not in rows_by_id:
            continue
        row = rows_by_id[canonical_id]
        row["md_system_id"] = system.system_id
        row["md_protein"] = system.protein
        row["md_trajectory_status"] = system.trajectory_status
        source_relative = MD_SOURCE_RELATIVE.get(system.system_id)
        if source_relative is not None:
            row.update(md_summary(workspace_root / source_relative, source_relative.as_posix()))

        audit = interaction_audit.get("systems", {}).get(system.system_id, {})
        row["md_interaction_source"] = audit.get("raw_data_dir", "")
        system_frames = int(audit.get("system_frame_count_from_contact_exports") or 0)
        row["md_contact_frame_count"] = system_frames or np.nan
        corruption = False
        for property_name, contact in audit.get("contacts", {}).items():
            parsed = int(contact.get("parsed_event_rows") or 0)
            occupied = int(contact.get("unique_event_frames") or 0)
            row[interaction_column_name(property_name, "event_count_per_frame")] = (
                parsed / system_frames if system_frames else np.nan
            )
            row[interaction_column_name(property_name, "occupied_frame_fraction")] = (
                occupied / system_frames if system_frames else np.nan
            )
            corruption = corruption or int(contact.get("nul_bytes") or 0) > 0
        row["md_source_corruption_flag"] = corruption
        row["md_interaction_status"] = "available_case_evidence"
        row["md_used_in_model_v3"] = False
        row["md_training_exclusion_reason"] = (
            "MD interaction/MMGBSA coverage is 1 of 17 internal candidates; case evidence only"
        )

    output = pd.DataFrame(rows_by_id.values())
    if "md_interaction_status" not in output:
        output["md_interaction_status"] = "not_available"
    else:
        output["md_interaction_status"] = output["md_interaction_status"].fillna("not_available")
    if "md_used_in_model_v3" not in output:
        output["md_used_in_model_v3"] = False
    else:
        output["md_used_in_model_v3"] = (
            output["md_used_in_model_v3"].astype("boolean").fillna(False).astype(bool)
        )
    if "md_training_exclusion_reason" not in output:
        output["md_training_exclusion_reason"] = "No same-protocol MD feature block for this compound"
    else:
        output["md_training_exclusion_reason"] = output["md_training_exclusion_reason"].fillna(
            "No same-protocol MD feature block for this compound"
        )
    return output.sort_values(["is_internal_training_candidate", "compound_id"], ascending=[False, True])


def make_feature_table(
    project_root: Path,
    samples: pd.DataFrame,
    chemical_space: pd.DataFrame,
) -> tuple[pd.DataFrame, dict[str, list[str]]]:
    manifest = pd.read_csv(
        project_root / "data" / "dataset_v0.2" / "feature_manifest.csv",
        dtype=str,
        keep_default_na=False,
    )
    docking_columns = manifest.loc[
        manifest["feature_group"].eq("docking")
        & manifest["used_in_model2"].str.lower().eq("true"),
        "feature",
    ].tolist()
    quickprop_columns = manifest.loc[
        manifest["feature_group"].eq("quickprop")
        & manifest["used_in_model2"].str.lower().eq("true"),
        "feature",
    ].tolist()
    priors = pd.read_csv(project_root / "results" / "model_v2" / "external_priors_internal.csv")
    prior_columns = [column for column in priors.columns if column.startswith("prior_task_")]
    admet = pd.read_csv(project_root / "data" / "admet_features_v0_2.csv")
    admet_columns = [column for column in admet.columns if column.startswith("admet_")]

    output = samples[["compound_id", "canonical_smiles", "scaffold", *MORGAN_COLUMNS]].copy()
    descriptors = []
    canonical_values = []
    scaffold_values = []
    for smiles in output["canonical_smiles"]:
        canonical, scaffold, mol = canonicalize(smiles)
        canonical_values.append(canonical)
        scaffold_values.append(scaffold)
        descriptors.append(descriptor_row(mol))
    output["canonical_smiles"] = canonical_values
    output["scaffold"] = scaffold_values
    output = pd.concat([output.reset_index(drop=True), pd.DataFrame(descriptors)], axis=1)
    output = output.merge(
        samples[["compound_id", *docking_columns, *quickprop_columns]],
        on="compound_id",
        how="left",
        validate="one_to_one",
    )
    output = output.merge(
        chemical_space[["compound_id", *SIMILARITY_COLUMNS]],
        on="compound_id",
        how="left",
        validate="one_to_one",
    )
    output = output.merge(
        admet[["canonical_id", *admet_columns]].rename(columns={"canonical_id": "compound_id"}),
        on="compound_id",
        how="left",
        validate="one_to_one",
    )
    output = output.merge(
        priors[["compound_id", *prior_columns]],
        on="compound_id",
        how="left",
        validate="one_to_one",
    )

    groups = {
        "morgan_fingerprint": MORGAN_COLUMNS,
        "enhanced_rdkit_descriptors": ENHANCED_DESCRIPTOR_COLUMNS,
        "chemical_similarity": SIMILARITY_COLUMNS,
        "docking": docking_columns,
        "quickprop_complete_nonconstant": quickprop_columns,
        "admet": admet_columns,
        "external_knowledge_priors": prior_columns,
    }
    features = [column for columns in groups.values() for column in columns]
    numeric = output[features].apply(pd.to_numeric, errors="coerce")
    missing = numeric.isna().sum()
    bad = missing.loc[missing.gt(0)]
    if len(bad):
        raise ValueError(f"Model v3 requires complete features; missing values: {bad.to_dict()}")
    if output["compound_id"].duplicated().any() or output["canonical_smiles"].duplicated().any():
        raise ValueError("Feature table contains duplicate compound identity")
    output[features] = numeric.astype(np.float32)
    return output, groups


def logo_oof(x: pd.DataFrame, y: np.ndarray, groups: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    splitter = LeaveOneGroupOut()
    predictions = np.full(len(y), np.nan, dtype=float)
    folds = np.full(len(y), -1, dtype=int)
    for fold, (train_index, test_index) in enumerate(splitter.split(x, y, groups), start=1):
        model = make_regressor()
        model.fit(x.iloc[train_index], y[train_index])
        predictions[test_index] = model.predict(x.iloc[test_index])
        folds[test_index] = fold
    if np.isnan(predictions).any() or (folds < 0).any():
        raise RuntimeError("Model v3 OOF predictions are incomplete")
    return predictions, folds


def comparator_table(project_root: Path, v3_metrics: dict[str, Any], feature_count: int) -> pd.DataFrame:
    preserved = pd.read_csv(project_root / "results" / "model_v2" / "internal_model_comparison.csv")
    selections = [
        ("Model 0", "Model v0", "Docking ranking"),
        ("Legacy P1 LightGBM", "Model v1", "Current baseline"),
        ("Model v2-B", "Model v2", "External knowledge enhanced model"),
    ]
    rows: list[dict[str, Any]] = []
    for source_id, model_id, label in selections:
        selected = preserved.loc[preserved["model_id"].eq(source_id)]
        if len(selected) != 1:
            raise ValueError(f"Expected one preserved comparator row for {source_id}")
        source = selected.iloc[0]
        rows.append(
            {
                "model_id": model_id,
                "model": source["model"],
                "description": label,
                "evaluation_samples": int(source["evaluation_samples"]),
                "scaffold_groups": int(source["scaffold_groups"]),
                "benchmark_protocol": source["benchmark_protocol"],
                "feature_count": int(source["feature_count"]),
                "spearman": float(source["spearman"]),
                "rmse": float(source["rmse"]),
                "ndcg_at_5": float(source["ndcg_at_5"]),
                "top_k_enrichment": float(source["top_k_enrichment"]),
                "hit_recovery": float(source["hit_recovery"]),
                "status": "preserved_comparator",
                "source_model_id": source_id,
            }
        )
    rows.append(
        {
            "model_id": "Model v3",
            "model": "lightgbm_feature_external_enhanced_v3",
            "description": "Structure + external knowledge enhanced ranking model",
            "evaluation_samples": 17,
            "scaffold_groups": 11,
            "benchmark_protocol": "scaffold_grouped_leave_one_out",
            "feature_count": feature_count,
            "spearman": v3_metrics["spearman"],
            "rmse": v3_metrics["rmse"],
            "ndcg_at_5": v3_metrics["ndcg_at_5"],
            "top_k_enrichment": v3_metrics["top_k_enrichment"],
            "hit_recovery": v3_metrics["hit_recovery"],
            "status": "new_oof_result",
            "source_model_id": "Model v3",
        }
    )
    return pd.DataFrame(rows)


def report_text(
    comparison: pd.DataFrame,
    feature_groups: dict[str, list[str]],
    reference_count: int,
    binding: pd.DataFrame,
) -> str:
    v2 = comparison.loc[comparison["model_id"].eq("Model v2")].iloc[0]
    v3 = comparison.loc[comparison["model_id"].eq("Model v3")].iloc[0]
    deltas = {
        "spearman": v3["spearman"] - v2["spearman"],
        "rmse": v3["rmse"] - v2["rmse"],
        "ndcg": v3["ndcg_at_5"] - v2["ndcg_at_5"],
        "enrichment": v3["top_k_enrichment"] - v2["top_k_enrichment"],
    }
    metric_rows = []
    for row in comparison.itertuples(index=False):
        metric_rows.append(
            f"| {row.model_id} | {row.feature_count} | {row.spearman:.4f} | "
            f"{row.rmse:.4f} | {row.ndcg_at_5:.4f} | "
            f"{row.top_k_enrichment:.2f} | {row.hit_recovery:.2f} |"
        )
    md_internal = binding.loc[
        binding["is_internal_training_candidate"].eq(True)
        & binding["md_interaction_status"].eq("available_case_evidence")
    ]
    feature_lines = [f"- `{name}`：{len(columns)} 个特征" for name, columns in feature_groups.items()]
    improved = []
    if deltas["spearman"] > 0:
        improved.append("Spearman")
    if deltas["rmse"] < 0:
        improved.append("RMSE")
    if deltas["ndcg"] > 0:
        improved.append("NDCG@5")
    if deltas["enrichment"] > 0:
        improved.append("Top-5 enrichment")
    improvement_statement = "、".join(improved) if improved else "本轮四项主指标均未形成提升"

    return f"""# ATP-Navigator Model v3 Report

版本：Model v3.0  
任务：Feature-enhanced AI ranking model  
标签语义：同协议静态 MM/GBSA 计算排序，lower-is-better；不是实验活性。

## 1. 新增的 AI 能力

Model v3 在保留 Morgan fingerprint、Docking/QuickProp 和 Model v2 外部知识先验的基础上，新增了更完整的 RDKit 分子大小/原子/环/H-bond/LogP/TPSA/可旋转键描述符、面向可追溯直接 ATP assay 参考集的最大 Morgan-Tanimoto 相似性、scaffold 覆盖标志，以及完整覆盖内部 17 个候选的 ADMET endpoint 特征。

化学空间分析使用 {reference_count} 个去重后的外部直接 ATP assay 参考结构。其 `label_confidence` 仍是来源可追溯但未逐条内部复核，因此相似性是外部知识特征，不是已确认活性标签。

## 2. 相比 Model v2 的变化

Model v3 相比 Model v2 的 OOF 指标变化：Spearman {deltas['spearman']:+.4f}，RMSE {deltas['rmse']:+.4f}，NDCG@5 {deltas['ndcg']:+.4f}，Top-5 enrichment {deltas['enrichment']:+.2f}。本轮实际改善项为：{improvement_statement}。由于只有 17 个样本，不能把任何小幅变化解释为稳定泛化提升。

## 3. 使用的数据

- 内部 Dataset v0.2：17 个身份确认候选；11 个 Bemis–Murcko scaffold。
- 训练标签：`MMGBSA_dG_Bind_static`，只作监督标签和评价基准。
- Model v2 外部先验：AB whole-cell MIC、PA ATP IC50、Mtb ATP IC50、AB ATP IC50 四个隔离任务的预测值。
- ADMET：17/17 候选具有完整 endpoint 记录。
- Docking 与完整非恒定 QuickProp：17/17 候选覆盖。
- MD interaction/MMGBSA：内部候选仅 {len(md_internal)}/17 覆盖，未进入训练。

## 4. 模型结构

模型为 LightGBM regression，沿用 Model v2 的固定参数和 `random_state=42`，不做小样本超参数搜索。评价采用 Leave-One-Scaffold-Group-Out，共 11 折；同一 scaffold 不跨训练与测试。

特征组成：

{chr(10).join(feature_lines)}

总特征数：{len([item for columns in feature_groups.values() for item in columns])}。

静态 MM/GBSA 未进入特征；MD/MMGBSA 和 MD interaction 只写入 `binding_feature_table.csv`，不进行均值填充，也不把“是否做过 MD”作为模型信号。

## 5. 严格评价结果

所有模型均在同一 17 个候选上比较；Model v0/v1/v2 读取既有不可变结果，Model v3 使用同类 scaffold-aware OOF 协议。

| 模型 | 特征数 | Spearman | RMSE | NDCG@5 | Top-5 enrichment | Hit recovery |
|---|---:|---:|---:|---:|---:|---:|
{chr(10).join(metric_rows)}

Docking-only 的 RMSE 是 Glide score 与 MM/GBSA 的跨量纲差，只保留作形式对照，不能解释为校准误差。其余 RMSE 均是静态 MM/GBSA 标签尺度上的 OOF 误差。

`candidate_ranking.csv` 来自在全部 17 个内部样本上重新拟合的最终模型，用于形成当前候选优先级输出；它不参与上表性能计算。上表 Model v3 指标只来自未见当前 scaffold 的 OOF 预测。

## 6. 限制

- 内部标签只有 17 个样本，单个候选即可显著改变 Top-5 指标。
- 没有独立的前瞻性测试集，也没有生物活性标签；本模型只优化计算候选排序。
- 外部 ATP 参考数据来源可追溯但尚未逐条回源复核，相似性和先验存在 domain shift。
- ADMET endpoint 为预测数据，不是本团队实验测量。
- MD 动态证据只覆盖 IN-2 与 Hit3，原始轨迹仍为不完整下载片段；现有接触导出可作案例证据但不可支持通用 MD 特征模型。
- 本轮没有把静态 MM/GBSA作为输入，因此不存在用标签预测标签的直接泄漏；也没有把缺失 MD 特征静默填充。

## 7. 产物与复现

- `src/model_v3_pipeline.py`
- `data/model_v3/chemical_space_analysis.csv`
- `data/model_v3/binding_feature_table.csv`
- `models/model_v3/model.joblib`
- `models/model_v3/training_config.json`
- `models/model_v3/feature_list.json`
- `results/model_v3/model_v3_comparison.csv`
- `results/model_v3/model_v3_oof_predictions.csv`
- `results/model_v3/candidate_ranking.csv`

当前目录布局下运行：`.venv/Scripts/python.exe src/model_v3_pipeline.py train`。如果仓库与 `表征/运行/作图` 不在同一父目录，使用 `--workspace-root` 显式指定资料工作区。
"""


def train(project_root: Path, workspace_root: Path) -> dict[str, Any]:
    data_dir = project_root / "data" / "model_v3"
    model_dir = project_root / "models" / "model_v3"
    result_dir = project_root / "results" / "model_v3"
    for directory in (data_dir, model_dir, result_dir):
        directory.mkdir(parents=True, exist_ok=True)

    samples_path = project_root / "data" / "dataset_v0.2" / "samples.csv"
    dataset_path = project_root / "data" / "dataset_v1.0" / "ATP_Navigator_Dataset_v1.csv"
    samples = pd.read_csv(samples_path, low_memory=False)
    dataset = pd.read_csv(dataset_path, dtype=str, keep_default_na=False)
    if len(samples) != 17:
        raise ValueError(f"Expected preserved 17-candidate internal dataset, found {len(samples)}")
    if samples["compound_id"].duplicated().any() or samples["canonical_smiles"].duplicated().any():
        raise ValueError("Internal candidate identity is not unique")

    chemical_space, references = chemical_space_table(samples, dataset)
    chemical_space.to_csv(data_dir / "chemical_space_analysis.csv", index=False)

    binding = binding_feature_table(project_root, workspace_root, samples)
    binding.to_csv(data_dir / "binding_feature_table.csv", index=False)

    feature_table, feature_groups = make_feature_table(
        project_root, samples, chemical_space
    )
    feature_columns = [column for columns in feature_groups.values() for column in columns]
    training_table = feature_table.merge(
        samples[["compound_id", "label_score", "label_source", "label_type", "label_protocol"]],
        on="compound_id",
        how="left",
        validate="one_to_one",
    )
    training_table.to_csv(data_dir / "training_table.csv", index=False)

    x = feature_table[feature_columns]
    y = samples.set_index("compound_id").loc[feature_table["compound_id"], "label_score"].to_numpy(dtype=float)
    scaffolds = feature_table["scaffold"].to_numpy(dtype=str)
    if len(np.unique(scaffolds)) != 11:
        raise ValueError(f"Expected 11 preserved scaffold groups, found {len(np.unique(scaffolds))}")
    predictions, folds = logo_oof(x, y, scaffolds)
    metrics = ranking_metrics(y, predictions, k=TOP_K)

    observed_order = np.argsort(y, kind="stable")
    true_top = set(observed_order[: min(TOP_K, len(y))])
    predicted_top = set(np.argsort(predictions, kind="stable")[: min(TOP_K, len(y))])
    oof = feature_table[["compound_id", "canonical_smiles", "scaffold"]].copy()
    oof["fold_id"] = folds
    oof["observed_static_mmgbsa"] = y
    oof["oof_prediction"] = predictions
    oof["observed_rank"] = pd.Series(y).rank(method="min", ascending=True).astype(int)
    oof["predicted_rank"] = pd.Series(predictions).rank(method="min", ascending=True).astype(int)
    oof["is_true_top5"] = [index in true_top for index in range(len(y))]
    oof["is_predicted_top5"] = [index in predicted_top for index in range(len(y))]
    oof["label_semantics"] = "computational_static_MMGBSA_not_biological_activity"
    oof.to_csv(result_dir / "model_v3_oof_predictions.csv", index=False)

    comparison = comparator_table(project_root, metrics, len(feature_columns))
    comparison.to_csv(result_dir / "model_v3_comparison.csv", index=False)

    final_model = make_regressor()
    final_model.fit(x, y)
    full_scores = np.asarray(final_model.predict(x), dtype=float)
    ranking = feature_table[["compound_id", "canonical_smiles", "scaffold"]].copy()
    ranking["candidate_ranking_score_lower_is_better"] = full_scores
    ranking["candidate_priority_rank"] = pd.Series(full_scores).rank(method="min", ascending=True).astype(int)
    ranking["observed_static_mmgbsa_for_audit"] = y
    ranking["score_semantics"] = "model_prediction_of_static_MMGBSA_computational_ranking"
    ranking = ranking.sort_values("candidate_priority_rank")
    ranking.to_csv(result_dir / "candidate_ranking.csv", index=False)

    model_bundle = {
        "model_version": MODEL_VERSION,
        "model": final_model,
        "feature_columns": feature_columns,
        "feature_groups": feature_groups,
        "label": "MMGBSA_dG_Bind_static (lower-is-better; computational)",
        "training_samples": len(samples),
        "scaffold_groups": int(len(np.unique(scaffolds))),
        "chemical_reference_count": len(references),
        "md_features_used": False,
    }
    joblib.dump(model_bundle, model_dir / "model.joblib")

    config = {
        "model_version": MODEL_VERSION,
        "preserved_external_model_version": MODEL_V2_VERSION,
        "algorithm": "LightGBM LGBMRegressor",
        "parameters": final_model.get_params(),
        "random_seed": RANDOM_SEED,
        "evaluation": "Leave-One-Scaffold-Group-Out OOF",
        "top_k": TOP_K,
        "training_samples": len(samples),
        "scaffold_groups": int(len(np.unique(scaffolds))),
        "label": {
            "name": "MMGBSA_dG_Bind_static",
            "direction": "lower_is_better",
            "semantics": "computational ranking label; not biological activity",
            "used_as_feature": False,
        },
        "feature_count": len(feature_columns),
        "feature_groups": {name: len(columns) for name, columns in feature_groups.items()},
        "known_inhibitor_reference_policy": {
            "dataset_layer": "layer_2_atp_synthase_specific",
            "target_contains": "ATP synthase",
            "activity_scope": "direct ATP synthesis IC50 or target-specific IC50",
            "numeric_positive_only": True,
            "low_confidence_excluded": True,
            "deduplicated_reference_structures": len(references),
        },
        "excluded_feature_blocks": {
            "static_mmgbsa": "supervised label; excluded to prevent direct leakage",
            "md_mmgbsa": "only one of 17 internal candidates has mapped same-protocol MD data",
            "md_interactions": "only one of 17 internal candidates has mapped MD interaction data",
        },
        "input_hashes": {
            "samples.csv": sha256(samples_path),
            "ATP_Navigator_Dataset_v1.csv": sha256(dataset_path),
            "admet_features_v0_2.csv": sha256(project_root / "data" / "admet_features_v0_2.csv"),
            "feature_manifest.csv": sha256(project_root / "data" / "dataset_v0.2" / "feature_manifest.csv"),
            "external_priors_internal.csv": sha256(project_root / "results" / "model_v2" / "external_priors_internal.csv"),
            "phase4_interaction_audit.json": sha256(project_root / "results" / "phase4_interaction_audit.json"),
        },
        "environment": {
            "python": os.sys.version.split()[0],
            "rdkit": rdBase.rdkitVersion,
            "lightgbm": lgb.__version__,
            "pandas": pd.__version__,
            "numpy": np.__version__,
            "scipy": scipy_version,
        },
    }
    atomic_write_json(model_dir / "training_config.json", config)
    atomic_write_json(
        model_dir / "feature_list.json",
        {
            "model_version": MODEL_VERSION,
            "feature_count": len(feature_columns),
            "feature_groups": feature_groups,
            "all_features": feature_columns,
        },
    )

    report = report_text(comparison, feature_groups, len(references), binding)
    (project_root / "docs" / "Model_v3_Report.md").write_text(report, encoding="utf-8")

    payload = {
        "model_version": MODEL_VERSION,
        "metrics": metrics,
        "comparison": comparison.to_dict(orient="records"),
        "feature_count": len(feature_columns),
        "feature_groups": {name: len(columns) for name, columns in feature_groups.items()},
        "chemical_reference_count": len(references),
        "md_internal_coverage": int(
            binding.loc[
                binding["is_internal_training_candidate"].eq(True)
                & binding["md_interaction_status"].eq("available_case_evidence")
            ].shape[0]
        ),
    }
    atomic_write_json(result_dir / "model_v3_payload.json", payload)
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["train"])
    parser.add_argument(
        "--project-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
    )
    parser.add_argument(
        "--workspace-root",
        type=Path,
        default=None,
        help="Root containing 表征/运行/作图; defaults to project-root parent.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    project_root = args.project_root.resolve()
    workspace_root = (args.workspace_root or project_root.parent).resolve()
    payload = train(project_root, workspace_root)
    print(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
