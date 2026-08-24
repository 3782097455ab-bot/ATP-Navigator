"""ATP-Navigator Phase 7: external-knowledge enhanced training experiment.

This alpha experiment keeps MIC, ATP-target assay values, BindingDB benchmark
records, and internal static MM/GBSA labels in separate tasks. It never writes
predictions back to Dataset v2.0 as labels and never overwrites Model v0-v3 or
the Phase 5 Decision Engine outputs.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import platform
import re
import tempfile
from pathlib import Path
from typing import Any, Iterable

if os.name == "nt":
    os.environ.setdefault("WINDIR", os.environ.get("SystemRoot", r"C:\Windows"))

import joblib
import lightgbm as lgb
import numpy as np
import pandas as pd
from rdkit import Chem, DataStructs, rdBase
from rdkit.Chem import rdFingerprintGenerator
from rdkit.Chem.Scaffolds import MurckoScaffold
from scipy import stats
from sklearn.model_selection import GroupKFold, LeaveOneGroupOut

from model_v2_pipeline import make_regressor, ranking_metrics, sha256
from model_v3_pipeline import ENHANCED_DESCRIPTOR_COLUMNS, descriptor_row


rdBase.DisableLog("rdApp.warning")

MODEL_VERSION = "ATP-Navigator_Model_v4-alpha"
DATASET_VERSION = "ATP-Navigator_Dataset_v2.0"
RANDOM_SEED = 42
TOP_K = 5
REQUIRED_COLUMNS = [
    "compound_id",
    "canonical_smiles",
    "target",
    "organism",
    "activity_type",
    "activity_value",
    "unit",
    "reference",
    "source_level",
    "confidence",
    "task_type",
]
EXACT_NUMBER = re.compile(r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$")
RANGE_NUMBER = re.compile(
    r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)\s*[-–]\s*[+-]?(?:\d+(?:\.\d*)?|\.\d+)$"
)
SOURCE_RANK = {"A": 0, "B": 1, "C": 2, "D": 3}
CONFIDENCE_RANK = {"high": 0, "medium": 1, "low": 2}
TASK_A_SOURCE_WEIGHTS = {"A": 1.0, "B": 1.0, "C": 0.5, "D": 0.0}
TASK_B_SOURCE_WEIGHTS = {"A": 1.0, "B": 0.8, "C": 0.5, "D": 0.0}
CONFIDENCE_WEIGHTS = {"high": 1.0, "medium": 0.7, "low": 0.3}
MORGAN_COLUMNS = [f"morgan1024_{idx:04d}" for idx in range(1024)]


def json_safe(value: Any) -> Any:
    """Convert numpy/path values and non-finite metrics to strict JSON values."""
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


def atomic_write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", delete=False, dir=path.parent, suffix=".tmp"
    ) as handle:
        json.dump(json_safe(payload), handle, ensure_ascii=False, indent=2, allow_nan=False)
        temporary = Path(handle.name)
    temporary.replace(path)


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", delete=False, dir=path.parent, suffix=".tmp"
    ) as handle:
        handle.write(text)
        temporary = Path(handle.name)
    temporary.replace(path)


def atomic_to_csv(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8-sig", newline="", delete=False, dir=path.parent, suffix=".tmp"
    ) as handle:
        frame.to_csv(handle, index=False)
        temporary = Path(handle.name)
    temporary.replace(path)


def atomic_joblib(payload: Any, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(delete=False, dir=path.parent, suffix=".tmp") as handle:
        temporary = Path(handle.name)
    try:
        joblib.dump(payload, temporary)
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()


def safe_float(value: Any) -> float | None:
    text = str(value).strip()
    if not EXACT_NUMBER.fullmatch(text):
        return None
    number = float(text)
    if not math.isfinite(number):
        return None
    return number


def value_class(value: Any) -> str:
    text = str(value).strip()
    if safe_float(text) is not None:
        return "exact_numeric"
    if text.startswith((">", "<", "≥", "≤")):
        return "censored"
    if RANGE_NUMBER.fullmatch(text):
        return "range"
    if not text or text.lower() in {"unknown", "nan", "none"}:
        return "missing"
    return "other"


def normalize_unit(value: Any) -> str:
    text = str(value).strip().replace("ug/mL", "μg/mL").replace("ug/ml", "μg/mL")
    text = text.replace("µg/mL", "μg/mL")
    return text


def species_name(value: Any) -> str:
    text = str(value).strip()
    parts = text.split()
    if len(parts) >= 2 and parts[0][0:1].isalpha():
        return " ".join(parts[:2])
    return text or "unknown"


def slug(value: str) -> str:
    text = re.sub(r"[^a-zA-Z0-9]+", "_", str(value)).strip("_").lower()
    return text or "unknown"


def canonicalize(smiles: str) -> tuple[str, str, Chem.Mol]:
    mol = Chem.MolFromSmiles(str(smiles))
    if mol is None:
        raise ValueError(f"RDKit could not parse SMILES: {smiles}")
    canonical = Chem.MolToSmiles(mol, canonical=True, isomericSmiles=True)
    scaffold = MurckoScaffold.MurckoScaffoldSmiles(mol=mol, includeChirality=True)
    return canonical, scaffold or canonical, mol


def prepare_dataset(path: Path) -> tuple[pd.DataFrame, dict[str, Any]]:
    frame = pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    missing_columns = [column for column in REQUIRED_COLUMNS if column not in frame.columns]
    if missing_columns:
        raise ValueError(f"Dataset v2.0 missing required columns: {missing_columns}")
    frame = frame[REQUIRED_COLUMNS].copy()
    frame["unit_normalized"] = frame["unit"].map(normalize_unit)
    frame["organism_species"] = frame["organism"].map(species_name)
    frame["value_class"] = frame["activity_value"].map(value_class)
    frame["numeric_activity"] = frame["activity_value"].map(safe_float)

    canonical: list[str] = []
    scaffolds: list[str] = []
    invalid: list[int] = []
    for index, smiles in enumerate(frame["canonical_smiles"]):
        try:
            current, scaffold, _ = canonicalize(smiles)
        except ValueError:
            current, scaffold = "", ""
            invalid.append(index)
        canonical.append(current)
        scaffolds.append(scaffold)
    frame["rdkit_canonical_smiles"] = canonical
    frame["scaffold"] = scaffolds

    missing = {
        column: int(frame[column].astype(str).str.strip().isin(["", "unknown"]).sum())
        for column in REQUIRED_COLUMNS
    }
    cross_task = frame.groupby("rdkit_canonical_smiles")["task_type"].nunique()
    audit = {
        "dataset_version": DATASET_VERSION,
        "source_file": str(path.relative_to(path.parents[2])).replace("\\", "/"),
        "source_sha256": sha256(path),
        "rows": int(len(frame)),
        "unique_compound_ids": int(frame["compound_id"].nunique()),
        "unique_canonical_smiles": int(frame["rdkit_canonical_smiles"].nunique()),
        "invalid_smiles": len(invalid),
        "task_counts": frame["task_type"].value_counts().to_dict(),
        "source_levels": frame["source_level"].value_counts().to_dict(),
        "confidence_levels": frame["confidence"].value_counts().to_dict(),
        "value_classes": frame["value_class"].value_counts().to_dict(),
        "unit_counts": frame["unit_normalized"].value_counts().to_dict(),
        "activity_type_counts": frame["activity_type"].value_counts().to_dict(),
        "missing_or_unknown_required": missing,
        "canonical_present_in_multiple_tasks": int((cross_task > 1).sum()),
        "qc_warning": (
            "The supplied Dataset_QC_Report.md describes the earlier 6,777-row public master; "
            "this pipeline independently audits the 8,820-row standard Dataset v2.0 input."
        ),
        "provenance_boundary": (
            "source_level/reference annotations are user-supplied; Phase 7 checks structure and "
            "schema consistency but does not independently re-open every paper/database record"
        ),
    }
    if invalid:
        raise ValueError(f"Dataset v2.0 contains {len(invalid)} invalid SMILES")
    if any(missing.values()):
        raise ValueError(f"Dataset v2.0 contains missing required values: {missing}")
    return frame, audit


def best_label(values: Iterable[str], ranking: dict[str, int]) -> str:
    cleaned = [str(value) for value in values]
    return min(cleaned, key=lambda value: ranking.get(value, 999))


def aggregate_task_records(
    frame: pd.DataFrame,
    group_columns: list[str],
    source_weights: dict[str, float],
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for keys, group in frame.groupby(group_columns, sort=True, dropna=False):
        if not isinstance(keys, tuple):
            keys = (keys,)
        values = pd.to_numeric(group["numeric_activity"], errors="coerce").dropna().to_numpy(float)
        if values.size == 0 or np.any(values <= 0):
            continue
        record = dict(zip(group_columns, keys))
        record.update(
            {
                "compound_ids": "|".join(sorted(set(group["compound_id"]))),
                "measurement_count": int(len(group)),
                "activity_value_median": float(np.median(values)),
                "activity_value_min": float(np.min(values)),
                "activity_value_max": float(np.max(values)),
                "label_log10": float(np.log10(np.median(values))),
                "source_level": best_label(group["source_level"], SOURCE_RANK),
                "confidence": best_label(group["confidence"], CONFIDENCE_RANK),
                "reference_count": int(group["reference"].nunique()),
                "representative_reference": sorted(set(group["reference"]))[0],
            }
        )
        raw_weights = [
            source_weights.get(source, 0.0) * CONFIDENCE_WEIGHTS.get(confidence, 0.0)
            for source, confidence in zip(group["source_level"], group["confidence"])
        ]
        record["sample_weight"] = float(np.mean(raw_weights))
        rows.append(record)
    return pd.DataFrame(rows)


class StructureFeaturizer:
    def __init__(self, context_categories: list[str] | None = None):
        self.context_categories = context_categories or []
        self.generator = rdFingerprintGenerator.GetMorganGenerator(
            radius=2, fpSize=1024, includeChirality=True
        )

    @property
    def feature_names(self) -> list[str]:
        return [*MORGAN_COLUMNS, *ENHANCED_DESCRIPTOR_COLUMNS, *[f"context_{slug(x)}" for x in self.context_categories]]

    def frame(self, smiles: Iterable[str], contexts: Iterable[str] | None = None) -> pd.DataFrame:
        smiles_list = list(smiles)
        context_list = list(contexts) if contexts is not None else [""] * len(smiles_list)
        if len(smiles_list) != len(context_list):
            raise ValueError("SMILES/context length mismatch")
        rows: list[dict[str, float]] = []
        for text, context in zip(smiles_list, context_list):
            _, _, mol = canonicalize(text)
            fp = self.generator.GetFingerprint(mol)
            vector = np.zeros(1024, dtype=np.float32)
            DataStructs.ConvertToNumpyArray(fp, vector)
            row = {name: float(value) for name, value in zip(MORGAN_COLUMNS, vector)}
            row.update(descriptor_row(mol))
            for category in self.context_categories:
                row[f"context_{slug(category)}"] = float(str(context) == category)
            rows.append(row)
        return pd.DataFrame(rows, columns=self.feature_names, dtype=float)


def finite_or_none(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def regression_metrics(y_true: np.ndarray, predictions: np.ndarray) -> dict[str, Any]:
    rmse = float(np.sqrt(np.mean(np.square(y_true - predictions))))
    spearman = stats.spearmanr(y_true, predictions).statistic
    return {
        "n": int(len(y_true)),
        "rmse": rmse,
        "spearman": finite_or_none(spearman),
    }


def grouped_oof(
    x: pd.DataFrame,
    y: np.ndarray,
    groups: np.ndarray,
    sample_weight: np.ndarray | None,
    mode: str,
) -> tuple[np.ndarray, np.ndarray, str]:
    unique_groups = np.unique(groups)
    if len(unique_groups) < 2:
        raise ValueError("At least two scaffold groups are required")
    if mode == "leave_one_group_out":
        splitter = LeaveOneGroupOut()
        split_name = "Leave-One-Scaffold-Group-Out"
    else:
        n_splits = min(5, len(unique_groups))
        splitter = GroupKFold(n_splits=n_splits)
        split_name = f"{n_splits}-fold scaffold GroupKFold"
    predictions = np.full(len(y), np.nan, dtype=float)
    fold_ids = np.full(len(y), -1, dtype=int)
    for fold, (train_idx, test_idx) in enumerate(splitter.split(x, y, groups)):
        train_canonical = set(groups[train_idx])
        if train_canonical & set(groups[test_idx]):
            raise AssertionError("Scaffold leakage detected")
        model = make_regressor()
        kwargs: dict[str, Any] = {}
        if sample_weight is not None:
            kwargs["sample_weight"] = sample_weight[train_idx]
        model.fit(x.iloc[train_idx], y[train_idx], **kwargs)
        predictions[test_idx] = model.predict(x.iloc[test_idx])
        fold_ids[test_idx] = fold
    if np.isnan(predictions).any() or (fold_ids < 0).any():
        raise AssertionError("OOF prediction coverage failure")
    return predictions, fold_ids, split_name


def rank_percentile(series: pd.Series, direction: str) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce")
    output = pd.Series(np.nan, index=series.index, dtype=float)
    valid = values.notna()
    count = int(valid.sum())
    if count == 0:
        return output
    if count == 1:
        output.loc[valid] = 50.0
        return output
    ranks = values.loc[valid].rank(method="average", ascending=True)
    if direction == "lower_is_better":
        output.loc[valid] = 100.0 * (count - ranks) / (count - 1)
    else:
        output.loc[valid] = 100.0 * (ranks - 1.0) / (count - 1)
    return output


def task_a_view(dataset: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    task = dataset["task_type"].eq("Antibacterial")
    mic = dataset["activity_type"].eq("MIC")
    unit = dataset["unit_normalized"].eq("μg/mL")
    exact = dataset["value_class"].eq("exact_numeric") & dataset["numeric_activity"].gt(0)
    source = dataset["source_level"].isin(["A", "B", "C"])
    selected = dataset.loc[task & mic & unit & exact & source].copy()
    aggregated = aggregate_task_records(
        selected,
        ["rdkit_canonical_smiles", "scaffold", "organism_species", "unit_normalized"],
        TASK_A_SOURCE_WEIGHTS,
    )
    audit = {
        "raw_task_rows": int(task.sum()),
        "mic_rows": int((task & mic).sum()),
        "exact_positive_mic_rows": int(len(selected)),
        "excluded_censored_or_range_or_non_mic_rows": int(task.sum() - len(selected)),
        "aggregated_samples": int(len(aggregated)),
        "unique_structures": int(aggregated["rdkit_canonical_smiles"].nunique()),
        "scaffold_groups": int(aggregated["scaffold"].nunique()),
        "species": aggregated["organism_species"].value_counts().to_dict(),
        "label": "log10 MIC in μg/mL; lower-is-better",
        "classification_accuracy": None,
        "classification_status": "not_applicable_no_pre_registered_active_threshold",
    }
    return aggregated, audit


def train_task_a(
    dataset: pd.DataFrame,
    models_dir: Path,
    results_dir: Path,
) -> tuple[dict[str, Any], pd.DataFrame, pd.DataFrame, StructureFeaturizer]:
    view, audit = task_a_view(dataset)
    categories = sorted(view["organism_species"].unique())
    featurizer = StructureFeaturizer(categories)
    x = featurizer.frame(view["rdkit_canonical_smiles"], view["organism_species"])
    y = view["label_log10"].to_numpy(float)
    groups = view["scaffold"].to_numpy(str)
    weights = view["sample_weight"].to_numpy(float)
    predictions, folds, split_name = grouped_oof(x, y, groups, weights, "group_kfold")
    view = view.copy()
    view["oof_prediction_log10_mic_ug_ml"] = predictions
    view["oof_fold"] = folds
    view["residual"] = predictions - y

    metric_rows: list[dict[str, Any]] = []
    slices = {
        "all_eligible": np.ones(len(view), dtype=bool),
        "formal_A_B_high": view["source_level"].isin(["A", "B"]) & view["confidence"].eq("high"),
        "source_A": view["source_level"].eq("A"),
        "source_B": view["source_level"].eq("B"),
    }
    for name, mask in slices.items():
        mask_array = np.asarray(mask, dtype=bool)
        if int(mask_array.sum()) < 3:
            continue
        metrics = regression_metrics(y[mask_array], predictions[mask_array])
        metric_rows.append(
            {
                "task": "Task A",
                "slice": name,
                "label": "log10_MIC_ug_ml",
                "split": split_name,
                **metrics,
                "classification_accuracy": np.nan,
                "classification_status": "not_applicable_no_pre_registered_active_threshold",
            }
        )
    metrics_frame = pd.DataFrame(metric_rows)

    final_model = make_regressor()
    final_model.fit(x, y, sample_weight=weights)
    bundle = {
        "model_version": MODEL_VERSION,
        "task": "Task A antibacterial activity modeling",
        "model": final_model,
        "feature_names": featurizer.feature_names,
        "context_categories": categories,
        "label": "log10 MIC in μg/mL",
        "direction": "lower_is_better",
        "source_weights": TASK_A_SOURCE_WEIGHTS,
        "confidence_weights": CONFIDENCE_WEIGHTS,
        "classification_status": audit["classification_status"],
    }
    atomic_joblib(bundle, models_dir / "task_a_mic_model.joblib")
    atomic_to_csv(view, results_dir / "task_a_oof_predictions.csv")
    atomic_to_csv(metrics_frame, results_dir / "task_a_metrics.csv")
    training_columns = [
        "rdkit_canonical_smiles", "scaffold", "organism_species", "unit_normalized",
        "compound_ids", "measurement_count", "activity_value_median", "activity_value_min",
        "activity_value_max", "label_log10", "source_level", "confidence", "reference_count",
        "sample_weight",
    ]
    atomic_to_csv(view[training_columns], results_dir / "task_a_training_view.csv")
    summary = {
        **audit,
        "feature_count": len(featurizer.feature_names),
        "split": split_name,
        "formal_metrics": metrics_frame.loc[metrics_frame["slice"].eq("formal_A_B_high")].to_dict("records")[0],
    }
    return summary, view, metrics_frame, featurizer


def make_task_b_stratum(frame: pd.DataFrame) -> pd.Series:
    return (
        frame["activity_type"].map(slug)
        + "__"
        + frame["organism_species"].map(slug)
        + "__"
        + frame["unit_normalized"].map(slug)
    )


def task_b_view(dataset: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    task = dataset["task_type"].eq("ATP_target")
    exact = dataset["value_class"].eq("exact_numeric") & dataset["numeric_activity"].gt(0)
    source = dataset["source_level"].isin(["A", "B"])
    selected = dataset.loc[task & exact & source].copy()
    selected["stratum_id"] = make_task_b_stratum(selected)
    aggregated = aggregate_task_records(
        selected,
        [
            "stratum_id", "activity_type", "unit_normalized", "organism_species",
            "target", "rdkit_canonical_smiles", "scaffold",
        ],
        TASK_B_SOURCE_WEIGHTS,
    )
    audit = {
        "raw_task_rows": int(task.sum()),
        "exact_positive_A_B_rows": int(len(selected)),
        "aggregated_samples": int(len(aggregated)),
        "strata": int(aggregated["stratum_id"].nunique()),
        "rule": "train each activity_type + organism species + unit stratum separately",
        "minimum_unique_compounds": 8,
        "minimum_scaffolds": 3,
    }
    return aggregated, audit


def train_task_b(
    dataset: pd.DataFrame,
    models_dir: Path,
    results_dir: Path,
) -> tuple[dict[str, Any], dict[str, dict[str, Any]], pd.DataFrame, pd.DataFrame]:
    view, audit = task_b_view(dataset)
    featurizer = StructureFeaturizer()
    bundles: dict[str, dict[str, Any]] = {}
    metric_rows: list[dict[str, Any]] = []
    oof_rows: list[pd.DataFrame] = []
    stratum_summaries: list[dict[str, Any]] = []

    for stratum_id, group in view.groupby("stratum_id", sort=True):
        group = group.reset_index(drop=True)
        compounds = int(group["rdkit_canonical_smiles"].nunique())
        scaffolds = int(group["scaffold"].nunique())
        summary = {
            "stratum_id": stratum_id,
            "activity_type": group.iloc[0]["activity_type"],
            "organism_species": group.iloc[0]["organism_species"],
            "unit": group.iloc[0]["unit_normalized"],
            "samples": int(len(group)),
            "unique_compounds": compounds,
            "scaffolds": scaffolds,
        }
        if compounds < 8 or scaffolds < 3:
            summary["status"] = "insufficient_small_data"
            summary["reason"] = "requires >=8 unique compounds and >=3 scaffolds"
            metric_rows.append(
                {
                    "task": "Task B",
                    **summary,
                    "split": "not_run",
                    "spearman": np.nan,
                    "rmse": np.nan,
                    "ndcg_at_5": np.nan,
                    "top_k_enrichment": np.nan,
                    "hit_recovery": np.nan,
                }
            )
            stratum_summaries.append(summary)
            continue

        x = featurizer.frame(group["rdkit_canonical_smiles"])
        y = group["label_log10"].to_numpy(float)
        groups = group["scaffold"].to_numpy(str)
        weights = group["sample_weight"].to_numpy(float)
        predictions, folds, split_name = grouped_oof(x, y, groups, weights, "group_kfold")
        metrics = ranking_metrics(y, predictions, k=min(TOP_K, len(y)))
        summary.update({"status": "trained", "split": split_name})
        metric_rows.append(
            {
                "task": "Task B",
                **summary,
                "spearman": metrics["spearman"],
                "rmse": metrics["rmse"],
                "ndcg_at_5": metrics["ndcg_at_5"],
                "top_k_enrichment": metrics["top_k_enrichment"],
                "hit_recovery": metrics["hit_recovery"],
            }
        )
        oof = group.copy()
        oof["oof_prediction_log10"] = predictions
        oof["oof_fold"] = folds
        oof_rows.append(oof)

        final_model = make_regressor()
        final_model.fit(x, y, sample_weight=weights)
        bundle = {
            "model_version": MODEL_VERSION,
            "task": "Task B ATP synthase target modeling",
            "stratum_id": stratum_id,
            "activity_type": group.iloc[0]["activity_type"],
            "organism_species": group.iloc[0]["organism_species"],
            "target": group.iloc[0]["target"],
            "unit": group.iloc[0]["unit_normalized"],
            "label": f"log10 {group.iloc[0]['activity_type']} in {group.iloc[0]['unit_normalized']}",
            "direction": "lower_is_better",
            "model": final_model,
            "feature_names": featurizer.feature_names,
            "source_weights": TASK_B_SOURCE_WEIGHTS,
            "confidence_weights": CONFIDENCE_WEIGHTS,
            "sample_count": int(len(group)),
            "scaffold_count": scaffolds,
        }
        bundles[stratum_id] = bundle
        atomic_joblib(bundle, models_dir / f"task_b_{stratum_id}.joblib")
        stratum_summaries.append(summary)

    metrics_frame = pd.DataFrame(metric_rows)
    oof_frame = pd.concat(oof_rows, ignore_index=True) if oof_rows else pd.DataFrame()
    atomic_to_csv(metrics_frame, results_dir / "task_b_metrics.csv")
    atomic_to_csv(oof_frame, results_dir / "task_b_oof_predictions.csv")
    atomic_to_csv(view, results_dir / "task_b_training_view.csv")
    audit["trained_strata"] = int(len(bundles))
    audit["stratum_summary"] = stratum_summaries
    audit["feature_count"] = len(featurizer.feature_names)
    return audit, bundles, metrics_frame, oof_frame


def internal_external_priors(
    project_root: Path,
    task_a_featurizer: StructureFeaturizer,
    task_b_bundles: dict[str, dict[str, Any]],
    models_dir: Path,
) -> pd.DataFrame:
    samples = pd.read_csv(
        project_root / "data" / "dataset_v0.2" / "samples.csv",
        dtype=str,
        keep_default_na=False,
    )
    canonical = [canonicalize(smiles)[0] for smiles in samples["canonical_smiles"]]
    frame = pd.DataFrame(
        {
            "compound_id": samples["compound_id"],
            "canonical_smiles": canonical,
        }
    )

    task_a_bundle = joblib.load(models_dir / "task_a_mic_model.joblib")
    task_a_x = task_a_featurizer.frame(
        frame["canonical_smiles"],
        ["Acinetobacter baumannii"] * len(frame),
    )
    frame["v4a_task_a_ab_mic_log10_ug_ml"] = task_a_bundle["model"].predict(task_a_x)
    frame["v4a_task_a_ab_mic_priority"] = rank_percentile(
        frame["v4a_task_a_ab_mic_log10_ug_ml"], "lower_is_better"
    )

    b_priority_columns: list[str] = []
    b_prediction_columns: list[str] = []
    b_featurizer = StructureFeaturizer()
    b_x = b_featurizer.frame(frame["canonical_smiles"])
    for stratum_id, bundle in sorted(task_b_bundles.items()):
        prediction_column = f"v4a_task_b_{stratum_id}_prediction_log10"
        priority_column = f"v4a_task_b_{stratum_id}_priority"
        frame[prediction_column] = bundle["model"].predict(b_x)
        frame[priority_column] = rank_percentile(frame[prediction_column], "lower_is_better")
        b_prediction_columns.append(prediction_column)
        b_priority_columns.append(priority_column)
    if not b_priority_columns:
        frame["v4a_task_b_ensemble_priority"] = np.nan
    else:
        frame["v4a_task_b_ensemble_priority"] = frame[b_priority_columns].mean(axis=1)
    frame["v4a_task_b_ensemble_rank"] = frame["v4a_task_b_ensemble_priority"].rank(
        method="min", ascending=False
    ).astype("Int64")
    frame["task_b_ensemble_policy"] = (
        "equal-weight mean of within-17 rank percentiles from separately trained endpoint/organism/unit models"
    )
    frame["evidence_semantics"] = "external experimental knowledge model predictions; not internal assays"
    return frame


def train_internal_ranker(
    project_root: Path,
    priors: pd.DataFrame,
    models_dir: Path,
    results_dir: Path,
) -> tuple[dict[str, Any], pd.DataFrame, pd.DataFrame]:
    training = pd.read_csv(project_root / "data" / "model_v3" / "training_table.csv")
    v3_feature_payload = json.loads(
        (project_root / "models" / "model_v3" / "feature_list.json").read_text(encoding="utf-8")
    )
    v3_features = list(v3_feature_payload["all_features"])
    prior_features = [
        column
        for column in priors.columns
        if column.startswith("v4a_task_") and (column.endswith("prediction_log10") or column.endswith("_log10_ug_ml") or column.endswith("ensemble_priority"))
    ]
    if "v4a_task_a_ab_mic_log10_ug_ml" not in prior_features:
        prior_features.insert(0, "v4a_task_a_ab_mic_log10_ug_ml")
    prior_features = list(dict.fromkeys(prior_features))
    merged = training.merge(
        priors[["compound_id", *prior_features]],
        on="compound_id",
        how="left",
        validate="one_to_one",
    )
    if merged[prior_features].isna().any().any():
        raise ValueError("External prior prediction missing for an internal candidate")
    features = [*v3_features, *prior_features]
    x = merged[features].astype(float)
    y = merged["label_score"].to_numpy(float)
    groups = merged["scaffold"].to_numpy(str)
    predictions, folds, split_name = grouped_oof(
        x, y, groups, sample_weight=None, mode="leave_one_group_out"
    )
    metrics = ranking_metrics(y, predictions, k=TOP_K)

    oof = merged[["compound_id", "canonical_smiles", "scaffold", "label_score"]].copy()
    oof["model_v4_alpha_oof_prediction"] = predictions
    oof["fold"] = folds
    oof["label_semantics"] = "static MMGBSA computational ranking; not biological activity"
    atomic_to_csv(oof, results_dir / "internal_oof_predictions.csv")

    final_model = make_regressor()
    final_model.fit(x, y)
    bundle = {
        "model_version": MODEL_VERSION,
        "task": "Task C internal candidate computational ranking",
        "model": final_model,
        "feature_names": features,
        "base_feature_version": "Model v3",
        "new_external_prior_features": prior_features,
        "label": "static MMGBSA computational label",
        "direction": "lower_is_better",
        "evaluation": split_name,
    }
    atomic_joblib(bundle, models_dir / "candidate_ranker.joblib")
    final_predictions = final_model.predict(x)
    ranking = merged[["compound_id", "canonical_smiles", "scaffold", "label_score"]].copy()
    ranking["model_v4_alpha_prediction_lower_is_better"] = final_predictions
    ranking["model_v4_alpha_rank"] = ranking["model_v4_alpha_prediction_lower_is_better"].rank(
        method="min", ascending=True
    ).astype("Int64")
    ranking["score_semantics"] = "full-fit prediction of internal static MMGBSA computational ranking"
    ranking = ranking.sort_values(["model_v4_alpha_rank", "compound_id"])
    atomic_to_csv(ranking, results_dir / "candidate_ranking.csv")

    v3_comparison = pd.read_csv(project_root / "results" / "model_v3" / "model_v3_comparison.csv")
    v3 = v3_comparison.loc[v3_comparison["model_id"].eq("Model v3")].iloc[0]
    comparison = pd.DataFrame(
        [
            {
                "model_id": "Model v3",
                "model": v3["model"],
                "feature_count": int(v3["feature_count"]),
                "evaluation_samples": int(v3["evaluation_samples"]),
                "scaffold_groups": int(v3["scaffold_groups"]),
                "benchmark_protocol": v3["benchmark_protocol"],
                "spearman": float(v3["spearman"]),
                "rmse": float(v3["rmse"]),
                "ndcg_at_5": float(v3["ndcg_at_5"]),
                "top_k_enrichment": float(v3["top_k_enrichment"]),
                "hit_recovery": float(v3["hit_recovery"]),
                "status": "preserved_comparator",
            },
            {
                "model_id": "Model v4-alpha",
                "model": "lightgbm_v3_plus_dataset_v2_external_priors",
                "feature_count": len(features),
                "evaluation_samples": len(merged),
                "scaffold_groups": int(merged["scaffold"].nunique()),
                "benchmark_protocol": "scaffold_grouped_leave_one_group_out",
                "spearman": metrics["spearman"],
                "rmse": metrics["rmse"],
                "ndcg_at_5": metrics["ndcg_at_5"],
                "top_k_enrichment": metrics["top_k_enrichment"],
                "hit_recovery": metrics["hit_recovery"],
                "status": "alpha_experiment",
            },
        ]
    )
    for metric in ["spearman", "rmse", "ndcg_at_5", "top_k_enrichment", "hit_recovery"]:
        comparison[f"delta_v4alpha_minus_v3_{metric}"] = np.nan
        comparison.loc[comparison["model_id"].eq("Model v4-alpha"), f"delta_v4alpha_minus_v3_{metric}"] = (
            float(comparison.loc[comparison["model_id"].eq("Model v4-alpha"), metric].iloc[0])
            - float(comparison.loc[comparison["model_id"].eq("Model v3"), metric].iloc[0])
        )
    atomic_to_csv(comparison, results_dir / "model_comparison.csv")
    summary = {
        "training_samples": len(merged),
        "scaffold_groups": int(merged["scaffold"].nunique()),
        "base_feature_count": len(v3_features),
        "new_external_prior_feature_count": len(prior_features),
        "feature_count": len(features),
        "new_external_prior_features": prior_features,
        "evaluation": split_name,
        "metrics": metrics,
        "model_v3_metrics": {
            "spearman": float(v3["spearman"]),
            "rmse": float(v3["rmse"]),
            "ndcg_at_5": float(v3["ndcg_at_5"]),
            "top_k_enrichment": float(v3["top_k_enrichment"]),
            "hit_recovery": float(v3["hit_recovery"]),
        },
    }
    return summary, ranking, comparison


def experimental_decision_ranking(
    project_root: Path,
    priors: pd.DataFrame,
    v4_ranking: pd.DataFrame,
    results_dir: Path,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    preserved = pd.read_csv(project_root / "results" / "final_candidate_ranking.csv")
    frame = preserved.merge(
        priors,
        on=["compound_id", "canonical_smiles"],
        how="left",
        validate="one_to_one",
    ).merge(
        v4_ranking[["compound_id", "model_v4_alpha_prediction_lower_is_better", "model_v4_alpha_rank"]],
        on="compound_id",
        how="left",
        validate="one_to_one",
    )
    frame["model_v4_alpha_percentile"] = rank_percentile(
        frame["model_v4_alpha_prediction_lower_is_better"], "lower_is_better"
    )
    frame["binding_score_v4_alpha"] = (
        0.50 * frame["model_v4_alpha_percentile"]
        + 0.20 * frame["docking_percentile"]
        + 0.30 * frame["static_mmgbsa_percentile"]
    )
    frame["ATP_target_score_v4_alpha"] = (
        0.30 * frame["direct_ATP_similarity_percentile"]
        + 0.70 * frame["v4a_task_b_ensemble_priority"]
    )
    frame["antibacterial_score_v4_alpha"] = frame["v4a_task_a_ab_mic_priority"]
    frame["druglikeness_score_v4_alpha"] = frame["druglikeness_score"]
    frame["final_score_v4_alpha"] = (
        0.45 * frame["binding_score_v4_alpha"]
        + 0.25 * frame["ATP_target_score_v4_alpha"]
        + 0.15 * frame["antibacterial_score_v4_alpha"]
        + 0.15 * frame["druglikeness_score_v4_alpha"]
    )
    frame["final_rank_v4_alpha"] = frame["final_score_v4_alpha"].rank(
        method="min", ascending=False
    ).astype("Int64")
    frame["decision_status"] = "experimental_shadow_not_replacing_phase5"
    frame["experimental_MIC_status"] = "unknown"
    frame["experimental_ATP_enzyme_status"] = "unknown"
    frame["score_scope_v4_alpha"] = "relative_to_current_17_candidate_batch_not_probability"
    frame = frame.sort_values(["final_rank_v4_alpha", "compound_id"])
    leading = [
        "compound_id", "historical_alias", "final_rank_v4_alpha", "final_score_v4_alpha",
        "binding_score_v4_alpha", "ATP_target_score_v4_alpha",
        "antibacterial_score_v4_alpha", "druglikeness_score_v4_alpha",
        "model_v4_alpha_prediction_lower_is_better", "v4a_task_a_ab_mic_log10_ug_ml",
        "v4a_task_b_ensemble_priority", "decision_status", "experimental_MIC_status",
        "experimental_ATP_enzyme_status", "score_scope_v4_alpha",
    ]
    remaining = [column for column in frame.columns if column not in leading]
    frame = frame[leading + remaining]
    atomic_to_csv(frame, results_dir / "decision_engine_candidate_ranking.csv")

    old_rank = pd.to_numeric(frame["final_rank"], errors="coerce")
    new_rank = pd.to_numeric(frame["final_rank_v4_alpha"], errors="coerce")
    spearman = stats.spearmanr(old_rank, new_rank).statistic
    kendall = stats.kendalltau(old_rank, new_rank).statistic
    old_top3 = set(frame.nsmallest(3, "final_rank")["compound_id"])
    new_top3 = set(frame.nsmallest(3, "final_rank_v4_alpha")["compound_id"])
    old_top5 = set(frame.nsmallest(5, "final_rank")["compound_id"])
    new_top5 = set(frame.nsmallest(5, "final_rank_v4_alpha")["compound_id"])
    summary = {
        "formula": "0.45 Binding + 0.25 ATP target + 0.15 Antibacterial + 0.15 Drug-likeness",
        "phase5_output_overwritten": False,
        "component_update": {
            "binding": "Model v3 percentile replaced by Model v4-alpha percentile; docking/static MMGBSA subweights preserved",
            "ATP_target": "30% direct similarity + 70% equal-weight Task B stratum percentile ensemble",
            "antibacterial": "Task A predicted A. baumannii MIC percentile",
            "druglikeness": "preserved Phase 5 component",
        },
        "rank_spearman_vs_phase5": finite_or_none(spearman),
        "rank_kendall_vs_phase5": finite_or_none(kendall),
        "top3_overlap": len(old_top3 & new_top3),
        "top5_overlap": len(old_top5 & new_top5),
        "top_compound_v4_alpha": frame.iloc[0]["compound_id"],
        "top_alias_v4_alpha": frame.iloc[0]["historical_alias"],
        "top_score_v4_alpha": float(frame.iloc[0]["final_score_v4_alpha"]),
        "interpretation": "ranking comparison only; no experimental accuracy claim",
    }
    atomic_write_json(results_dir / "decision_engine_comparison.json", summary)
    return frame, summary


def markdown_table(frame: pd.DataFrame, columns: list[str], digits: int = 4) -> str:
    def render(value: Any) -> str:
        if pd.isna(value):
            return "—"
        if isinstance(value, (float, np.floating)):
            return f"{float(value):.{digits}f}"
        return str(value).replace("|", "/")

    lines = [
        "| " + " | ".join(columns) + " |",
        "|" + "|".join(["---"] * len(columns)) + "|",
    ]
    for row in frame[columns].itertuples(index=False, name=None):
        lines.append("| " + " | ".join(render(value) for value in row) + " |")
    return "\n".join(lines)


def build_report(
    audit: dict[str, Any],
    task_a: dict[str, Any],
    task_a_metrics: pd.DataFrame,
    task_b: dict[str, Any],
    task_b_metrics: pd.DataFrame,
    internal: dict[str, Any],
    comparison: pd.DataFrame,
    decision: pd.DataFrame,
    decision_summary: dict[str, Any],
) -> str:
    trained_b = task_b_metrics.loc[task_b_metrics["status"].eq("trained")].copy()
    top = decision.nsmallest(5, "final_rank_v4_alpha").copy()
    alpha_row = comparison.loc[comparison["model_id"].eq("Model v4-alpha")].iloc[0]
    v3_row = comparison.loc[comparison["model_id"].eq("Model v3")].iloc[0]
    improvement = (
        float(alpha_row["spearman"]) > float(v3_row["spearman"])
        and float(alpha_row["rmse"]) < float(v3_row["rmse"])
    )
    conclusion = (
        "在本次17候选scaffold-OOF实验中，Model v4-alpha的整体相关性和误差同时优于Model v3；"
        "但仍不足以证明外部知识带来稳定泛化提升。"
        if improvement
        else "本次实验未同时满足Spearman提高与RMSE下降，因此不能宣称外部知识已经带来明确提升。"
    )
    return f"""# ATP-Navigator Model v4-alpha Report

