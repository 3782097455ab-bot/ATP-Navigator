"""Compare frozen rankings to reviewed same-assay measurements. No training.

Retrospective concordance only; not a prospective trial, success probability,
cost reduction, or clinical validation. Censored results are not point labels.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from workspace_io import file_hash, now, read_json, write_json_new


def evaluate(snapshot_dir: Path, ranking_path: Path, output: Path) -> dict:
    manifest = read_json(snapshot_dir / "iteration_manifest.json")
    records_path = snapshot_dir / "reviewed_records.csv"
    if file_hash(records_path) != manifest["record_sha256"]:
        raise ValueError("Snapshot hash mismatch")
    if output.exists():
        raise FileExistsError("Choose a new evaluation directory")
    records = pd.read_csv(records_path, keep_default_na=False)
    ranking = pd.read_csv(ranking_path, keep_default_na=False)
    required = {"canonical_smiles", "final_score", "docking_score", "rank"}
    if not required.issubset(ranking):
        raise ValueError("Frozen ranking columns missing")
    ranking = ranking.loc[pd.to_numeric(ranking["rank"], errors="coerce").notna()].copy()
    if ranking["canonical_smiles"].duplicated().any():
        raise ValueError("Frozen ranking has duplicate structures")
    rows = []
    selected = records.loc[records["dataset_role"].isin(["holdout", "benchmark"]) & records["comparator"].eq("=")]
    for stratum, frame in selected.groupby("stratum", sort=True):
        endpoint = frame.iloc[0]["activity_type"]
        # Only same-protocol replicates: median is declared before evaluation.
        observed = frame.groupby("canonical_smiles", as_index=False)["numeric_value"].median()
        joined = ranking.merge(observed, on="canonical_smiles", validate="one_to_one")
        direction = 1 if endpoint == "CC50" else -1
        truth = direction * joined["numeric_value"].astype(float)
        for model, values in [("Docking_only", -pd.to_numeric(joined["docking_score"], errors="coerce")),
                              ("ATP_Navigator_frozen_profile", -pd.to_numeric(joined["rank"], errors="coerce"))]:
            valid = values.notna() & truth.notna() & np.isfinite(values) & np.isfinite(truth)
            n = int(valid.sum())
            enough = n >= 5 and truth[valid].nunique() > 1 and values[valid].nunique() > 1
            rows.append({"stratum": stratum, "model": model, "n_unique_measured_structures": n,
                         "status": "retrospective_concordance_only" if enough else "small_data_or_constant_values",
                         "spearman": float(spearmanr(values[valid], truth[valid]).statistic) if enough else None,
                         "rmse": None, "rmse_reason": "decision_rank_and_assay_values_have_different_units",
                         "endpoint": endpoint, "unit": frame.iloc[0]["unit"]})
    output.mkdir(parents=True, exist_ok=False)
    summary = {"created_at": now(), "status": "empty_no_matched_reviewed_holdout" if not rows else "see_stratum_metrics",
               "metrics": rows, "ranking_sha256": file_hash(ranking_path), "snapshot_id": manifest["snapshot_id"],
               "snapshot_sha256": file_hash(records_path), "training_performed": False,
               "prospective_validity": "not_established", "model_promotion": "not_allowed",
               "replicate_aggregation": "median_within_exact_stratum",
               "minimum_n_for_descriptive_correlation": 5,
               "limitations": "Five is only a reporting gate, not statistical adequacy; no cost or success-rate estimate."}
    write_json_new(output / "feedback_evaluation.json", summary)
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--ranking", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(evaluate(args.snapshot, args.ranking, args.output), ensure_ascii=False, indent=2))
