"""ATP-Navigator Model v2: task-separated external-knowledge ranking.

Task A trains organism-specific Gram-negative MIC regressors.
Task B trains homogeneous ATP-synthase experimental ranking regressors.
Task C ranks the 17 internal static-MM/GBSA candidates.

MIC, IC50, docking, and MM/GBSA are never placed in a shared label column.
External models provide predictions as auxiliary prior features only. Existing
models and results are read-only comparators; all v2 artifacts are additive.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import shutil
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

if os.name == "nt":
    os.environ.setdefault("WINDIR", os.environ.get("SystemRoot", r"C:\Windows"))

import joblib
import lightgbm as lgb
import numpy as np
import pandas as pd
from rdkit import Chem, DataStructs, rdBase
from rdkit.Chem import Crippen, Descriptors, Lipinski, rdFingerprintGenerator, rdMolDescriptors
from rdkit.Chem.Scaffolds import MurckoScaffold
from scipy.stats import rankdata, spearmanr
from sklearn.metrics import mean_squared_error, ndcg_score
from sklearn.model_selection import GroupKFold, LeaveOneGroupOut


rdBase.DisableLog("rdApp.warning")

RANDOM_SEED = 42
TOP_K = 5
MODEL_VERSION = "ATP-Navigator_Model_v2.0"
EXACT_NUMBER = re.compile(r"^-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?$")

MORGAN_COLUMNS = [f"morgan1024_{index:04d}" for index in range(1024)]
DESCRIPTOR_COLUMNS = [
    "desc_mol_wt",
    "desc_logp",
    "desc_tpsa",
    "desc_hbd",
    "desc_hba",
    "desc_rotatable_bonds",
    "desc_aromatic_ring_count",
    "desc_fraction_csp3",
    "desc_heavy_atom_count",
    "desc_ring_count",
    "desc_formal_charge",
]
STRUCTURE_COLUMNS = MORGAN_COLUMNS + DESCRIPTOR_COLUMNS


@dataclass(frozen=True)
class ExternalTask:
    task_id: str
    task_family: str
    organism: str
    activity_type: str
    unit: str
    target: str | None = None
    data_source: str | None = None
    use_as_internal_prior: bool = False
    prior_feature: str = ""


TASK_A = [
    ExternalTask(
        task_id="A_AB_MIC_UGML",
        task_family="Task A - antibacterial MIC prediction",
        organism="Acinetobacter baumannii",
        activity_type="MIC",
        unit="ug/mL",
        use_as_internal_prior=True,
        prior_feature="prior_task_a_ab_mic_log10_ug_ml",
    ),
    ExternalTask(
        task_id="A_ECOLI_MIC_UGML",
        task_family="Task A - antibacterial MIC prediction",
        organism="Escherichia coli",
        activity_type="MIC",
        unit="ug/mL",
    ),
    ExternalTask(
        task_id="A_PA_MIC_UGML",
        task_family="Task A - antibacterial MIC prediction",
        organism="Pseudomonas aeruginosa",
        activity_type="MIC",
        unit="ug/mL",
    ),
    ExternalTask(
        task_id="A_KP_MIC_UGML",
        task_family="Task A - antibacterial MIC prediction",
        organism="Klebsiella pneumoniae",
        activity_type="MIC",
        unit="ug/mL",
    ),
]

TASK_B = [
    ExternalTask(
        task_id="B_PA_ATP_IC50_UGML_2024",
        task_family="Task B - ATP synthase inhibitor ranking",
        organism="Pseudomonas aeruginosa ATP synthase in E. coli DK8/pASH20 vesicles",
        activity_type="IC50 (ATP synthesis inhibition)",
        unit="ug/mL",
        target="F1Fo-ATP synthase (Fo a/c interface)",
        data_source="Literature (ACS Med Chem Lett 2024)",
        use_as_internal_prior=True,
        prior_feature="prior_task_b_pa_atp_ic50_log10_ug_ml",
    ),
    ExternalTask(
        task_id="B_MTB_ATP_IC50_NM",
        task_family="Task B - ATP synthase inhibitor ranking",
        organism="Mycobacterium tuberculosis",
        activity_type="IC50",
        unit="nM",
        target="F1Fo-ATP synthase (M. tuberculosis)",
        data_source="ChEMBL",
        use_as_internal_prior=True,
        prior_feature="prior_task_b_mtb_atp_ic50_log10_nm",
    ),
    ExternalTask(
        task_id="B_AB_ATP_IC50_NGML_2025",
        task_family="Task B - ATP synthase inhibitor ranking",
        organism="Acinetobacter baumannii ATCC 17978 (inverted membrane vesicles)",
        activity_type="IC50 (ATP synthesis inhibition)",
        unit="ng/mL",
        target="F1Fo-ATP synthase (Fo a/c interface)",
        data_source="Literature (ACS Omega 2025)",
        use_as_internal_prior=True,
        prior_feature="prior_task_b_ab_atp_ic50_log10_ng_ml",
    ),
]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonicalize(smiles: str) -> tuple[str, str]:
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        raise ValueError(f"RDKit could not parse SMILES: {smiles}")
    canonical = Chem.MolToSmiles(mol, canonical=True, isomericSmiles=True)
    scaffold = MurckoScaffold.MurckoScaffoldSmiles(mol=mol, includeChirality=True)
    return canonical, scaffold or canonical


class MolecularFeaturizer:
    def __init__(self) -> None:
        self.generator = rdFingerprintGenerator.GetMorganGenerator(
            radius=2,
            fpSize=1024,
            includeChirality=True,
        )
        self.cache: dict[str, np.ndarray] = {}

    def one(self, canonical_smiles: str) -> np.ndarray:
        if canonical_smiles in self.cache:
            return self.cache[canonical_smiles]
        mol = Chem.MolFromSmiles(canonical_smiles)
        if mol is None:
            raise ValueError(f"Invalid canonical SMILES: {canonical_smiles}")
        fingerprint = self.generator.GetFingerprint(mol)
        bits = np.zeros(1024, dtype=np.float32)
        DataStructs.ConvertToNumpyArray(fingerprint, bits)
        descriptors = np.asarray(
            [
                Descriptors.MolWt(mol),
                Crippen.MolLogP(mol),
                rdMolDescriptors.CalcTPSA(mol),
                Lipinski.NumHDonors(mol),
                Lipinski.NumHAcceptors(mol),
                Lipinski.NumRotatableBonds(mol),
                rdMolDescriptors.CalcNumAromaticRings(mol),
                rdMolDescriptors.CalcFractionCSP3(mol),
                mol.GetNumHeavyAtoms(),
                rdMolDescriptors.CalcNumRings(mol),
                Chem.GetFormalCharge(mol),
            ],
            dtype=np.float32,
        )
        output = np.concatenate([bits, descriptors])
        self.cache[canonical_smiles] = output
        return output

    def frame(self, smiles: Iterable[str]) -> pd.DataFrame:
        matrix = np.vstack([self.one(value) for value in smiles])
        return pd.DataFrame(matrix, columns=STRUCTURE_COLUMNS)


def make_regressor() -> lgb.LGBMRegressor:
    return lgb.LGBMRegressor(
        objective="regression",
        n_estimators=160,
        learning_rate=0.03,
        num_leaves=7,
        max_depth=3,
        min_child_samples=2,
        subsample=0.9,
        colsample_bytree=0.45,
        reg_alpha=0.1,
        reg_lambda=1.0,
        random_state=RANDOM_SEED,
        n_jobs=1,
        deterministic=True,
        force_col_wise=True,
        verbosity=-1,
    )


def ranking_metrics(y_true: np.ndarray, predictions: np.ndarray, k: int = TOP_K) -> dict[str, Any]:
    y = np.asarray(y_true, dtype=float)
    pred = np.asarray(predictions, dtype=float)
    effective_k = min(max(int(k), 1), len(y))
    true_top = set(np.argsort(y, kind="stable")[:effective_k])
    pred_top = set(np.argsort(pred, kind="stable")[:effective_k])
    recovered = len(true_top.intersection(pred_top))
    relevance = len(y) - rankdata(y, method="average") + 1.0
    expected_random = (effective_k * effective_k) / len(y)
    return {
        "spearman": float(spearmanr(y, pred).statistic),
        "rmse": float(math.sqrt(mean_squared_error(y, pred))),
        "ndcg_at_5": float(
            ndcg_score(relevance.reshape(1, -1), (-pred).reshape(1, -1), k=effective_k)
        ),
        "top_k": effective_k,
        "recovered_hits": recovered,
        "true_hits": effective_k,
        "top_k_enrichment": float(recovered / expected_random),
        "hit_recovery": float(recovered / effective_k),
    }


def filter_external_task(dataset: pd.DataFrame, task: ExternalTask) -> pd.DataFrame:
    layer = "layer_1_general_antibacterial" if task.task_id.startswith("A_") else "layer_2_atp_synthase_specific"
    selected = dataset.loc[
        dataset["dataset_layer"].eq(layer)
        & dataset["organism"].eq(task.organism)
        & dataset["activity_type"].eq(task.activity_type)
        & dataset["unit"].eq(task.unit)
    ].copy()
    if task.target is not None:
        selected = selected.loc[selected["target"].eq(task.target)].copy()
    if task.data_source is not None:
        selected = selected.loc[selected["data_source"].eq(task.data_source)].copy()
    selected = selected.loc[selected["activity_value"].map(lambda value: bool(EXACT_NUMBER.fullmatch(value)))].copy()
    selected["label_raw"] = selected["activity_value"].astype(float)
    selected = selected.loc[selected["label_raw"].gt(0)].copy()
    selected["label"] = np.log10(selected["label_raw"])

    canonical: list[str] = []
    scaffolds: list[str] = []
    for smiles in selected["canonical_smiles"]:
        normalized, scaffold = canonicalize(smiles)
        canonical.append(normalized)
        scaffolds.append(scaffold)
    selected["rdkit_canonical_smiles"] = canonical
    selected["scaffold"] = scaffolds

    rows: list[dict[str, Any]] = []
    for canonical_smiles, group in selected.groupby("rdkit_canonical_smiles", sort=True):
        _, scaffold = canonicalize(canonical_smiles)
        rows.append(
            {
                "task_id": task.task_id,
                "task_family": task.task_family,
                "canonical_smiles": canonical_smiles,
                "scaffold": scaffold,
                "compound_ids": ";".join(sorted(set(group["compound_id"]))),
                "source_records": len(group),
                "label": float(group["label"].median()),
                "label_raw_median": float(group["label_raw"].median()),
                "label_transform": f"log10({task.activity_type} in {task.unit})",
                "organism": task.organism,
                "activity_type": task.activity_type,
                "unit": task.unit,
            }
        )
    return pd.DataFrame(rows)


def external_group_oof(
    view: pd.DataFrame,
    featurizer: MolecularFeaturizer,
) -> tuple[np.ndarray, np.ndarray, str]:
    x = featurizer.frame(view["canonical_smiles"])
    y = view["label"].to_numpy(dtype=float)
    groups = view["scaffold"].to_numpy(dtype=str)
    unique_groups = np.unique(groups)
    if len(unique_groups) < 3:
        raise ValueError(f"Task {view['task_id'].iloc[0]} has fewer than 3 scaffold groups")
    n_splits = min(5, len(unique_groups))
    splitter = GroupKFold(n_splits=n_splits)
    predictions = np.full(len(view), np.nan, dtype=float)
    fold_ids = np.full(len(view), -1, dtype=int)
    for fold_id, (train_index, test_index) in enumerate(splitter.split(x, y, groups), start=1):
        model = make_regressor()
        model.fit(x.iloc[train_index], y[train_index])
        predictions[test_index] = model.predict(x.iloc[test_index])
        fold_ids[test_index] = fold_id
    if np.isnan(predictions).any() or (fold_ids < 0).any():
        raise RuntimeError("External OOF prediction is incomplete")
    return predictions, fold_ids, f"scaffold_group_kfold_{n_splits}"


def internal_logo_oof(
    x: pd.DataFrame,
    y: np.ndarray,
    groups: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    predictions = np.full(len(y), np.nan, dtype=float)
    fold_ids = np.full(len(y), -1, dtype=int)
    splitter = LeaveOneGroupOut()
    for fold_id, (train_index, test_index) in enumerate(splitter.split(x, y, groups), start=1):
        model = make_regressor()
        model.fit(x.iloc[train_index], y[train_index])
        predictions[test_index] = model.predict(x.iloc[test_index])
        fold_ids[test_index] = fold_id
    if np.isnan(predictions).any() or (fold_ids < 0).any():
        raise RuntimeError("Internal OOF prediction is incomplete")
    return predictions, fold_ids


def legacy_comparison_rows(project_root: Path) -> list[dict[str, Any]]:
    payload = json.loads((project_root / "results" / "phase3_results_payload.json").read_text(encoding="utf-8"))
    rows = []
    for source in payload["comparison_rows"]:
        rows.append(
            {
                "model_id": source["model_id"],
                "model": source["model"],
                "dataset_version": source["dataset_version"],
                "evaluation_samples": source["evaluation_samples"],
                "scaffold_groups": 11,
                "benchmark_protocol": source["benchmark_protocol"],
                "feature_set": source["feature_set"],
                "feature_count": source["feature_count"],
                "spearman": source["spearman"],
                "rmse": source["rmse"],
                "ndcg_at_5": source["ndcg"],
                "top_k": source["top_k"],
                "recovered_hits": source["recovered_hits"],
                "true_hits": source["true_hits"],
                "top_k_enrichment": source["top_k_enrichment"],
                "hit_recovery": source["hit_recovery"],
                "status": "preserved_comparator",
                "notes": source["notes"],
            }
        )
    return rows


def prepare_audit(project_root: Path) -> tuple[pd.DataFrame, pd.DataFrame, list[dict[str, Any]]]:
    dataset_path = project_root / "data" / "dataset_v1.0" / "ATP_Navigator_Dataset_v1.csv"
    dataset = pd.read_csv(dataset_path, dtype=str, keep_default_na=False)
    internal = pd.read_csv(project_root / "data" / "dataset_v0.2" / "samples.csv", low_memory=False)
    if internal["canonical_smiles"].duplicated().any() or internal["compound_id"].duplicated().any():
        raise ValueError("Internal Dataset v0.2 is not unique by compound and canonical SMILES")
    internal_canonical = {canonicalize(value)[0] for value in internal["canonical_smiles"]}

    task_views = []
    summary = []
    for task in [*TASK_A, *TASK_B]:
        view = filter_external_task(dataset, task)
        overlap = len(set(view["canonical_smiles"]).intersection(internal_canonical))
        if overlap:
            view = view.loc[~view["canonical_smiles"].isin(internal_canonical)].copy()
        task_views.append(view)
        summary.append(
            {
                "task_id": task.task_id,
                "task_family": task.task_family,
                "raw_compatible_records": int(view["source_records"].sum()),
                "deduplicated_compounds": len(view),
                "scaffold_groups": int(view["scaffold"].nunique()),
                "activity_type": task.activity_type,
                "organism": task.organism,
                "unit": task.unit,
                "label_transform": view["label_transform"].iloc[0] if len(view) else "",
                "internal_structure_overlap_removed": overlap,
                "used_as_internal_prior": task.use_as_internal_prior,
                "prior_feature": task.prior_feature,
            }
        )
    return dataset, internal, summary


def train(project_root: Path) -> dict[str, Any]:
    dataset_path = project_root / "data" / "dataset_v1.0" / "ATP_Navigator_Dataset_v1.csv"
    dataset = pd.read_csv(dataset_path, dtype=str, keep_default_na=False)
    samples_path = project_root / "data" / "dataset_v0.2" / "samples.csv"
    samples = pd.read_csv(samples_path, low_memory=False)
    feature_manifest_path = project_root / "data" / "dataset_v0.2" / "feature_manifest.csv"
    feature_manifest = pd.read_csv(feature_manifest_path, dtype=str, keep_default_na=False)
    model2_columns = feature_manifest.loc[
        feature_manifest["used_in_model2"].str.lower().eq("true"), "feature"
    ].tolist()
    if len(model2_columns) != 1089:
        raise ValueError(f"Expected 1089 preserved Model 2 features, found {len(model2_columns)}")
    if any(column not in samples.columns for column in [*STRUCTURE_COLUMNS, *model2_columns]):
        raise ValueError("Dataset v0.2 does not contain the required v2 feature columns")

    internal_canonical = {canonicalize(value)[0] for value in samples["canonical_smiles"]}
    featurizer = MolecularFeaturizer()
    external_metrics: list[dict[str, Any]] = []
    external_oof_rows: list[dict[str, Any]] = []
    task_summary: list[dict[str, Any]] = []
    prior_predictions: dict[str, np.ndarray] = {}
    external_models: dict[str, Any] = {}

    canonical_internal = [canonicalize(value)[0] for value in samples["canonical_smiles"]]
    internal_structure_matrix = featurizer.frame(canonical_internal)

    for task in [*TASK_A, *TASK_B]:
        view = filter_external_task(dataset, task)
        overlap_mask = view["canonical_smiles"].isin(internal_canonical)
        overlap_count = int(overlap_mask.sum())
        view = view.loc[~overlap_mask].reset_index(drop=True)
        if len(view) < 8:
            raise ValueError(f"Task {task.task_id} has too few compatible compounds: {len(view)}")
        predictions, fold_ids, split_name = external_group_oof(view, featurizer)
        metrics = ranking_metrics(view["label"].to_numpy(dtype=float), predictions)
        metrics_row = {
            "task_id": task.task_id,
            "task_family": task.task_family,
            "model": "LightGBM regression",
            "samples": len(view),
            "scaffold_groups": int(view["scaffold"].nunique()),
            "feature_count": len(STRUCTURE_COLUMNS),
            "features": "Morgan1024 + RDKit11",
            "label": view["label_transform"].iloc[0],
            "split": split_name,
            **metrics,
        }
        external_metrics.append(metrics_row)
        task_summary.append(
            {
                "task_id": task.task_id,
                "task_family": task.task_family,
                "raw_compatible_records": int(view["source_records"].sum()),
                "deduplicated_compounds": len(view),
                "scaffold_groups": int(view["scaffold"].nunique()),
                "activity_type": task.activity_type,
                "organism": task.organism,
                "unit": task.unit,
                "label_transform": view["label_transform"].iloc[0],
                "internal_structure_overlap_removed": overlap_count,
                "used_as_internal_prior": task.use_as_internal_prior,
                "prior_feature": task.prior_feature,
            }
        )
        for index, row in view.iterrows():
            external_oof_rows.append(
                {
                    "task_id": task.task_id,
                    "compound_ids": row["compound_ids"],
                    "canonical_smiles": row["canonical_smiles"],
                    "scaffold": row["scaffold"],
                    "fold_id": int(fold_ids[index]),
                    "observed_log_label": float(row["label"]),
                    "predicted_log_label": float(predictions[index]),
                    "label_transform": row["label_transform"],
                }
            )

        x_external = featurizer.frame(view["canonical_smiles"])
        full_model = make_regressor()
        full_model.fit(x_external, view["label"].to_numpy(dtype=float))
        external_models[task.task_id] = {
            "model": full_model,
            "feature_columns": STRUCTURE_COLUMNS,
                "task": asdict(task),
            "training_samples": len(view),
            "scaffold_groups": int(view["scaffold"].nunique()),
            "label_transform": view["label_transform"].iloc[0],
        }
        if task.use_as_internal_prior:
            prior_predictions[task.prior_feature] = np.asarray(
                full_model.predict(internal_structure_matrix), dtype=float
            )

    expected_priors = [task.prior_feature for task in [*TASK_A, *TASK_B] if task.use_as_internal_prior]
    if sorted(prior_predictions) != sorted(expected_priors):
        raise RuntimeError("External prior feature construction is incomplete")

    x_v2a = samples[STRUCTURE_COLUMNS].astype(float).reset_index(drop=True)
    x_v2b = samples[model2_columns].astype(float).reset_index(drop=True).copy()
    for feature in expected_priors:
        x_v2b[feature] = prior_predictions[feature]

    y = samples["label_score"].to_numpy(dtype=float)
    groups = samples["scaffold"].astype(str).to_numpy()
    predictions_a, folds_a = internal_logo_oof(x_v2a, y, groups)
    predictions_b, folds_b = internal_logo_oof(x_v2b, y, groups)
    if not np.array_equal(folds_a, folds_b):
        raise RuntimeError("Model v2-A and v2-B did not use identical scaffold folds")

    metrics_a = ranking_metrics(y, predictions_a)
    metrics_b = ranking_metrics(y, predictions_b)
    comparison = legacy_comparison_rows(project_root)
    comparison.extend(
        [
            {
                "model_id": "Model v2-A",
                "model": "lightgbm_structure_only_v2",
                "dataset_version": "dataset_v1.0 + internal dataset_v0.2",
                "evaluation_samples": len(samples),
                "scaffold_groups": int(samples["scaffold"].nunique()),
                "benchmark_protocol": "scaffold_grouped_leave_one_group_out",
                "feature_set": "Morgan1024 + RDKit11",
                "feature_count": len(STRUCTURE_COLUMNS),
                **metrics_a,
                "status": "new_v2_result",
                "notes": "Structure-only ablation; target is internal static MM/GBSA, not biological activity.",
            },
            {
                "model_id": "Model v2-B",
                "model": "lightgbm_enhanced_plus_external_priors_v2",
                "dataset_version": "dataset_v1.0 + internal dataset_v0.2",
                "evaluation_samples": len(samples),
                "scaffold_groups": int(samples["scaffold"].nunique()),
                "benchmark_protocol": "scaffold_grouped_leave_one_group_out",
                "feature_set": "Preserved Model 2 features + 4 external task priors",
                "feature_count": len(x_v2b.columns),
                **metrics_b,
                "status": "new_v2_result",
                "notes": "External models are label-independent of Task C; priors are auxiliary features, not merged labels.",
            },
        ]
    )

    internal_oof = []
    for model_id, model_name, predictions, folds in [
        ("Model v2-A", "lightgbm_structure_only_v2", predictions_a, folds_a),
        ("Model v2-B", "lightgbm_enhanced_plus_external_priors_v2", predictions_b, folds_b),
    ]:
        for index, sample in samples.iterrows():
            internal_oof.append(
                {
                    "compound_id": sample["compound_id"],
                    "historical_alias": sample["historical_alias"],
                    "canonical_smiles": sample["canonical_smiles"],
                    "scaffold": sample["scaffold"],
                    "model_id": model_id,
                    "model": model_name,
                    "fold_id": int(folds[index]),
                    "observed_mmgbsa": float(y[index]),
                    "predicted_score": float(predictions[index]),
                    "score_direction": "lower_is_better",
                }
            )

    internal_prior_rows = []
    for index, sample in samples.iterrows():
        row = {
            "compound_id": sample["compound_id"],
            "historical_alias": sample["historical_alias"],
            "canonical_smiles": sample["canonical_smiles"],
            "scaffold": sample["scaffold"],
        }
        row.update({feature: float(prior_predictions[feature][index]) for feature in expected_priors})
        internal_prior_rows.append(row)

    model_a = make_regressor()
    model_a.fit(x_v2a, y)
    model_b = make_regressor()
    model_b.fit(x_v2b, y)

    models_final = project_root / "models" / "model_v2"
    results_final = project_root / "results" / "model_v2"
    if models_final.exists() or results_final.exists():
        raise FileExistsError("Model v2 output already exists; existing v2 artifacts were not overwritten")
    models_final.parent.mkdir(parents=True, exist_ok=True)
    results_final.parent.mkdir(parents=True, exist_ok=True)

    temp_models = Path(tempfile.mkdtemp(prefix=".model_v2-", dir=models_final.parent))
    temp_results = Path(tempfile.mkdtemp(prefix=".model_v2-", dir=results_final.parent))
    try:
        for task_id, bundle in external_models.items():
            joblib.dump(bundle, temp_models / f"{task_id.lower()}.joblib")
        joblib.dump(
            {
                "model": model_a,
                "model_version": MODEL_VERSION,
                "model_id": "Model v2-A",
                "feature_columns": STRUCTURE_COLUMNS,
                "target": "internal_static_MMGBSA",
            },
            temp_models / "model_v2_a_structure_only.joblib",
        )
        joblib.dump(
            {
                "model": model_b,
                "model_version": MODEL_VERSION,
                "model_id": "Model v2-B",
                "feature_columns": list(x_v2b.columns),
                "external_prior_features": expected_priors,
                "external_model_files": [f"{task.task_id.lower()}.joblib" for task in [*TASK_A, *TASK_B]],
                "target": "internal_static_MMGBSA",
            },
            temp_models / "model_v2_b_external_enhanced.joblib",
        )

        payload = {
            "model_version": MODEL_VERSION,
            "task_separation": {
                "Task A": "organism-specific log10 MIC regression in ug/mL",
                "Task B": "assay/source/unit-specific log10 ATP synthase IC50 regression/ranking",
                "Task C": "internal static MMGBSA candidate ranking",
                "prohibited": "No shared MIC/IC50/MMGBSA label",
            },
            "table_headers": {
                "task_summary": list(task_summary[0].keys()),
                "external_metrics": list(external_metrics[0].keys()),
                "external_oof": list(external_oof_rows[0].keys()),
                "internal_comparison": list(comparison[0].keys()),
                "internal_oof": list(internal_oof[0].keys()),
                "internal_priors": list(internal_prior_rows[0].keys()),
            },
            "tables": {
                "task_summary": task_summary,
                "external_metrics": external_metrics,
                "external_oof": external_oof_rows,
                "internal_comparison": comparison,
                "internal_oof": internal_oof,
                "internal_priors": internal_prior_rows,
            },
            "parameters": make_regressor().get_params(),
            "data_audit": {
                "dataset_v1_sha256": sha256(dataset_path),
                "dataset_v0_2_sha256": sha256(samples_path),
                "feature_manifest_sha256": sha256(feature_manifest_path),
                "dataset_v1_rows": len(dataset),
                "internal_samples": len(samples),
                "internal_unique_smiles": samples["canonical_smiles"].nunique(),
                "internal_scaffolds": samples["scaffold"].nunique(),
                "external_internal_structure_overlap": 0,
            },
            "software": {
                "python": os.sys.version.split()[0],
                "pandas": pd.__version__,
                "numpy": np.__version__,
                "rdkit": rdBase.rdkitVersion,
                "lightgbm": lgb.__version__,
            },
        }
        (temp_results / "model_v2_payload.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        temp_models.rename(models_final)
        temp_results.rename(results_final)
    except Exception:
        shutil.rmtree(temp_models, ignore_errors=True)
        shutil.rmtree(temp_results, ignore_errors=True)
        raise
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Train task-separated ATP-Navigator Model v2")
    parser.add_argument("command", choices=("audit", "train"))
    parser.add_argument(
        "--project-root",
        default=str(Path(__file__).resolve().parents[1]),
        help="ATP-Navigator project root",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    project_root = Path(args.project_root).resolve()
    if args.command == "audit":
        _, _, summary = prepare_audit(project_root)
        print(json.dumps({"model_version": MODEL_VERSION, "tasks": summary}, ensure_ascii=False, indent=2))
        return 0
    payload = train(project_root)
    print(
        json.dumps(
            {
                "model_version": payload["model_version"],
                "external_tasks": len(payload["tables"]["external_metrics"]),
                "internal_models": 2,
                "results": str(project_root / "results" / "model_v2"),
                "models": str(project_root / "models" / "model_v2"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
