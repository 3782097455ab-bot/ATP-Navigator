"""Phase 4 small-sample ranker benchmark and interaction-data audit.

This module is additive: it reads Dataset v0.2 and Phase 3 outputs, leaves all
prior models/results untouched, and writes only Phase 4 payloads and figures.

The supervised target remains the computational static MM/GBSA ordering of the
17 identity-verified candidates. It is not a biological-activity endpoint.
"""

from __future__ import annotations

import json
import math
import os
import re
import tempfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Callable

if os.name == "nt":
    os.environ.setdefault("WINDIR", os.environ.get("SystemRoot", r"C:\Windows"))
os.environ.setdefault("MPLCONFIGDIR", str(Path(tempfile.gettempdir()) / "atp_phase4_mpl"))

import lightgbm as lgb
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import xgboost as xgb
from scipy.stats import rankdata, spearmanr
from sklearn.metrics import mean_squared_error, ndcg_score
from sklearn.model_selection import LeaveOneGroupOut


RANDOM_SEED = 42
TOP_K = 5
DATASET_VERSION = "dataset_v0.2"


def relevance_labels(y: np.ndarray) -> np.ndarray:
    """Return integer relevance: lowest energy gets the largest value."""
    order = np.argsort(np.asarray(y, dtype=float), kind="stable")
    relevance = np.empty(len(order), dtype=np.int32)
    relevance[order] = np.arange(len(order), 0, -1, dtype=np.int32)
    return relevance


def ranking_metrics(y_true: np.ndarray, score_lower_better: np.ndarray, k: int = TOP_K) -> dict[str, Any]:
    y = np.asarray(y_true, dtype=float)
    pred = np.asarray(score_lower_better, dtype=float)
    n = len(y)
    effective_k = min(max(int(k), 1), n)
    true_top = set(np.argsort(y, kind="stable")[:effective_k])
    pred_top = set(np.argsort(pred, kind="stable")[:effective_k])
    recovered = len(true_top.intersection(pred_top))
    rel = n - rankdata(y, method="average") + 1.0
    ndcg = ndcg_score(rel.reshape(1, -1), (-pred).reshape(1, -1), k=effective_k)
    expected_random = (effective_k * effective_k) / n
    return {
        "spearman": float(spearmanr(y, pred).statistic),
        "ndcg_at_5": float(ndcg),
        "top_k": effective_k,
        "recovered_hits": recovered,
        "true_hits": effective_k,
        "top_k_enrichment": float(recovered / expected_random),
        "hit_recovery": float(recovered / effective_k),
    }


def enrichment_curve(y_true: np.ndarray, score_lower_better: np.ndarray, max_k: int = 10) -> list[dict[str, Any]]:
    y = np.asarray(y_true, dtype=float)
    pred = np.asarray(score_lower_better, dtype=float)
    n = len(y)
    rows: list[dict[str, Any]] = []
    for k in range(1, min(max_k, n) + 1):
        true_top = set(np.argsort(y, kind="stable")[:k])
        pred_top = set(np.argsort(pred, kind="stable")[:k])
        recovered = len(true_top.intersection(pred_top))
        expected = (k * k) / n
        rows.append(
            {
                "k": k,
                "recovered_hits": recovered,
                "hit_recovery": recovered / k,
                "top_k_enrichment": recovered / expected,
            }
        )
    return rows


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


