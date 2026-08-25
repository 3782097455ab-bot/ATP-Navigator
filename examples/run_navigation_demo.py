"""Run the complete Phase 10 demo on the preserved 17 internal candidates."""

from __future__ import annotations

import hashlib
import json
import sys
import tempfile
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from input_processor import atomic_csv  # noqa: E402
from navigator_pipeline import NavigatorPipeline, atomic_json  # noqa: E402
from workflow_evaluator import evaluate_workflow, write_evaluation  # noqa: E402


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_demo_input(path: Path) -> pd.DataFrame:
    training = pd.read_csv(PROJECT_ROOT / "data/model_v3/training_table.csv")
    samples = pd.read_csv(PROJECT_ROOT / "data/dataset_v0.2/samples.csv")
    aliases = samples.set_index("compound_id")["historical_alias"].to_dict()
    quickprop = [column for column in training if column.startswith("quickprop_")]
    admet = [column for column in training if column.startswith("admet_")]
    literature = [column for column in training if column.startswith("prior_task_")]
    docking = [
        column
        for column in training
        if column.startswith("glide_") and column != "glide_docking_score"
    ]
    rows = []
    for row in training.to_dict(orient="records"):
        rows.append(
            {
                "compound_id": row["compound_id"],
                "historical_alias": aliases.get(row["compound_id"], ""),
                "SMILES": row["canonical_smiles"],
                "docking_score": row["glide_docking_score"],
                "mmgbsa_score": row["label_score"],
                "docking_features": json.dumps(
                    {column: row[column] for column in docking}, ensure_ascii=False
                ),
                "quickprop_features": json.dumps(
                    {column: row[column] for column in quickprop}, ensure_ascii=False
                ),
                "admet_features": json.dumps(
                    {column: row[column] for column in admet}, ensure_ascii=False
                ),
                "literature_features": json.dumps(
                    {column: row[column] for column in literature}, ensure_ascii=False
                ),
                "source": "preserved_internal_17_candidate_demo",
            }
        )
    demo = pd.DataFrame(rows)
    atomic_csv(demo, path)
    return demo


def system_summary(
    ranking: pd.DataFrame,
    validation: dict,
    profile: str,
    replay_match: bool,
) -> str:
    top = ranking.loc[ranking["rank"].notna()].sort_values("rank").head(6)
    table_rows = []
    for row in top.itertuples(index=False):
        alias = getattr(row, "historical_alias", "") or row.compound_id
        table_rows.append(
            f"| {int(row.rank)} | {alias} | `{row.compound_id}` | {row.final_score:.2f} | "
            f"{row.mean_rank:.2f} | {row.p_top3:.3f} | {row.risk} |"
        )
    passed = sum(bool(check["pass"]) for check in validation["checks"])
    total = len(validation["checks"])
    return f"""# ATP-Navigator Phase 10 Demo Summary

运行模式：`{profile}`  
候选数量：{len(ranking)}  
完整决策数量：{validation['complete_decision_count']}  
工作流自评：{validation['workflow_readiness']}（{passed}/{total} checks passed）  
确定性复跑一致：{str(replay_match).lower()}

## End-to-end workflow

```text
Candidate input
  → RDKit structure validation and canonicalization
  → Morgan1024 + molecular descriptors
  → preserved Model v3 / declared Model v2-A fallback
  → ATP-reference similarity + external knowledge priors
  → transparent four-component decision score
  → profile-conditioned robustness ranking
  → candidate explanation and workflow self-audit
```

## Current top experimental priorities

| Rank | Alias | Compound ID | Final score | Mean robust rank | P(Top 3) | Predicted risk band |
|---:|---|---|---:|---:|---:|---|
{chr(10).join(table_rows)}

`P(Top 3)` is conditional rank acceptability under the declared weight distribution, not biological activity probability.

## Scientific status

- Model training performed in Phase 10: no;
- Historical models modified: no;
- Experimental ATP inhibition: unknown;
- MIC: unknown;
- Experimental toxicity: unknown;
- Biological hit-rate improvement evaluated: no;
- Demonstrated capability: an auditable workflow from post-screening candidates to a frozen experimental-priority panel.
"""


def main() -> int:
    demo_dir = PROJECT_ROOT / "results/demo"
    demo_dir.mkdir(parents=True, exist_ok=True)
    input_path = demo_dir / "demo_input.csv"
    build_demo_input(input_path)
    profile = "atp_mechanism_focused"
    pipeline = NavigatorPipeline(PROJECT_ROOT)
    trace = pipeline.run(
        input_path,
        profile=profile,
        output_dir=demo_dir,
        report_path=demo_dir / "candidate_explanation.md",
    )
    first_ranking = demo_dir / "final_navigation_report.csv"
    with tempfile.TemporaryDirectory(prefix="atp_navigator_phase10_") as temporary:
        replay_dir = Path(temporary)
        pipeline.run(
            input_path,
            profile=profile,
            output_dir=replay_dir,
            report_path=replay_dir / "candidate_explanation.md",
        )
        replay_match = file_hash(first_ranking) == file_hash(
            replay_dir / "final_navigation_report.csv"
        )

    processed = pd.read_csv(demo_dir / "processed_candidate_table.csv", low_memory=False)
    ranking = pd.read_csv(first_ranking, low_memory=False)
    validation = evaluate_workflow(
        processed,
        ranking,
        model_hashes_unchanged=trace["model_change"] == "none",
        deterministic_replay=replay_match,
    )
    write_evaluation(validation, demo_dir)
    atomic_csv(ranking, demo_dir / "candidate_ranking.csv")
    (demo_dir / "system_summary.md").write_text(
        system_summary(ranking, validation, profile, replay_match), encoding="utf-8"
    )
    trace["deterministic_replay"] = replay_match
    trace["workflow_readiness"] = validation["workflow_readiness"]
    trace["demo_outputs"] = {
        "candidate_ranking": "results/demo/candidate_ranking.csv",
        "candidate_explanation": "results/demo/candidate_explanation.md",
        "system_summary": "results/demo/system_summary.md",
        "workflow_validation": "results/demo/workflow_validation.json",
        "profile_comparison": "results/demo/profile_comparison.csv",
        "profile_rank_stability": "results/demo/profile_rank_stability.csv",
        "top_candidate_consistency": "results/demo/top_candidate_consistency.csv",
    }
    atomic_json(trace, demo_dir / "pipeline_trace.json")
    print(
        json.dumps(
            {
                "phase": "Phase 10",
                "profile": profile,
                "candidate_count": len(ranking),
                "top_candidate": ranking.iloc[0]["historical_alias"],
                "workflow_readiness": validation["workflow_readiness"],
                "deterministic_replay": replay_match,
                "historical_models_modified": False,
                "experimental_values_imputed": 0,
                "output_directory": str(demo_dir.relative_to(PROJECT_ROOT)),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