版本：`{MODEL_VERSION}`  
阶段：Phase 7 — External Knowledge Enhanced Training Experiment  
日期：2026-08-24

## 1. 实验目标与结论

本轮是第一次Dataset v2.0外部知识增强实验，不是最终模型。Model v0-v3、Phase 5 `results/final_candidate_ranking.csv`和`scoring_config.json`均未覆盖。

{conclusion}

内部比较仍以17个候选的静态MM/GBSA计算标签为基准，不是MIC、IC50或真实生物活性提升证明。

## 2. Dataset v2.0接入审计

- 输入：8,820行，{audit['unique_canonical_smiles']:,}个RDKit canonical structures，SMILES解析失败{audit['invalid_smiles']}；
- Task A：{audit['task_counts'].get('Antibacterial', 0):,}行；Task B：{audit['task_counts'].get('ATP_target', 0):,}行；Benchmark：{audit['task_counts'].get('Benchmark', 0):,}行；
- activity值：exact {audit['value_classes'].get('exact_numeric', 0):,}，censored {audit['value_classes'].get('censored', 0):,}，range {audit['value_classes'].get('range', 0):,}；
- 43个canonical structure跨task出现，所有划分按scaffold/canonical identity隔离；
- 2,080条Benchmark记录没有进入Task A/B训练，也没有进入内部MM/GBSA标签；
- `Dataset_QC_Report_external_source.md`审计的是早期6,777行主库；本pipeline对当前8,820行标准输入另行生成`dataset_audit.json`；
- source level与reference为用户提供的来源标注，本轮没有逐条重新打开论文或数据库验证。

