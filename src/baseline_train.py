"""Train ATP-Navigator Phase 1 docking-only and classical ML baselines."""

from __future__ import annotations

import argparse
import importlib
import json
import os
import platform
from pathlib import Path
from typing import Callable

os.environ.setdefault("LOKY_MAX_CPU_COUNT", "2")

import joblib
import numpy as np
import pandas as pd
from sklearn.base import RegressorMixin
from sklearn.ensemble import RandomForestRegressor
from sklearn.feature_selection import VarianceThreshold
from sklearn.impute import SimpleImputer
from sklearn.model_selection import LeaveOneOut, cross_val_predict
from sklearn.pipeline import Pipeline

from evaluation import evaluate_predictions, save_metric_chart, save_prediction_chart
from feature_pipeline import FeatureConfig, MoleculeFeaturePipeline


RANDOM_SEED = 42


def model_factories() -> dict[str, Callable[[], RegressorMixin]]:
    factories: dict[str, Callable[[], RegressorMixin]] = {
        "random_forest": lambda: RandomForestRegressor(
            n_estimators=500,
            max_features="sqrt",
            min_samples_leaf=2,
            random_state=RANDOM_SEED,
            n_jobs=1,
        )
    }
    try:
        from xgboost import XGBRegressor

        factories["xgboost"] = lambda: XGBRegressor(
            n_estimators=300,
            max_depth=3,
            learning_rate=0.03,
            subsample=0.8,
            colsample_bytree=0.8,
            reg_alpha=0.05,
            reg_lambda=1.0,
            objective="reg:squarederror",
            random_state=RANDOM_SEED,
            n_jobs=1,
            verbosity=0,
        )
    except ImportError:
        pass
    try:
        from lightgbm import LGBMRegressor

        factories["lightgbm"] = lambda: LGBMRegressor(
            n_estimators=300,
            num_leaves=7,
            max_depth=3,
            learning_rate=0.03,
            min_child_samples=3,
            subsample=0.8,
            colsample_bytree=0.8,
            reg_lambda=1.0,
            random_state=RANDOM_SEED,
            verbosity=-1,
        )
    except ImportError:
        pass
    return factories


def make_pipeline(regressor: RegressorMixin) -> Pipeline:
    return Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="median", keep_empty_features=False)),
            ("variance", VarianceThreshold(threshold=0.0)),
            ("regressor", regressor),
        ]
    )


def docking_only_ranking(feature_matrix: pd.DataFrame) -> tuple[pd.DataFrame, str | None]:
    score_column = None
    for candidate in ("score_Docking", "score_HTVS"):
        if candidate in feature_matrix.columns and feature_matrix[candidate].notna().any():
            score_column = candidate
            break
    if score_column is None:
        return pd.DataFrame(columns=["canonical_id", "docking_score", "rank", "score_source"]), None

    ranking = feature_matrix.loc[
        feature_matrix[score_column].notna(),
        ["canonical_id", "historical_alias", score_column],
    ].copy()
    ranking = ranking.rename(columns={score_column: "docking_score"})
    ranking["rank"] = ranking["docking_score"].rank(method="min", ascending=True).astype(int)
    ranking["score_source"] = score_column.removeprefix("score_")
    ranking = ranking.sort_values(["rank", "canonical_id"], kind="stable")
    return ranking, score_column


def dependency_versions() -> dict[str, str | None]:
    output: dict[str, str | None] = {"python": platform.python_version()}
    for module_name in ["numpy", "pandas", "sklearn", "scipy", "rdkit", "xgboost", "lightgbm"]:
        try:
            module = importlib.import_module(module_name)
            output[module_name] = getattr(module, "__version__", "installed")
        except ImportError:
            output[module_name] = None
    return output