def make_lgb_ranker() -> lgb.LGBMRanker:
    return lgb.LGBMRanker(
        objective="lambdarank",
        metric="ndcg",
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


def make_xgb_ranker() -> xgb.XGBRanker:
    return xgb.XGBRanker(
        objective="rank:ndcg",
        eval_metric="ndcg@5",
        n_estimators=160,
        learning_rate=0.03,
        max_depth=3,
        min_child_weight=1.0,
        subsample=0.9,
        colsample_bytree=0.45,
        reg_alpha=0.1,
        reg_lambda=1.0,
        tree_method="hist",
        lambdarank_pair_method="topk",
        lambdarank_num_pair_per_sample=5,
        random_state=RANDOM_SEED,
        n_jobs=1,
    )


def run_logo(
    x: pd.DataFrame,
    y: np.ndarray,
    groups: np.ndarray,
    model_factory: Callable[[], Any],
    *,
    ranker: bool,
) -> tuple[np.ndarray, np.ndarray]:
    predictions = np.full(len(y), np.nan, dtype=float)
    folds = np.full(len(y), -1, dtype=int)
    splitter = LeaveOneGroupOut()
    for fold_id, (train_idx, test_idx) in enumerate(splitter.split(x, y, groups), start=1):
        model = model_factory()
        x_train = x.iloc[train_idx]
        x_test = x.iloc[test_idx]
        if ranker:
            rel = relevance_labels(y[train_idx])
            if isinstance(model, lgb.LGBMRanker):
                model.fit(x_train, rel, group=[len(train_idx)])
            else:
                qid = np.zeros(len(train_idx), dtype=np.int32)
                model.fit(x_train, rel, qid=qid, verbose=False)
            # Rankers emit higher-is-better utility; store negative utility so
            # every evaluation column follows ATP-Navigator lower-is-better.
            predictions[test_idx] = -np.asarray(model.predict(x_test), dtype=float)
        else:
            model.fit(x_train, y[train_idx])
            predictions[test_idx] = np.asarray(model.predict(x_test), dtype=float)
        folds[test_idx] = fold_id
    if np.isnan(predictions).any() or (folds < 0).any():
        raise RuntimeError("Incomplete out-of-fold predictions")
    return predictions, folds


def load_phase3_predictions(project_root: Path, sample_ids: list[str]) -> dict[str, np.ndarray]:
    path = project_root / "results" / "phase3_oof_predictions.csv"
    frame = pd.read_csv(path)
    id_col = next(column for column in ["compound_id", "canonical_id"] if column in frame.columns)
    model_col = "model" if "model" in frame.columns else "model_id"
    pred_col = next(
        column for column in ["predicted_score", "ranking_score", "score_lower_is_better"] if column in frame.columns
    )
    output: dict[str, np.ndarray] = {}
    for model_name, subset in frame.groupby(model_col):
        indexed = subset.drop_duplicates(id_col).set_index(id_col)
        if set(sample_ids).issubset(indexed.index):
            output[str(model_name)] = indexed.loc[sample_ids, pred_col].to_numpy(dtype=float)
    return output


def parse_contact_file(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    lines = raw.splitlines()
    events: list[tuple[int, int, str, str]] = []
    numeric_candidate_lines = 0
    rejected_numeric_lines = 0
    pattern = re.compile(rb"^\s*(\d+)\s+(\d+)\s+([A-Za-z0-9])\s+([A-Z]{3})(?:\s+.*)?\s*$")
    numeric_prefix = re.compile(rb"^\s*\d")
    for line in lines:
        if numeric_prefix.match(line):
            numeric_candidate_lines += 1
            match = pattern.match(line)
            if not match:
                rejected_numeric_lines += 1
                continue
            events.append(
                (
                    int(match.group(1)),
                    int(match.group(2)),
                    match.group(3).decode("ascii"),
                    match.group(4).decode("ascii"),
                )
            )
    unique_frames = {event[0] for event in events}
    inferred_frames = max(unique_frames) + 1 if unique_frames else 0
    residue_events: Counter[str] = Counter()
    residue_frames: defaultdict[str, set[int]] = defaultdict(set)
    for frame, residue_number, chain, residue_name in events:
        residue = f"{chain}:{residue_name}{residue_number}"
        residue_events[residue] += 1
        residue_frames[residue].add(frame)
    top_residues = []
    for residue, count in residue_events.most_common(12):
        occupied = len(residue_frames[residue])
        top_residues.append(
            {
                "residue": residue,
                "event_count": count,
                "occupied_frames": occupied,
                "occupancy": occupied / inferred_frames if inferred_frames else None,
            }
        )
    return {
        "file": path.as_posix(),
        "bytes": len(raw),
        "nul_bytes": raw.count(b"\x00"),
        "non_ascii_bytes": sum(byte > 127 for byte in raw),
        "numeric_candidate_lines": numeric_candidate_lines,
        "parsed_event_rows": len(events),
        "rejected_numeric_lines": rejected_numeric_lines,
        "parse_rate_numeric_lines": len(events) / numeric_candidate_lines if numeric_candidate_lines else None,
        "unique_event_frames": len(unique_frames),
        "max_frame": max(unique_frames) if unique_frames else None,
        "inferred_frame_count": inferred_frames,
        "top_residues": top_residues,
    }


def audit_interactions(project_root: Path) -> dict[str, Any]:
    workspace_root = project_root.parent
    systems = {
        "SYS-MD-IN2-001": workspace_root
        / "作图"
        / "作图"
        / "1-阳性化合物和蛋白的MD"
        / "图-1"
        / "raw-data",
        "SYS-MD-HIT-001": workspace_root
        / "作图"
        / "作图"
        / "3-新型苗头有化合物和蛋白复合物的MD"
        / "图-1"
        / "raw-data",
    }
    interaction_types = ["HBond", "Hydrophobic", "Ionic", "Pi-Cation", "Pi-Pi", "WaterBridge", "Halogen", "Metal"]
    output: dict[str, Any] = {"systems": {}}
    for system_id, raw_dir in systems.items():
        system_result: dict[str, Any] = {"raw_data_dir": raw_dir.relative_to(workspace_root).as_posix(), "contacts": {}}
        for interaction_type in interaction_types:
            path = raw_dir / f"PL-Contacts_{interaction_type}.dat"
            if path.exists():
                parsed = parse_contact_file(path)
                parsed["file"] = path.relative_to(workspace_root).as_posix()
                system_result["contacts"][interaction_type] = parsed
        system_frame_count = max(
            (contact.get("inferred_frame_count", 0) for contact in system_result["contacts"].values()),
            default=0,
        )
        system_result["system_frame_count_from_contact_exports"] = system_frame_count
        for contact in system_result["contacts"].values():
            for residue in contact["top_residues"]:
                residue["occupancy_file_inferred"] = residue.pop("occupancy")
                residue["occupancy_system_frames"] = (
                    residue["occupied_frames"] / system_frame_count if system_frame_count else None
                )
        trajectory_dir = (
            workspace_root / "运行" / "运行" / ("ATP-Ref-MD1" if system_id == "SYS-MD-IN2-001" else "ATP-Top1-MD2")
        )
        fragments = sorted(trajectory_dir.glob("*.xtc.baiduyun.p.downloading"))
        system_result["raw_trajectory_status"] = "incomplete_download_fragment" if fragments else "not_found"
        system_result["raw_trajectory_sources"] = [p.relative_to(workspace_root).as_posix() for p in fragments]
        output["systems"][system_id] = system_result
    return output


def plot_model_comparison(comparison: pd.DataFrame, output_path: Path) -> None:
    metrics = ["spearman", "ndcg_at_5", "top_k_enrichment", "hit_recovery"]
    fig, axes = plt.subplots(1, 4, figsize=(16, 4.3))
    labels = comparison["model_id"].tolist()
    colors = ["#6B7280", "#94A3B8", "#2563EB", "#0F766E", "#B45309"][: len(labels)]
    for axis, metric in zip(axes, metrics):
        values = comparison[metric].to_numpy(dtype=float)
        axis.bar(labels, values, color=colors)
        axis.set_title(metric.replace("_", " "))
        axis.tick_params(axis="x", rotation=35, labelsize=8)
        axis.grid(axis="y", alpha=0.2)
        if metric in {"spearman", "ndcg_at_5", "hit_recovery"}:
            axis.set_ylim(-1.0 if metric == "spearman" else 0.0, 1.0)
    fig.suptitle("Phase 4 strict comparison (n=17; computational MM/GBSA ordering)", fontsize=12)
    fig.tight_layout()
    fig.savefig(output_path, dpi=220, bbox_inches="tight")
    plt.close(fig)


def plot_enrichment(curves: pd.DataFrame, output_path: Path) -> None:
    fig, axis = plt.subplots(figsize=(8.5, 5.2))
    for model_id, subset in curves.groupby("model_id", sort=False):
        axis.plot(subset["k"], subset["top_k_enrichment"], marker="o", linewidth=1.8, label=model_id)
    axis.axhline(1.0, color="#111827", linestyle="--", linewidth=1, label="random expectation")
    axis.set_xlabel("k")
    axis.set_ylabel("Top-k enrichment")
    axis.set_title("Top-k enrichment under the fixed Phase 4 benchmark")
    axis.set_xticks(sorted(curves["k"].unique()))
    axis.grid(alpha=0.2)
    axis.legend(fontsize=8, ncol=2)
    fig.tight_layout()
    fig.savefig(output_path, dpi=220, bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    project_root = Path(__file__).resolve().parents[1]
    results_dir = project_root / "results"
    figures_dir = results_dir / "figures"
    figures_dir.mkdir(parents=True, exist_ok=True)

    samples = pd.read_csv(project_root / "data" / DATASET_VERSION / "samples.csv")
    manifest = pd.read_csv(project_root / "data" / DATASET_VERSION / "feature_manifest.csv")
    feature_names = manifest.loc[manifest["used_in_model2"].astype(str).str.lower().eq("true"), "feature"].tolist()
    if len(samples) != 17 or samples["compound_id"].nunique() != 17:
        raise ValueError("Phase 4 strict benchmark requires the 17 unique Dataset v0.2 candidates")
    forbidden = [name for name in feature_names if "label" in name.lower() or "mmgbsa" in name.lower()]
    if forbidden:
        raise ValueError(f"Target leakage columns detected: {forbidden}")
    missing = [name for name in feature_names if name not in samples.columns]
    if missing:
        raise ValueError(f"Feature columns missing from samples.csv: {missing[:10]}")

    # Match Phase 3's float64 matrix exactly so Model 2 is a reproducible
    # preserved comparator rather than a subtly altered reimplementation.
    x = samples[feature_names].astype(float)
    y = samples["label_score"].to_numpy(dtype=float)
    groups = samples["scaffold"].astype(str).to_numpy()
    sample_ids = samples["compound_id"].astype(str).tolist()

    regression_oof, fold_ids = run_logo(x, y, groups, make_regressor, ranker=False)
    lgb_rank_oof, lgb_folds = run_logo(x, y, groups, make_lgb_ranker, ranker=True)
    xgb_rank_oof, xgb_folds = run_logo(x, y, groups, make_xgb_ranker, ranker=True)
    if not (np.array_equal(fold_ids, lgb_folds) and np.array_equal(fold_ids, xgb_folds)):
        raise RuntimeError("Model folds are not identical")

    prior = load_phase3_predictions(project_root, sample_ids)
    model0 = samples["glide_docking_score"].to_numpy(dtype=float)
    legacy = next((values for name, values in prior.items() if "baseline" in name.lower() or "legacy" in name.lower()), None)
    phase3_model2 = next((values for name, values in prior.items() if "enhanced" in name.lower() or name == "Model 2"), None)
    regression_benchmark = phase3_model2 if phase3_model2 is not None else regression_oof

    model_specs: list[dict[str, Any]] = [
        {
            "model_id": "Model 0",
            "model": "docking_only",
            "scores": model0,
            "protocol": "same_population_direct_ranking",
            "score_scale": "Glide energy-like; lower is better",
            "rmse_applicable": True,
            "notes": "Preserved non-learned baseline.",
        }
    ]
    if legacy is not None:
        model_specs.append(
            {
                "model_id": "Legacy P1 LightGBM",
                "model": "lightgbm_baseline",
                "scores": legacy,
                "protocol": "scaffold_grouped_leave_one_group_out",
                "score_scale": "MMGBSA surrogate; lower is better",
                "rmse_applicable": True,
                "notes": "Preserved Phase 1 out-of-fold baseline.",
            }
        )
    model_specs.extend(
        [
            {
                "model_id": "Model 2",
                "model": "lightgbm_regression_enhanced",
                "scores": regression_benchmark,
                "protocol": "scaffold_grouped_leave_one_group_out",
                "score_scale": "MMGBSA surrogate; lower is better",
                "rmse_applicable": True,
                "notes": "Preserved Phase 3 enhanced-feature OOF comparator under the same scaffold folds.",
            },
            {
                "model_id": "Model 3",
                "model": "lightgbm_lambdarank",
                "scores": lgb_rank_oof,
                "protocol": "scaffold_grouped_leave_one_group_out",
                "score_scale": "negative ranking utility; lower is better; arbitrary scale",
                "rmse_applicable": False,
                "notes": "LambdaRank objective with integer within-training-fold relevance; no RMSE interpretation.",
            },
            {
                "model_id": "Model 4",
                "model": "xgboost_ranker_ndcg5",
                "scores": xgb_rank_oof,
                "protocol": "scaffold_grouped_leave_one_group_out",
                "score_scale": "negative ranking utility; lower is better; arbitrary scale",
                "rmse_applicable": False,
                "notes": "XGBoost rank:ndcg with top-k pairs fixed at k=5; no RMSE interpretation.",
            },
        ]
    )

    comparison_rows: list[dict[str, Any]] = []
    prediction_rows: list[dict[str, Any]] = []
    curve_rows: list[dict[str, Any]] = []
    for spec in model_specs:
        scores = np.asarray(spec["scores"], dtype=float)
        metrics = ranking_metrics(y, scores, TOP_K)
        row = {
            "model_id": spec["model_id"],
            "model": spec["model"],
            "dataset_version": DATASET_VERSION,
            "evaluation_population": "verified_17_candidate_common_set",
            "evaluation_samples": len(y),
            "scaffold_groups": int(pd.Series(groups).nunique()),
            "benchmark_protocol": spec["protocol"],
            "feature_set": "Glide docking score" if spec["model_id"] == "Model 0" else "Phase 3 enhanced feature set (1089)" if spec["model_id"] in {"Model 2", "Model 3", "Model 4"} else "Phase 1 feature set",
            "feature_count": 1 if spec["model_id"] == "Model 0" else len(feature_names) if spec["model_id"] in {"Model 2", "Model 3", "Model 4"} else 1035,
            "score_scale": spec["score_scale"],
            "spearman": metrics["spearman"],
            "rmse": float(math.sqrt(mean_squared_error(y, scores))) if spec["rmse_applicable"] else None,
            **{key: metrics[key] for key in ["ndcg_at_5", "top_k", "recovered_hits", "true_hits", "top_k_enrichment", "hit_recovery"]},
            "target_definition": "computational_static_MMGBSA_ordering_not_biological_activity",
            "status": "ok",
            "notes": spec["notes"],
        }
        comparison_rows.append(row)
        for index, sample in samples.reset_index(drop=True).iterrows():
            prediction_rows.append(
                {
                    "model_id": spec["model_id"],
                    "model": spec["model"],
                    "compound_id": sample["compound_id"],
                    "compound_code": sample["compound_code"],
                    "historical_alias": sample["historical_alias"],
                    "scaffold_fold": int(fold_ids[index]) if spec["model_id"] not in {"Model 0"} else None,
                    "observed_mmgbsa_score": float(y[index]),
                    "ranking_score_lower_is_better": float(scores[index]),
                    "observed_rank": int(rankdata(y, method="ordinal")[index]),
                    "predicted_rank": int(rankdata(scores, method="ordinal")[index]),
                    "is_true_top5": bool(index in set(np.argsort(y, kind="stable")[:TOP_K])),
                    "is_predicted_top5": bool(index in set(np.argsort(scores, kind="stable")[:TOP_K])),
                    "label_semantics": "computational_static_MMGBSA_not_biological_activity",
                }
            )
        for curve in enrichment_curve(y, scores, max_k=10):
            curve_rows.append({"model_id": spec["model_id"], "model": spec["model"], **curve})

    comparison = pd.DataFrame(comparison_rows)
    predictions = pd.DataFrame(prediction_rows)
    curves = pd.DataFrame(curve_rows)
    plot_model_comparison(comparison, figures_dir / "phase4_ranking_model_comparison.png")
    plot_enrichment(curves, figures_dir / "phase4_topk_enrichment_curve.png")

    interaction_audit = audit_interactions(project_root)
    def json_records(frame: pd.DataFrame) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        for raw_record in frame.to_dict(orient="records"):
            record: dict[str, Any] = {}
            for key, value in raw_record.items():
                if isinstance(value, (float, np.floating)) and not np.isfinite(value):
                    record[key] = None
                elif isinstance(value, np.generic):
                    record[key] = value.item()
                else:
                    record[key] = value
            records.append(record)
        return records

    payload = {
        "comparison_headers": comparison.columns.tolist(),
        "comparison_rows": json_records(comparison),
        "prediction_headers": predictions.columns.tolist(),
        "prediction_rows": json_records(predictions),
        "curve_rows": curves.to_dict(orient="records"),
        "environment": {
            "lightgbm": lgb.__version__,
            "xgboost": xgb.__version__,
            "pandas": pd.__version__,
            "numpy": np.__version__,
        },
        "fresh_retrain_vs_preserved_phase3_max_abs_difference": None,
    }
    if phase3_model2 is not None:
        payload["fresh_retrain_vs_preserved_phase3_max_abs_difference"] = float(
            np.max(np.abs(regression_oof - phase3_model2))
        )
    (results_dir / "phase4_ranker_payload.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    (results_dir / "phase4_interaction_audit.json").write_text(
        json.dumps(interaction_audit, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(comparison.to_string(index=False))
    print(
        json.dumps(
            {
                "fresh_retrain_vs_preserved_phase3_max_abs_difference": payload[
                    "fresh_retrain_vs_preserved_phase3_max_abs_difference"
                ]
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
