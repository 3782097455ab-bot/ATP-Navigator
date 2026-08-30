"""Task-isolated Competition RC shadow experiment.

Only the Gram-negative MIC task receives new eligible member records.  The
ATP-target and internal ranking tasks remain unchanged because the new sources
do not provide compatible exact labels.  The experiment is therefore incapable
of silently replacing the official Model v3 candidate ranker.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import tempfile
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from rdkit import Chem
from rdkit.Chem.Scaffolds import MurckoScaffold
from scipy import stats
from sklearn.model_selection import GroupKFold

from model_v2_pipeline import make_regressor, ranking_metrics
from model_v4_alpha_pipeline import StructureFeaturizer, prepare_dataset


EXPERIMENT_ID = "competition_rc_shadow_001"
SEED = 20260831


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [safe(v) for v in value]
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, Path):
        return str(value)
    return value


def atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False, dir=path.parent) as handle:
        json.dump(safe(payload), handle, ensure_ascii=False, indent=2, allow_nan=False)
        temporary = Path(handle.name)
    temporary.replace(path)


def atomic_csv(path: Path, frame: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8-sig", newline="", delete=False, dir=path.parent) as handle:
        frame.to_csv(handle, index=False)
        temporary = Path(handle.name)
    temporary.replace(path)


def samples_from_v2(frame: pd.DataFrame) -> pd.DataFrame:
    selected = frame.loc[
        frame["task_type"].eq("Antibacterial")
        & frame["activity_type"].eq("MIC")
        & frame["unit_normalized"].eq("μg/mL")
        & frame["value_class"].eq("exact_numeric")
        & frame["numeric_activity"].gt(0)
        & frame["source_level"].isin(["A", "B", "C"])
    ].copy()
    selected["context"] = selected["organism"].astype(str).str.strip()
    selected["label_log10"] = np.log10(selected["numeric_activity"].astype(float))
    selected["sample_weight"] = selected["source_level"].map({"A": 1.0, "B": 1.0, "C": 0.5}).fillna(0.5)
    selected["data_origin"] = "External_Dataset_v2"
    return aggregate(selected, "rdkit_canonical_smiles", "reference")


def samples_from_member(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path, dtype=str, keep_default_na=False)
    selected = frame.loc[frame["training_eligible"].str.lower().eq("true")].copy()
    selected["rdkit_canonical_smiles"] = selected["canonical_smiles"]
    selected["scaffold"] = selected["canonical_smiles"].map(
        lambda smiles: MurckoScaffold.MurckoScaffoldSmiles(
            mol=Chem.MolFromSmiles(smiles), includeChirality=True
        ) or smiles
    )
    selected["context"] = selected["raw_organism"]
    selected["label_log10"] = np.log10(pd.to_numeric(selected["activity_value_numeric"], errors="raise"))
    selected["sample_weight"] = 1.0
    selected["data_origin"] = "Member2_GN_MIC"
    selected["reference"] = selected["raw_reference"]
    return aggregate(selected, "rdkit_canonical_smiles", "reference")


def aggregate(frame: pd.DataFrame, smiles_column: str, reference_column: str) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for keys, group in frame.groupby([smiles_column, "scaffold", "context"], sort=True, dropna=False):
        smiles, scaffold, context = keys
        values = pd.to_numeric(group["label_log10"], errors="coerce").dropna()
        if values.empty:
            continue
        rows.append({
            "canonical_smiles": smiles, "scaffold": scaffold, "context": context,
            "label_log10": float(values.median()), "measurement_count": int(len(group)),
            "sample_weight": float(pd.to_numeric(group["sample_weight"], errors="coerce").fillna(0.5).max()),
            "data_origin": "|".join(sorted(set(group["data_origin"].astype(str)))),
            "references": "|".join(sorted(set(group[reference_column].astype(str)))),
        })
    return pd.DataFrame(rows)


def metric_row(name: str, y: np.ndarray, pred: np.ndarray) -> dict[str, Any]:
    ranking = ranking_metrics(y, pred, k=min(5, len(y)))
    return {
        "model": name, "evaluation_task": "Gram-negative MIC context",
        "label": "log10_MIC_ug_mL_lower_is_better", "n": len(y),
        "rmse": float(np.sqrt(np.mean((y - pred) ** 2))),
        "spearman": float(stats.spearmanr(y, pred).statistic),
        "ndcg_at_5": ranking["ndcg_at_5"], "top_k_enrichment": ranking["top_k_enrichment"],
        "hit_recovery": ranking["hit_recovery"],
        "split": "same 5-fold scaffold GroupKFold; exact compounds/scaffolds excluded from held-out folds",
    }


def run(project: Path) -> dict[str, Any]:
    project = project.resolve()
    result_dir = project / "results/release_candidate/model_promotion"
    model_dir = project / "models/experiments" / EXPERIMENT_ID
    result_dir.mkdir(parents=True, exist_ok=True)
    model_dir.mkdir(parents=True, exist_ok=True)
    protected = json.loads((project / "results/phase14/model_hashes_after.json").read_text(encoding="utf-8"))
    before = {name: digest(project / name) for name in protected}

    dataset, dataset_audit = prepare_dataset(project / "data/dataset_v2.0/ATP_Navigator_external_dataset_v1.csv")
    baseline = samples_from_v2(dataset)
    member = samples_from_member(project / "results/release_candidate/member_data_integration/member2_qc.csv")
    combined = pd.concat([baseline, member], ignore_index=True)
    # Reaggregate after append so an exact structure/context is one sample and
    # repeated measurements are not mistaken for independent compounds.
    combined = aggregate(combined.assign(reference=combined["references"]), "canonical_smiles", "reference")

    contexts = sorted(set(combined["context"]))
    featurizer = StructureFeaturizer(contexts)
    base_x = featurizer.frame(baseline["canonical_smiles"], baseline["context"])
    combined_x = featurizer.frame(combined["canonical_smiles"], combined["context"])
    y = baseline["label_log10"].to_numpy(float)
    groups = baseline["scaffold"].astype(str).to_numpy()
    unique_groups = np.unique(groups)
    splitter = GroupKFold(n_splits=min(5, len(unique_groups)))
    baseline_pred = np.full(len(baseline), np.nan)
    augmented_pred = np.full(len(baseline), np.nan)
    fold_ids = np.full(len(baseline), -1, dtype=int)
    for fold, (train, test) in enumerate(splitter.split(base_x, y, groups)):
        test_scaffolds = set(groups[test])
        if test_scaffolds & set(groups[train]):
            raise RuntimeError("scaffold leakage in baseline split")
        base_model = make_regressor().fit(base_x.iloc[train], y[train], sample_weight=baseline["sample_weight"].to_numpy(float)[train])
        baseline_pred[test] = base_model.predict(base_x.iloc[test])
        augmented_train = ~combined["scaffold"].astype(str).isin(test_scaffolds)
        if set(combined.loc[augmented_train, "scaffold"].astype(str)) & test_scaffolds:
            raise RuntimeError("member-data scaffold leakage")
        aug_model = make_regressor().fit(
            combined_x.loc[augmented_train], combined.loc[augmented_train, "label_log10"].to_numpy(float),
            sample_weight=combined.loc[augmented_train, "sample_weight"].to_numpy(float),
        )
        augmented_pred[test] = aug_model.predict(base_x.iloc[test])
        fold_ids[test] = fold
    if np.isnan(baseline_pred).any() or np.isnan(augmented_pred).any():
        raise RuntimeError("OOF coverage incomplete")

    comparison = pd.DataFrame([metric_row("TaskA_v2_replayed_control", y, baseline_pred),
                               metric_row("TaskA_member2_context_shadow", y, augmented_pred)])
    atomic_csv(result_dir / "task_a_shadow_comparison.csv", comparison)
    oof = baseline.copy()
    oof["fold_id"] = fold_ids
    oof["baseline_oof"] = baseline_pred
    oof["augmented_oof"] = augmented_pred
    atomic_csv(result_dir / "task_a_shadow_oof.csv", oof)

    rng = np.random.default_rng(SEED)
    differences = []
    folds = sorted(set(fold_ids))
    for _ in range(2000):
        sampled = rng.choice(folds, len(folds), replace=True)
        indices = np.concatenate([np.flatnonzero(fold_ids == fold) for fold in sampled])
        old = float(np.sqrt(np.mean((y[indices] - baseline_pred[indices]) ** 2)))
        new = float(np.sqrt(np.mean((y[indices] - augmented_pred[indices]) ** 2)))
        differences.append(new - old)
    interval = np.quantile(differences, [0.025, 0.975]).tolist()

    final_model = make_regressor().fit(combined_x, combined["label_log10"].to_numpy(float),
                                       sample_weight=combined["sample_weight"].to_numpy(float))
    bundle = {
        "model": final_model, "model_version": EXPERIMENT_ID,
        "task": "Gram-negative MIC context shadow only", "label": "log10 MIC ug/mL",
        "feature_names": featurizer.feature_names, "context_categories": contexts,
        "training_rows": len(combined), "unique_structures": int(combined["canonical_smiles"].nunique()),
        "official": False, "may_replace_model_v3": False,
    }
    joblib.dump(bundle, model_dir / "task_a_member2_context_shadow.joblib")
    atomic_csv(result_dir / "task_a_shadow_training_view.csv", combined)

    member_keys = set(member["canonical_smiles"])
    base_keys = set(baseline["canonical_smiles"])
    domain = {
        "member_unique_structures": len(member_keys), "exact_structure_overlap_with_v2_task_a": len(member_keys & base_keys),
        "truly_new_structures": len(member_keys - base_keys),
        "new_information_type": "assay/strain/resistance context, not chemical-space expansion",
    }
    old_metrics = comparison.iloc[0].to_dict()
    new_metrics = comparison.iloc[1].to_dict()
    rmse_delta = float(new_metrics["rmse"] - old_metrics["rmse"])
    spearman_delta = float(new_metrics["spearman"] - old_metrics["spearman"])
    promotion = {
        "official_model_before": "Model v3",
        "official_model_after": "Model v3",
        "promotion_passed": False,
        "task_a_shadow_result": "improved" if rmse_delta < 0 and spearman_delta > 0 else "mixed_or_not_improved",
        "rmse_delta_shadow_minus_control": rmse_delta,
        "spearman_delta_shadow_minus_control": spearman_delta,
        "bootstrap_rmse_delta_95_interval": interval,
        "cold_scaffold_evaluation_n": len(baseline),
        "model_v3_direct_comparison_status": "not_applicable_task_mismatch",
        "reason": "MIC context model cannot replace the internal static-MMGBSA candidate ranker; Member1/BindingDB added zero compatible exact ATP-synthase training labels; prior internal release shadow did not exceed Model v3",
        "prior_internal_shadow_reference": "results/release_v1_shadow_replace_atp_002/experiment_summary.json",
    }
    atomic_json(result_dir / "model_promotion_gate.json", promotion)
    atomic_json(result_dir / "domain_shift_audit.json", domain)

    after = {name: digest(project / name) for name in protected}
    changed = {name: {"before": before[name], "after": after[name]} for name in before if before[name] != after[name]}
    if changed:
        raise RuntimeError(f"protected models changed: {changed}")
    config = {
        "experiment_id": EXPERIMENT_ID, "random_seed": SEED,
        "data_manifest": "results/release_candidate/member_data_integration/member_data_manifest.csv",
        "training_policy": "MIC only; full organism/strain context; fixed scaffold OOF; no endpoint pooling",
        "baseline_samples": len(baseline), "augmented_samples": len(combined),
        "member_training_rows": int(len(member)), "feature_count": len(featurizer.feature_names),
        "protected_model_hashes": before,
    }
    atomic_json(model_dir / "training_config.json", config)
    atomic_json(model_dir / "feature_list.json", featurizer.feature_names)
    summary = {
        "experiment_id": EXPERIMENT_ID, "dataset_audit_rows": dataset_audit["rows"],
        "task_a": {"baseline_samples": len(baseline), "augmented_samples": len(combined), "member_eligible_rows": len(member),
                   "metrics": comparison.to_dict("records"), "bootstrap_rmse_delta_95_interval": interval},
        "task_b": {"trained": False, "reason": "zero new exact compatible ATP-synthase endpoint records"},
        "task_c": {"trained": False, "reason": "no new internal MMGBSA or biological candidate labels"},
        "promotion": promotion, "domain_shift": domain,
        "protected_model_hashes_unchanged": True, "new_model_hash": digest(model_dir / "task_a_member2_context_shadow.joblib"),
    }
    atomic_json(result_dir / "shadow_experiment_summary.json", summary)
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    print(json.dumps(run(args.project), ensure_ascii=False, indent=2))
