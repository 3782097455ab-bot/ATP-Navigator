"""Create additive Phase 2 figures from existing strict benchmark outputs."""

from __future__ import annotations

import json
import os
from pathlib import Path

os.environ.setdefault("WINDIR", r"C:\Windows")
os.environ.setdefault("MPLBACKEND", "Agg")
_MPL_CONFIG = Path(__file__).resolve().parents[1] / "results" / ".matplotlib"
_MPL_CONFIG.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", str(_MPL_CONFIG))

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.patches import FancyBboxPatch


COLORS = {
    "random_forest": "#4C78A8",
    "xgboost": "#F58518",
    "lightgbm": "#54A24B",
}


def configure_style() -> None:
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.titleweight": "bold",
            "figure.dpi": 160,
        }
    )


def baseline_comparison(project_root: Path, output_dir: Path) -> None:
    data = pd.read_csv(project_root / "results" / "baseline_comparison.csv")
    ok = data.loc[data["status"].eq("ok")].copy()
    metrics = [
        ("spearman", "Spearman"),
        ("ndcg", "NDCG@5"),
        ("top_k_enrichment", "Top-5 enrichment"),
        ("hit_recovery", "Hit recovery"),
    ]
    fig, axes = plt.subplots(1, 4, figsize=(13.5, 3.8))
    for axis, (column, title) in zip(axes, metrics):
        values = ok[column].astype(float).to_numpy()
        names = ok["model"].str.replace("_", " ").str.title().to_list()
        colors = [COLORS.get(model, "#777777") for model in ok["model"]]
        bars = axis.bar(names, values, color=colors, width=0.68)
        axis.set_title(title, fontsize=10)
        axis.tick_params(axis="x", rotation=34, labelsize=8)
        axis.grid(axis="y", alpha=0.2)
        axis.bar_label(bars, fmt="%.2f", padding=2, fontsize=8)
        upper = max(1.0, float(values.max()) * 1.25) if column != "top_k_enrichment" else float(values.max()) * 1.25
        axis.set_ylim(0, upper)
    fig.suptitle("Phase 1.5 strict baseline comparison", fontsize=14, fontweight="bold")
    fig.text(
        0.5,
        0.01,
        "Scaffold-grouped OOF, n=17. Labels are computational MM/GBSA ranks, not biological activity.\n"
        "Docking-only is not plotted because only 1/17 candidates has a confirmed readable-HTVS bridge.",
        ha="center",
        va="bottom",
        fontsize=8,
        color="#444444",
    )
    fig.tight_layout(rect=(0, 0.12, 1, 0.92))
    fig.savefig(output_dir / "baseline_model_comparison.png", bbox_inches="tight")
    plt.close(fig)


def ranking_flow(output_dir: Path) -> None:
    fig, axis = plt.subplots(figsize=(14, 4.8))
    axis.set_xlim(0, 14)
    axis.set_ylim(0, 5)
    axis.axis("off")
    nodes = [
        (0.4, 2.0, 2.0, 1.1, "Schrodinger\noutputs", "#DCEAF7"),
        (3.0, 2.0, 2.0, 1.1, "Identity gate\nverified joins only", "#FFF1CC"),
        (5.6, 2.0, 2.1, 1.1, "Feature blocks\nMorgan / descriptors\nDocking / ADMET", "#E1F1E8"),
        (8.3, 2.0, 2.1, 1.1, "Model ablation\nM0 - M3", "#E9E2F5"),
        (11.0, 2.0, 2.2, 1.1, "Scaffold-grouped\nOOF evaluation", "#F8E0DF"),
    ]
    for x, y, width, height, label, color in nodes:
        patch = FancyBboxPatch(
            (x, y), width, height, boxstyle="round,pad=0.04,rounding_size=0.08",
            linewidth=1.2, edgecolor="#3F4C5A", facecolor=color,
        )
        axis.add_patch(patch)
        axis.text(x + width / 2, y + height / 2, label, ha="center", va="center", fontsize=10)
    for left, right in zip(nodes[:-1], nodes[1:]):
        axis.annotate(
            "", xy=(right[0], 2.55), xytext=(left[0] + left[2], 2.55),
            arrowprops={"arrowstyle": "->", "lw": 1.6, "color": "#3F4C5A"},
        )
    axis.annotate(
        "No verified bridge -> keep missing; do not merge by name or row order",
        xy=(4.0, 1.95), xytext=(4.0, 0.75), ha="center", va="center", fontsize=9, color="#8A5A00",
        arrowprops={"arrowstyle": "-[", "lw": 1.0, "color": "#8A5A00"},
    )
    axis.text(7, 4.35, "ATP-Navigator AI-enhanced candidate-ranking workflow", ha="center", fontsize=15, fontweight="bold")
    axis.text(
        7, 0.25,
        "Output: interpretable computational priority with evidence coverage and uncertainty warnings — not an activity prediction.",
        ha="center", fontsize=9, color="#444444",
    )
    fig.savefig(output_dir / "ai_ranking_workflow.png", bbox_inches="tight")
    plt.close(fig)