def train_baselines(
    project_root: Path,
    *,
    target_stage: str = "MMGBSA",
    top_k: int = 5,
    n_bits: int = 1024,
) -> None:
    project_root = project_root.resolve()
    results_dir = project_root / "results"
    models_dir = project_root / "models"
    results_dir.mkdir(parents=True, exist_ok=True)
    models_dir.mkdir(parents=True, exist_ok=True)

    feature_pipeline = MoleculeFeaturePipeline(project_root, FeatureConfig(n_bits=n_bits))
    feature_matrix, feature_metadata = feature_pipeline.build()
    feature_pipeline.save(feature_matrix, feature_metadata)

    target_column = f"score_{target_stage}"
    if target_column not in feature_matrix.columns:
        raise ValueError(f"Target stage not found in current data: {target_stage}")

    metrics_rows: list[dict[str, object]] = []
    prediction_parts: list[pd.DataFrame] = []

    docking_ranking, docking_column = docking_only_ranking(feature_matrix)
    docking_ranking.to_csv(results_dir / "docking_only_ranking.csv", index=False)
    if docking_column:
        overlap = feature_matrix.loc[
            feature_matrix[docking_column].notna() & feature_matrix[target_column].notna(),
            ["canonical_id", target_column, docking_column],
        ]
        docking_metrics = evaluate_predictions(
            overlap[target_column], overlap[docking_column], top_k=top_k
        )
    else:
        docking_metrics = evaluate_predictions([], [], top_k=top_k)
    metrics_rows.append(
        {
            "model": "docking_only",
            "target_stage": target_stage,
            "feature_count": 1 if docking_column else 0,
            **docking_metrics,
        }
    )

    candidate_features = feature_pipeline.model_feature_columns(feature_matrix, target_stage)
    train_mask = feature_matrix[target_column].notna() & feature_matrix["smiles_valid"].eq(True)
    train = feature_matrix.loc[train_mask].copy()
    usable_features = [
        column
        for column in candidate_features
        if pd.to_numeric(train[column], errors="coerce").notna().any()
    ]
    X = train[usable_features].apply(pd.to_numeric, errors="coerce")
    y = pd.to_numeric(train[target_column], errors="coerce")

    if len(train) < 5:
        raise ValueError(
            f"Only {len(train)} rows have both valid SMILES and {target_stage}; at least 5 are required."
        )

    factories = model_factories()
    expected_models = ["random_forest", "xgboost", "lightgbm"]
    cv = LeaveOneOut()
    for model_name in expected_models:
        if model_name not in factories:
            metrics_rows.append(
                {
                    "model": model_name,
                    "target_stage": target_stage,
                    "feature_count": len(usable_features),
                    "n_samples": len(train),
                    "spearman": np.nan,
                    "rmse": np.nan,
                    "ndcg": np.nan,
                    "top_k": min(top_k, len(train)),
                    "top_k_recall": np.nan,
                    "status": "missing_dependency",
                }
            )
            continue

        estimator = make_pipeline(factories[model_name]())
        predictions = cross_val_predict(estimator, X, y, cv=cv, n_jobs=1, method="predict")
        model_metrics = evaluate_predictions(y, predictions, top_k=top_k)
        metrics_rows.append(
            {
                "model": model_name,
                "target_stage": target_stage,
                "feature_count": len(usable_features),
                **model_metrics,
            }
        )
        prediction_part = train[["canonical_id", "historical_alias", "smiles"]].copy()
        prediction_part["model"] = model_name
        prediction_part["observed_score"] = y.to_numpy()
        prediction_part["predicted_score"] = predictions
        prediction_part["observed_rank"] = prediction_part["observed_score"].rank(
            method="min", ascending=True
        ).astype(int)
        prediction_part["predicted_rank"] = prediction_part["predicted_score"].rank(
            method="min", ascending=True
        ).astype(int)
        prediction_parts.append(prediction_part)

        estimator.fit(X, y)
        joblib.dump(estimator, models_dir / f"{model_name}_{target_stage.lower()}_baseline.joblib")

    metrics = pd.DataFrame(metrics_rows)
    metrics.to_csv(results_dir / "metrics.csv", index=False)
    predictions = (
        pd.concat(prediction_parts, ignore_index=True)
        if prediction_parts
        else pd.DataFrame(
            columns=[
                "canonical_id",
                "historical_alias",
                "smiles",
                "model",
                "observed_score",
                "predicted_score",
                "observed_rank",
                "predicted_rank",
            ]
        )
    )
    predictions.to_csv(results_dir / "predictions.csv", index=False)
    predictions.sort_values(["model", "predicted_rank", "canonical_id"], kind="stable").to_csv(
        results_dir / "candidate_ranking.csv", index=False
    )
    save_prediction_chart(predictions, results_dir / "predicted_vs_observed.png")
    save_metric_chart(metrics, results_dir / "ranking_metrics.png")

    run_metadata = {
        "phase": "Phase 1 baseline",
        "target_stage": target_stage,
        "score_direction": "lower_is_better",
        "cv": "leave_one_out",
        "random_seed": RANDOM_SEED,
        "training_rows": int(len(train)),
        "usable_feature_count": int(len(usable_features)),
        "usable_feature_groups": {
            "morgan": sum(column.startswith("morgan_") for column in usable_features),
            "physicochemical": sum(column.startswith("desc_") for column in usable_features),
            "screening_evidence": sum(column.startswith("score_") for column in usable_features),
            "quickprop": sum(
                column.lower().startswith(("quickprop_", "qp_", "r_qp_", "i_qp_"))
                for column in usable_features
            ),
        },
        "docking_target_overlap": int(
            (
                feature_matrix[docking_column].notna() & feature_matrix[target_column].notna()
            ).sum()
        )
        if docking_column
        else 0,
        "limitations": [
            "Dataset v0.1 has no verified canonical-id bridge between HTVS/Docking records and the MMGBSA hit set.",
            "QuickProp fields are not present in molecules.csv or screening_records.csv.",
            "MMGBSA training set is a small computed-label set, not experimental activity data.",
        ],
        "dependencies": dependency_versions(),
    }
    (results_dir / "run_metadata.json").write_text(
        json.dumps(run_metadata, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train ATP-Navigator Phase 1 baselines")
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--target-stage", default="MMGBSA")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--n-bits", type=int, default=1024)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    train_baselines(
        args.project_root,
        target_stage=args.target_stage,
        top_k=args.top_k,
        n_bits=args.n_bits,
    )


if __name__ == "__main__":
    main()
