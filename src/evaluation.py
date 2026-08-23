"""Ranking and regression metrics for ATP-Navigator baselines."""

from __future__ import annotations

import math
import os
import tempfile
from pathlib import Path
from typing import Iterable

if os.name == "nt":
    os.environ.setdefault("WINDIR", os.environ.get("SystemRoot", r"C:\Windows"))
os.environ.setdefault("MPLCONFIGDIR", str(Path(tempfile.gettempdir()) / "atp_navigator_mpl"))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.stats import rankdata, spearmanr
from sklearn.metrics import mean_squared_error, ndcg_score


def _paired_arrays(y_true: Iterable[float], y_pred: Iterable[float]) -> tuple[np.ndarray, np.ndarray]:
    frame = pd.DataFrame({"true": y_true, "pred": y_pred}).dropna()
    return frame["true"].to_numpy(dtype=float), frame["pred"].to_numpy(dtype=float)


def top_k_recall(y_true: Iterable[float], y_pred: Iterable[float], k: int = 5) -> float:
    """Recall of the k best predicted candidates against the k best true candidates.

    ATP-Navigator energy-like scores use the convention that lower is better.
    """
    true, pred = _paired_arrays(y_true, y_pred)
    if true.size == 0:
        return math.nan
    effective_k = min(max(int(k), 1), true.size)
    true_top = set(np.argsort(true, kind="stable")[:effective_k])
    pred_top = set(np.argsort(pred, kind="stable")[:effective_k])
    return len(true_top.intersection(pred_top)) / effective_k


def ranking_ndcg(y_true: Iterable[float], y_pred: Iterable[float], k: int | None = None) -> float:
    """Rank-based NDCG with lower energy treated as better."""
    true, pred = _paired_arrays(y_true, y_pred)
    if true.size < 2:
        return math.nan
    # Best (lowest) true score receives highest non-negative relevance.
    true_ranks = rankdata(true, method="average")
    relevance = true.size - true_ranks + 1.0
    return float(ndcg_score(relevance.reshape(1, -1), (-pred).reshape(1, -1), k=k))


def evaluate_predictions(
    y_true: Iterable[float],
    y_pred: Iterable[float],
    *,
    top_k: int = 5,
) -> dict[str, float | int | str]:
    true, pred = _paired_arrays(y_true, y_pred)
    if true.size < 2:
        return {
            "n_samples": int(true.size),
            "spearman": math.nan,
            "rmse": math.nan,
            "ndcg": math.nan,
            "top_k": min(top_k, int(true.size)),
            "top_k_recall": math.nan,
            "status": "not_evaluable_insufficient_overlap",
        }
    spearman = spearmanr(true, pred).statistic
    return {
        "n_samples": int(true.size),
        "spearman": float(spearman) if not np.isnan(spearman) else math.nan,
        "rmse": float(np.sqrt(mean_squared_error(true, pred))),
        "ndcg": ranking_ndcg(true, pred, k=min(top_k, true.size)),
        "top_k": min(top_k, int(true.size)),
        "top_k_recall": top_k_recall(true, pred, k=top_k),
        "status": "ok",
    }


def save_prediction_chart(predictions: pd.DataFrame, output_path: str | Path) -> None:
    usable = predictions.dropna(subset=["observed_score", "predicted_score"])
    if usable.empty:
        return
    models = sorted(usable["model"].unique())
    columns = min(3, len(models))
    rows = math.ceil(len(models) / columns)
    fig, axes = plt.subplots(rows, columns, figsize=(5 * columns, 4.2 * rows), squeeze=False)
    low = min(usable["observed_score"].min(), usable["predicted_score"].min())
    high = max(usable["observed_score"].max(), usable["predicted_score"].max())
    for axis, model in zip(axes.flat, models):
        subset = usable.loc[usable["model"] == model]
        axis.scatter(subset["observed_score"], subset["predicted_score"], alpha=0.8, s=34)
        axis.plot([low, high], [low, high], linestyle="--", color="#666666", linewidth=1)
        axis.set_title(model)
        axis.set_xlabel("Observed score (lower is better)")
        axis.set_ylabel("Out-of-fold predicted score")
        axis.grid(alpha=0.2)
    for axis in axes.flat[len(models):]:
        axis.set_visible(False)
    fig.tight_layout()
    fig.savefig(output_path, dpi=200, bbox_inches="tight")
    plt.close(fig)


def save_metric_chart(metrics: pd.DataFrame, output_path: str | Path) -> None:
    usable = metrics.loc[metrics["status"].eq("ok")].copy()
    if usable.empty:
        return
    columns = ["spearman", "ndcg", "top_k_recall"]
    figure, axes = plt.subplots(1, len(columns), figsize=(13, 4), squeeze=False)
    for axis, metric in zip(axes.flat, columns):
        axis.bar(usable["model"], usable[metric], color="#2F6B8A")
        axis.set_title(metric)
        axis.set_ylim(-1.0 if metric == "spearman" else 0.0, 1.0)
        axis.tick_params(axis="x", rotation=25)
        axis.grid(axis="y", alpha=0.2)
    figure.tight_layout()
    figure.savefig(output_path, dpi=200, bbox_inches="tight")
    plt.close(figure)