def topk_enrichment(project_root: Path, output_dir: Path) -> None:
    predictions = pd.DataFrame(json.loads((project_root / "results" / "phase15_predictions.json").read_text(encoding="utf-8")))
    models = list(predictions["model"].drop_duplicates())
    fig, axis = plt.subplots(figsize=(7.4, 4.8))
    for model in models:
        rows = predictions.loc[predictions["model"].eq(model)].copy()
        n = len(rows)
        ks = np.arange(1, min(8, n // 2) + 1)
        observed_order = rows.sort_values("observed_score")["canonical_id"].tolist()
        predicted_order = rows.sort_values("predicted_score")["canonical_id"].tolist()
        enrichment = []
        for k in ks:
            recovered = len(set(observed_order[:k]).intersection(predicted_order[:k]))
            expected = (k * k) / n
            enrichment.append(recovered / expected if expected else np.nan)
        axis.plot(
            ks, enrichment, marker="o", linewidth=2.0,
            label={"random_forest": "Random Forest", "xgboost": "XGBoost", "lightgbm": "LightGBM"}.get(model, model),
            color=COLORS.get(model, "#777777"),
        )
    axis.axhline(1.0, color="#666666", linestyle="--", linewidth=1.2, label="Random expectation")
    axis.set_xlabel("k (computational top-k)")
    axis.set_ylabel("Enrichment factor")
    axis.set_title("Strict OOF top-k enrichment", fontsize=13)
    axis.grid(alpha=0.2)
    axis.legend(frameon=False, ncol=2, fontsize=8)
    fig.text(
        0.5, 0.01,
        "n=17; lower MM/GBSA and lower predicted score rank higher. Stair steps reflect the small candidate set.",
        ha="center", fontsize=8, color="#444444",
    )
    fig.tight_layout(rect=(0, 0.06, 1, 1))
    fig.savefig(output_dir / "top_k_enrichment_curve.png", bbox_inches="tight")
    plt.close(fig)


def interpretability_readiness(output_dir: Path) -> None:
    fig, axis = plt.subplots(figsize=(10.5, 4.6))
    axis.axis("off")
    axis.set_xlim(0, 10.5)
    axis.set_ylim(0, 4.6)
    cards = [
        (0.4, "Current evidence", "Strict OOF predictions exist\nNo fold-wise feature importance yet", "#F8E0DF"),
        (3.7, "Phase 2 method", "Fold-wise permutation importance\nAggregate by feature group", "#FFF1CC"),
        (7.0, "Allowed claim", "Ranking sensitivity evidence\nExploratory, non-causal", "#E1F1E8"),
    ]
    for x, title, body, color in cards:
        patch = FancyBboxPatch((x, 1.25), 2.8, 1.75, boxstyle="round,pad=0.05", facecolor=color, edgecolor="#3F4C5A")
        axis.add_patch(patch)
        axis.text(x + 1.4, 2.62, title, ha="center", va="center", fontsize=11, fontweight="bold")
        axis.text(x + 1.4, 1.92, body, ha="center", va="center", fontsize=9)
    axis.annotate("", xy=(3.65, 2.12), xytext=(3.2, 2.12), arrowprops={"arrowstyle": "->", "lw": 1.5})
    axis.annotate("", xy=(6.95, 2.12), xytext=(6.5, 2.12), arrowprops={"arrowstyle": "->", "lw": 1.5})
    axis.text(5.25, 4.0, "Model interpretability: readiness and guardrails", ha="center", fontsize=14, fontweight="bold")
    axis.text(
        5.25, 0.55,
        "No SHAP or feature-importance ranking is shown yet: the existing full-fit models cannot represent strict OOF explanations.",
        ha="center", fontsize=9, color="#555555",
    )
    fig.savefig(output_dir / "model_interpretability_readiness.png", bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    project_root = Path(__file__).resolve().parents[1]
    output_dir = project_root / "results" / "figures"
    output_dir.mkdir(parents=True, exist_ok=True)
    configure_style()
    baseline_comparison(project_root, output_dir)
    ranking_flow(output_dir)
    topk_enrichment(project_root, output_dir)
    interpretability_readiness(output_dir)
    print(json.dumps({"output_dir": str(output_dir), "figures": sorted(path.name for path in output_dir.glob("*.png"))}, indent=2))


if __name__ == "__main__":
    main()