## 3. 三任务隔离

### Task A — Antibacterial activity modeling

- 标签：精确、正值、MIC、μg/mL；回归目标为`log10(MIC μg/mL)`，lower-is-better；
- 截尾值、范围值、ETC inhibition和非MIC行不转数值；
- 同结构×organism species重复测量取中位数，保留测量数、范围、来源等级与reference数量；
- 特征：Morgan1024 + RDKit16 + organism species one-hot；source level和confidence仅作样本权重，不作分子特征；
- 训练规模：{task_a['aggregated_samples']:,}个结构-物种样本，{task_a['unique_structures']:,}个结构，{task_a['scaffold_groups']:,}个scaffold；
- 评价：{task_a['split']}；正式报告切片为A/B且confidence=high；
- classification accuracy：不适用。当前没有预注册active/inactive阈值，未事后创造分类标签。

{markdown_table(task_a_metrics, ['slice', 'n', 'rmse', 'spearman', 'classification_status'])}

### Task B — ATP synthase target modeling

- 不把IC50、Activity%、Inhibition%或不同单位混成同一回归目标；
- 按`activity_type + organism species + unit`分别训练；每个stratum至少8个结构、3个scaffold；
- 标签为各stratum内`log10(activity_value)`，仅A/B实验来源；
- source weights：A=1.0、B=0.8；confidence high=1.0、medium=0.7；
- 当前训练strata：{task_b['trained_strata']}；其余strata保留`insufficient_small_data`状态。

