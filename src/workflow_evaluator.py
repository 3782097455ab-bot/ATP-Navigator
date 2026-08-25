"""Self-audit the Phase 10 workflow without claiming biological performance."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

import pandas as pd


EVALUATOR_VERSION = "ATP-Navigator_Phase10_WorkflowEvaluator_v1.0"


def atomic_json(payload: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", delete=False, dir=path.parent, suffix=".tmp"
    ) as handle:
        temporary = Path(handle.name)
        json.dump(payload, handle, ensure_ascii=False, indent=2, allow_nan=False)
    temporary.replace(path)


def atomic_csv(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", newline="", delete=False, dir=path.parent, suffix=".tmp"
    ) as handle:
        temporary = Path(handle.name)
        frame.to_csv(handle, index=False)
    temporary.replace(path)


def evaluate_workflow(
    processed: pd.DataFrame,
    ranking: pd.DataFrame,
    model_hashes_unchanged: bool,
    deterministic_replay: bool | None = None,
) -> dict[str, Any]:
    count = len(processed)
    valid = int(processed["structure_status"].eq("valid").sum())
    full_model = int(processed["model_v3_status"].eq("available").sum())
    any_model = int(processed["model_score"].notna().sum())
    duplicate_count = int(processed["duplicate_structure_of"].fillna("").ne("").sum())
    eligible_count = count - duplicate_count
    complete = int(ranking["final_score"].notna().sum())
    ranked = ranking.loc[ranking["rank"].notna(), "rank"]
    rank_integrity = bool(
        len(ranked) == complete
        and ranked.astype(int).nunique() == complete
        and set(ranked.astype(int)) == set(range(1, complete + 1))
    )
    experiment_unknown_integrity = bool(
        processed[
            [
                "experimental_ATP_inhibition",
                "experimental_MIC",
                "experimental_toxicity",
            ]
        ]
        .fillna("unknown")
        .eq("unknown")
        .all()
        .all()
    )
    score_semantics_integrity = bool(
        ranking["score_scope"]
        .eq("batch_relative_computational_decision_not_probability")
        .all()
    )
    source_traceability = bool(
        processed["source"].fillna("").str.strip().ne("").all()
        and ranking["input_processor_version"].fillna("").str.strip().ne("").all()
    )
    decision_coverage = complete / eligible_count if eligible_count else 0.0
    checks = [
        {
            "check": "valid_structure_coverage",
            "value": valid / count,
            "pass": valid == count,
            "interpretation": "All submitted structures parse and standardize with RDKit.",
        },
        {
            "check": "any_preserved_model_coverage",
            "value": any_model / count,
            "pass": any_model == valid,
            "interpretation": "Every valid structure receives either frozen Model v3 or transparent Model v2-A fallback output.",
        },
        {
            "check": "full_model_v3_coverage",
            "value": full_model / count,
            "pass": full_model == valid,
            "interpretation": "Informational coverage gate; failure triggers documented fallback rather than imputation.",
        },
        {
            "check": "complete_decision_coverage",
            "value": decision_coverage,
            "pass": complete == eligible_count,
            "interpretation": "Every unique eligible structure has all four decision components.",
        },
        {
            "check": "rank_integrity",
            "value": float(rank_integrity),
            "pass": rank_integrity,
            "interpretation": "Ranks are complete and unique among scored candidates.",
        },
        {
            "check": "experimental_unknown_integrity",
            "value": float(experiment_unknown_integrity),
            "pass": experiment_unknown_integrity,
            "interpretation": "No experimental ATP, MIC, or toxicity value was created by the workflow.",
        },
        {
            "check": "score_semantics_integrity",
            "value": float(score_semantics_integrity),
            "pass": score_semantics_integrity,
            "interpretation": "Outputs explicitly remain batch-relative computational decision scores.",
        },
        {
            "check": "source_traceability",
            "value": float(source_traceability),
            "pass": source_traceability,
            "interpretation": "Every candidate and workflow output retains source/version provenance.",
        },
        {
            "check": "historical_model_hash_integrity",
            "value": float(model_hashes_unchanged),
            "pass": bool(model_hashes_unchanged),
            "interpretation": "The workflow did not modify preserved model files.",
        },
    ]
    if deterministic_replay is not None:
        checks.append(
            {
                "check": "deterministic_replay",
                "value": float(deterministic_replay),
                "pass": bool(deterministic_replay),
                "interpretation": "Repeated run with the same input/profile produces the same ranking content.",
            }
        )
    critical_names = {
        "valid_structure_coverage",
        "any_preserved_model_coverage",
        "complete_decision_coverage",
        "rank_integrity",
        "experimental_unknown_integrity",
        "score_semantics_integrity",
        "source_traceability",
        "historical_model_hash_integrity",
        "deterministic_replay",
    }
    critical = [row for row in checks if row["check"] in critical_names]
    return {
        "evaluator_version": EVALUATOR_VERSION,
        "candidate_count": count,
        "unique_ranking_eligible_count": eligible_count,
        "complete_decision_count": complete,
        "duplicate_structure_count": duplicate_count,
        "workflow_readiness": "pass" if all(row["pass"] for row in critical) else "conditional",
        "biological_performance_evaluated": False,
        "performance_reason": (
            "No internal experimental ATP inhibition, MIC, or toxicity labels are available. "
            "This audit evaluates workflow integrity and evidence coverage, not predictive accuracy."
        ),
        "checks": checks,
    }


def write_evaluation(payload: dict[str, Any], output_dir: str | Path) -> None:
    output_dir = Path(output_dir)
    atomic_json(payload, output_dir / "workflow_validation.json")
    atomic_csv(pd.DataFrame(payload["checks"]), output_dir / "workflow_validation.csv")

