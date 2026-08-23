"""Strict, incremental benchmark for ATP-Navigator Phase 1.5.

This module does not overwrite Phase 1 metrics, predictions or model files. It
re-evaluates the same model definitions with Bemis-Murcko scaffold groups held
out and emits JSON payloads for the Phase 1.5 comparison artifacts.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd
from rdkit import Chem, DataStructs
from rdkit.Chem import rdFingerprintGenerator
from rdkit.Chem.Scaffolds import MurckoScaffold
from sklearn.model_selection import LeaveOneGroupOut, cross_val_predict

from baseline_train import make_pipeline, model_factories
from evaluation import evaluate_predictions
from feature_pipeline import FeatureConfig, MoleculeFeaturePipeline


def scaffold_key(smiles: str) -> str:
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        raise ValueError(f"Invalid SMILES in strict benchmark: {smiles}")
    scaffold = MurckoScaffold.MurckoScaffoldSmiles(mol=mol, includeChirality=True)
    return scaffold or Chem.MolToSmiles(mol, canonical=True, isomericSmiles=True)


def enrichment_metrics(y_true: np.ndarray, y_pred: np.ndarray, top_k: int) -> dict[str, float | int]:
    n_samples = len(y_true)
    if n_samples == 0:
        return {
            "top_k": 0,
            "recovered_hits": 0,
            "true_hits": 0,
            "top_k_enrichment": np.nan,
            "hit_recovery": np.nan,
        }
    effective_k = min(max(int(top_k), 1), n_samples)
    true_top = set(np.argsort(y_true, kind="stable")[:effective_k])
    predicted_top = set(np.argsort(y_pred, kind="stable")[:effective_k])
    recovered = len(true_top.intersection(predicted_top))
    random_expected_overlap = effective_k * effective_k / n_samples
    return {
        "top_k": effective_k,
        "recovered_hits": recovered,
        "true_hits": effective_k,
        "top_k_enrichment": recovered / random_expected_overlap,
        "hit_recovery": recovered / effective_k,
    }


def structural_audit(train: pd.DataFrame) -> dict[str, object]:
    mols = [Chem.MolFromSmiles(smiles) for smiles in train["smiles"]]
    canonical_smiles = [
        Chem.MolToSmiles(mol, canonical=True, isomericSmiles=True) for mol in mols
    ]
    inchikeys = [Chem.MolToInchiKey(mol) for mol in mols]
    connectivity_keys = [key.split("-")[0] for key in inchikeys]
    scaffolds = [scaffold_key(smiles) for smiles in train["smiles"]]
    scaffold_counts = Counter(scaffolds)

    generator = rdFingerprintGenerator.GetMorganGenerator(
        radius=2, fpSize=1024, includeChirality=True
    )
    fingerprints = [generator.GetFingerprint(mol) for mol in mols]
    similarities = [
        DataStructs.TanimotoSimilarity(fingerprints[left], fingerprints[right])
        for left in range(len(fingerprints))
        for right in range(left + 1, len(fingerprints))
    ]
    return {
        "candidate_rows": len(train),
        "unique_canonical_ids": int(train["canonical_id"].nunique()),
        "unique_raw_smiles": int(train["smiles"].nunique()),
        "unique_canonical_smiles": len(set(canonical_smiles)),
        "unique_inchikeys": len(set(inchikeys)),
        "unique_connectivity_keys": len(set(connectivity_keys)),
        "unique_scaffolds": len(scaffold_counts),
        "scaffold_group_sizes": sorted(scaffold_counts.values(), reverse=True),
        "largest_scaffold_group": max(scaffold_counts.values()),
        "max_pairwise_tanimoto": max(similarities),
        "mean_pairwise_tanimoto": sum(similarities) / len(similarities),
        "pairs_tanimoto_ge_0_7": sum(value >= 0.7 for value in similarities),
    }


def run_benchmark(project_root: Path, *, top_k: int = 5, n_bits: int = 1024) -> None:
    project_root = project_root.resolve()
    results_dir = project_root / "results"
    results_dir.mkdir(parents=True, exist_ok=True)

    feature_pipeline = MoleculeFeaturePipeline(project_root, FeatureConfig(n_bits=n_bits))
    feature_matrix, _ = feature_pipeline.build()
    target_column = "score_MMGBSA"
    train = feature_matrix.loc[
        feature_matrix[target_column].notna() & feature_matrix["smiles_valid"].eq(True)
    ].copy()
    train = train.sort_values("canonical_id", kind="stable").reset_index(drop=True)

    candidate_features = feature_pipeline.model_feature_columns(feature_matrix, "MMGBSA")
    usable_features = [
        column
        for column in candidate_features
        if pd.to_numeric(train[column], errors="coerce").notna().any()
    ]
    X = train[usable_features].apply(pd.to_numeric, errors="coerce")
    y = pd.to_numeric(train[target_column], errors="coerce").to_numpy(dtype=float)
    groups = np.asarray([scaffold_key(smiles) for smiles in train["smiles"]])

    structural = structural_audit(train)
    screening = pd.read_csv(project_root / "data" / "screening_records.csv")
    label_rows = screening.loc[
        screening["canonical_id"].isin(train["canonical_id"])
        & screening["stage"].eq("MMGBSA")
    ].copy()
    label_counts = label_rows.groupby("canonical_id").size()
    label_sources = sorted(label_rows["source_file"].dropna().unique().tolist())

    comparison_rows: list[dict[str, object]] = [
        {
            "model_id": "Model 0",
            "model": "docking_only",
            "benchmark_protocol": "no_common_evaluation_set",
            "ranking_population": 1633,
            "evaluation_samples": 0,
            "feature_set": "best HTVS Glide docking score per canonical_id",
            "spearman": None,
            "ndcg": None,
            "top_k": 0,
            "top_k_enrichment": None,
            "hit_recovery": None,
            "recovered_hits": 0,
            "true_hits": 0,
            "status": "not_evaluable_no_verified_id_bridge",
            "notes": "HTVS ranking is retained, but HTVS canonical IDs cannot yet be verified against the 17 MMGBSA candidates.",
        }
    ]
    strict_predictions: list[dict[str, object]] = []
    logo = LeaveOneGroupOut()
    factories = model_factories()
    model_labels = [
        ("Model 1", "random_forest"),
        ("Model 2", "xgboost"),
        ("Model 3", "lightgbm"),
    ]
    for model_id, model_name in model_labels:
        if model_name not in factories:
            comparison_rows.append(
                {
                    "model_id": model_id,
                    "model": model_name,
                    "benchmark_protocol": "scaffold_grouped_leave_one_out",
                    "ranking_population": len(train),
                    "evaluation_samples": 0,
                    "feature_set": "Morgan1024 + RDKit10 + ADMET_SUM",
                    "spearman": None,
                    "ndcg": None,
                    "top_k": 0,
                    "top_k_enrichment": None,
                    "hit_recovery": None,
                    "recovered_hits": 0,
                    "true_hits": 0,
                    "status": "missing_dependency",
                    "notes": "Model dependency is not installed.",
                }
            )
            continue

        estimator = make_pipeline(factories[model_name]())
        predicted = cross_val_predict(
            estimator,
            X,
            y,
            groups=groups,
            cv=logo,
            n_jobs=1,
            method="predict",
        )
        base_metrics = evaluate_predictions(y, predicted, top_k=top_k)
        enrichment = enrichment_metrics(y, predicted, top_k)
        comparison_rows.append(
            {
                "model_id": model_id,
                "model": model_name,
                "benchmark_protocol": "scaffold_grouped_leave_one_out",
                "ranking_population": len(train),
                "evaluation_samples": len(train),
                "feature_set": "Morgan1024 + RDKit10 + ADMET_SUM",
                "spearman": base_metrics["spearman"],
                "ndcg": base_metrics["ndcg"],
                "top_k": enrichment["top_k"],
                "top_k_enrichment": enrichment["top_k_enrichment"],
                "hit_recovery": enrichment["hit_recovery"],
                "recovered_hits": enrichment["recovered_hits"],
                "true_hits": enrichment["true_hits"],
                "status": base_metrics["status"],
                "notes": "All members of the held-out Bemis-Murcko scaffold group are excluded from training.",
            }
        )
        for index, row in train.iterrows():
            strict_predictions.append(
                {
                    "canonical_id": row["canonical_id"],
                    "model": model_name,
                    "scaffold": groups[index],
                    "observed_score": y[index],
                    "predicted_score": float(predicted[index]),
                }
            )

    split_audit = {
        "phase": "Phase 1.5",
        "preserved_baseline": True,
        "original_protocol": "leave_one_molecule_out",
        "strict_protocol": "leave_one_Bemis-Murcko_scaffold_group_out",
        "structural_audit": structural,
        "leakage_assessment": {
            "duplicate_canonical_id_across_rows": False,
            "duplicate_canonical_smiles": structural["unique_canonical_smiles"] < len(train),
            "duplicate_connectivity_identity": structural["unique_connectivity_keys"] < len(train),
            "same_compound_conformer_split": False,
            "same_scaffold_can_cross_original_LOOCV": structural["largest_scaffold_group"] > 1,
            "preprocessing_fitted_outside_fold": False,
            "target_column_in_model_features": target_column in usable_features,
            "model_selection_bias_risk": "Metrics compare three fixed models on the same small OOF set; model choice needs later external or nested validation.",
        },
        "label_assessment": {
            "training_label": "VSW static MMGBSA dG Bind",
            "score_direction": "lower_is_better",
            "training_label_rows": len(label_rows),
            "min_label_rows_per_candidate": int(label_counts.min()),
            "max_label_rows_per_candidate": int(label_counts.max()),
            "label_sources": label_sources,
            "mixed_MD_frame_mean_in_training": False,
            "schema_risk": "screening_records.stage=MMGBSA also contains two MD-frame means outside this 17-compound training subset; future schema needs protocol_id and aggregation fields.",
        },
        "correction": {
            "implemented_now": "scaffold_grouped_leave_one_out benchmark",
            "retained_old_results": True,
            "next_required": "verified HTVS-to-hit canonical ID bridge before Model 0 can be scored on the same benchmark set",
        },
    }

    payload = {
        "comparison_headers": list(comparison_rows[0].keys()),
        "comparison_rows": comparison_rows,
    }
    (results_dir / "baseline_comparison_payload.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (results_dir / "phase15_predictions.json").write_text(
        json.dumps(strict_predictions, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (results_dir / "split_audit.json").write_text(
        json.dumps(split_audit, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps({"comparison_rows": comparison_rows, "split_audit": split_audit}, ensure_ascii=False, indent=2))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run ATP-Navigator Phase 1.5 strict benchmark")
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--n-bits", type=int, default=1024)
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    run_benchmark(args.project_root, top_k=args.top_k, n_bits=args.n_bits)