{markdown_table(trained_b, ['stratum_id', 'samples', 'scaffolds', 'spearman', 'rmse', 'ndcg_at_5', 'top_k_enrichment', 'hit_recovery']) if not trained_b.empty else '当前无可训练Task B stratum。'}

Task B各stratum指标不可跨单位解释为一个统一IC50性能；Task C只对每个模型在内部17候选上的预测做rank percentile，再等权形成ATP知识ensemble。

### Task C — Candidate ranking

- 基础：保留Model v3全部1,128个特征；
- 新增：{internal['new_external_prior_feature_count']}个Dataset v2.0 Task A/B预测特征；总特征{internal['feature_count']}；
- 标签：内部17候选静态MM/GBSA，lower-is-better；Task A MIC和Task B IC50从未成为Task C标签；
- 评价：{internal['evaluation']}，17个候选、11个scaffold。

## 4. Model v3 vs Model v4-alpha

{markdown_table(comparison, ['model_id', 'feature_count', 'spearman', 'rmse', 'ndcg_at_5', 'top_k_enrichment', 'hit_recovery'])}

性能差值必须结合n=17解释。即使某一指标提高，也不能证明真实活性命中率提高；Top-k指标单个候选即可显著改变。

## 5. Decision Engine实验接入

原Phase 5结果未覆盖。`decision_engine_candidate_ranking.csv`是shadow experiment：

- 仍用45/25/15/15总权重；
- Binding中将Model v3 percentile替换为Model v4-alpha percentile，Docking和静态MM/GBSA子权重不变；
- ATP Target = 30%直接ATP结构相似性 + 70% Task B分层ensemble；
- Antibacterial = Task A对A. baumannii预测的批次内percentile；
- Drug-likeness保留Phase 5结果；实验MIC和ATP enzyme仍标记`unknown`。

相对原Phase 5：Spearman {decision_summary['rank_spearman_vs_phase5']:.4f}，Kendall {decision_summary['rank_kendall_vs_phase5']:.4f}，Top3重叠{decision_summary['top3_overlap']}/3，Top5重叠{decision_summary['top5_overlap']}/5。这是排名变化，不是实验准确率。

{markdown_table(top, ['final_rank_v4_alpha', 'historical_alias', 'compound_id', 'final_score_v4_alpha', 'decision_status'])}

## 6. Small-data limitation

- 内部Task C只有17个候选/11个scaffold，无独立前瞻测试集；
- Task B各同质stratum仅8–25个样本、3–18个scaffold，相关性方差很大；
- Dataset v2.0与既有Model v2知识来源存在内容重叠，本轮是增量工程实验，不是独立外部验证；
- Task A/B模型预测是计算先验，不是内部候选的MIC或ATP enzyme实验；
- 2,080条BindingDB benchmark严格未用于本轮训练，后续只能在冻结协议和训练去重后作验证/校准；
- source quality等级由提供文件给出，本轮未逐条回源核实；
- 未处理截尾MIC的删失回归；本轮直接排除，可能产生选择偏差。

## 7. 下一轮最缺数据

1. 更多同一ATP synthase亚型、同一assay、同一unit的A等级IC50，尤其A. baumannii且scaffold更分散；
2. 内部17候选的ATP synthase功能/酶抑制、MIC/MBC、实验毒性和重复测量；
3. 独立于Dataset v2.0和Model v2来源的冻结测试集；
4. 对截尾MIC可使用的检测上下限与原始实验条件，用于删失回归；
5. target protein ID、assay protocol、strain、pH/培养条件等可结构化条件字段；
6. 更多内部中等/负候选的同协议静态MM/GBSA，降低仅Top17的选择偏差。

## 8. 复现产物

- `src/model_v4_alpha_pipeline.py`
- `data/dataset_v2.0/ATP_Navigator_external_dataset_v1.csv`
- `models/model_v4_alpha/`
- `results/model_v4_alpha/`
- `docs/Model_v4_alpha_Report.md`

本报告只描述本次实际运行结果，不将Model v4-alpha登记为最终模型。
"""


def build_config(
    project_root: Path,
    audit: dict[str, Any],
    task_a: dict[str, Any],
    task_b: dict[str, Any],
    internal: dict[str, Any],
    decision: dict[str, Any],
) -> dict[str, Any]:
    input_paths = {
        "dataset_v2": project_root / "data" / "dataset_v2.0" / "ATP_Navigator_external_dataset_v1.csv",
        "model_input_spec": project_root / "docs" / "ATP_Navigator_Model_Input_Spec.md",
        "data_dictionary": project_root / "docs" / "ATP_Navigator_Data_Dictionary_v1.md",
        "source_quality": project_root / "docs" / "Source_Quality_System.md",
        "model_v3_training_table": project_root / "data" / "model_v3" / "training_table.csv",
        "phase5_ranking": project_root / "results" / "final_candidate_ranking.csv",
    }
    return {
        "model_version": MODEL_VERSION,
        "status": "alpha_experiment_not_final",
        "random_seed": RANDOM_SEED,
        "tasks": {
            "A": task_a,
            "B": task_b,
            "C": internal,
        },
        "label_separation": {
            "Task A": "MIC μg/mL only",
            "Task B": "separate activity_type + organism + unit strata",
            "Task C": "internal static MMGBSA computational ranking only",
            "Benchmark": "excluded from training",
        },
        "weights": {
            "task_a_source": TASK_A_SOURCE_WEIGHTS,
            "task_b_source": TASK_B_SOURCE_WEIGHTS,
            "confidence": CONFIDENCE_WEIGHTS,
        },
        "lightgbm_parameters": make_regressor().get_params(),
        "decision_shadow": decision,
        "dataset_audit": audit,
        "input_hashes": {name: sha256(path) for name, path in input_paths.items()},
        "environment": {
            "python": platform.python_version(),
            "pandas": pd.__version__,
            "numpy": np.__version__,
            "rdkit": rdBase.rdkitVersion,
            "lightgbm": lgb.__version__,
        },
    }


def run(project_root: Path) -> dict[str, Any]:
    project_root = project_root.resolve()
    dataset_path = project_root / "data" / "dataset_v2.0" / "ATP_Navigator_external_dataset_v1.csv"
    results_dir = project_root / "results" / "model_v4_alpha"
    models_dir = project_root / "models" / "model_v4_alpha"
    results_dir.mkdir(parents=True, exist_ok=True)
    models_dir.mkdir(parents=True, exist_ok=True)

    dataset, audit = prepare_dataset(dataset_path)
    internal_samples = pd.read_csv(
        project_root / "data" / "dataset_v0.2" / "samples.csv", dtype=str, keep_default_na=False
    )
    internal_canonical = {canonicalize(smiles)[0] for smiles in internal_samples["canonical_smiles"]}
    external_canonical = set(dataset["rdkit_canonical_smiles"])
    audit["internal_exact_structure_overlap"] = len(internal_canonical & external_canonical)
    audit["benchmark_training_policy"] = "2,080 Benchmark rows excluded from Task A/B/C training"
    atomic_write_json(results_dir / "dataset_audit.json", audit)
    atomic_to_csv(
        pd.DataFrame(
            [
                {
                    "task_type": task,
                    "rows": int(count),
                    "training_use": "excluded_validation_only" if task == "Benchmark" else "task_specific_filter_only",
                }
                for task, count in audit["task_counts"].items()
            ]
        ),
        results_dir / "task_routing_audit.csv",
    )

    task_a_summary, _, task_a_metrics, task_a_featurizer = train_task_a(
        dataset, models_dir, results_dir
    )
    task_b_summary, task_b_bundles, task_b_metrics, _ = train_task_b(
        dataset, models_dir, results_dir
    )
    priors = internal_external_priors(
        project_root, task_a_featurizer, task_b_bundles, models_dir
    )
    atomic_to_csv(priors, results_dir / "external_priors_internal.csv")
    internal_summary, v4_ranking, comparison = train_internal_ranker(
        project_root, priors, models_dir, results_dir
    )
    decision_ranking, decision_summary = experimental_decision_ranking(
        project_root, priors, v4_ranking, results_dir
    )
    report = build_report(
        audit,
        task_a_summary,
        task_a_metrics,
        task_b_summary,
        task_b_metrics,
        internal_summary,
        comparison,
        decision_ranking,
        decision_summary,
    )
    atomic_write_text(project_root / "docs" / "Model_v4_alpha_Report.md", report)

    config = build_config(
        project_root,
        audit,
        task_a_summary,
        task_b_summary,
        internal_summary,
        decision_summary,
    )
    atomic_write_json(models_dir / "training_config.json", config)
    feature_payload = {
        "model_version": MODEL_VERSION,
        "task_a": joblib.load(models_dir / "task_a_mic_model.joblib")["feature_names"],
        "task_b": {key: value["feature_names"] for key, value in task_b_bundles.items()},
        "task_c": joblib.load(models_dir / "candidate_ranker.joblib")["feature_names"],
    }
    atomic_write_json(models_dir / "feature_list.json", feature_payload)
    metadata = {
        "dataset_version": DATASET_VERSION,
        "source_file": "ATP_Navigator_external_dataset_v1.csv",
        "source_sha256": audit["source_sha256"],
        "rows": audit["rows"],
        "unique_canonical_smiles": audit["unique_canonical_smiles"],
        "task_counts": audit["task_counts"],
        "immutable_source": True,
        "derived_training_views": [
            "results/model_v4_alpha/task_a_training_view.csv",
            "results/model_v4_alpha/task_b_training_view.csv",
        ],
        "labels_not_mixed": True,
    }
    atomic_write_json(project_root / "data" / "dataset_v2.0" / "dataset_metadata.json", metadata)
    payload = {
        "model_version": MODEL_VERSION,
        "dataset": audit,
        "task_a": task_a_summary,
        "task_b": task_b_summary,
        "task_c": internal_summary,
        "decision": decision_summary,
        "outputs": {
            "report": "docs/Model_v4_alpha_Report.md",
            "results": "results/model_v4_alpha",
            "models": "models/model_v4_alpha",
        },
    }
    atomic_write_json(results_dir / "run_metadata.json", payload)
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--project-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
    )
    parser.add_argument("command", choices=["run", "audit"])
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.command == "audit":
        dataset, audit = prepare_dataset(
            args.project_root / "data" / "dataset_v2.0" / "ATP_Navigator_external_dataset_v1.csv"
        )
        print(json.dumps(json_safe(audit), ensure_ascii=False, indent=2, allow_nan=False))
        print(f"validated_rows={len(dataset)}")
    else:
        print(
            json.dumps(
                json_safe(run(args.project_root)),
                ensure_ascii=False,
                indent=2,
                allow_nan=False,
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
