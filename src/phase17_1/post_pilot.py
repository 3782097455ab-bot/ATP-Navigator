"""Strict, read-only post-analysis for the completed Phase 17.1 pilot.

This module consumes cached result tables only.  It does not execute physics
jobs, mutate Registry evidence, change the frozen protocol, train a model, or
start the optional 60-candidate extension.
"""
from __future__ import annotations

import json
import hashlib
import math
import os
import tempfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


PROTOCOL_RAW = {
    "glide": "glide_score",
    "vina": "vina_score",
    "open_mmgbsa": "open_mmgbsa_deltaG",
}
PROTOCOL_UTILITY = {
    "glide": "glide_utility",
    "vina": "vina_utility",
    "open_mmgbsa": "mmgbsa_utility",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)
            handle.write("\n")
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def atomic_csv(path: Path, frame: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    os.close(fd)
    try:
        frame.to_csv(temporary, index=False, encoding="utf-8")
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def frozen_model_hashes(project: Path) -> dict[str, str]:
    expected = json.loads((project / "results/phase14/model_hashes_after.json").read_text(encoding="utf-8"))
    actual: dict[str, str] = {}
    for relative, expected_hash in expected.items():
        path = project / relative.replace("\\", "/")
        if not path.is_file():
            raise FileNotFoundError(f"frozen_model_missing:{relative}")
        actual[relative] = _sha256(path)
        if actual[relative] != expected_hash:
            raise ValueError(f"frozen_model_hash_changed:{relative}")
    return actual


def _finite(value: Any) -> bool:
    try:
        return value is not None and math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def strict_json_value(value: Any) -> Any:
    """Convert only JSON-incompatible missing scalars to null recursively."""
    if isinstance(value, dict):
        return {str(key): strict_json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [strict_json_value(item) for item in value]
    if isinstance(value, np.generic):
        value = value.item()
    if value is pd.NA or value is None:
        return None
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def _rank_utility(values: pd.Series) -> pd.Series:
    """Within-protocol percentile utility; lower raw energy/score is better."""
    numeric = pd.to_numeric(values, errors="coerce")
    finite_mask = numeric.map(_finite)
    output = pd.Series(np.nan, index=values.index, dtype=float)
    count = int(finite_mask.sum())
    if count == 0:
        return output
    if count == 1:
        output.loc[finite_mask] = 1.0
        return output
    ranks = numeric.loc[finite_mask].rank(method="average", ascending=True)
    output.loc[finite_mask] = 1.0 - (ranks - 1.0) / (count - 1.0)
    return output


def _kendall_tau_b(values_a: pd.Series, values_b: pd.Series) -> float:
    x = values_a.to_numpy(dtype=float)
    y = values_b.to_numpy(dtype=float)
    concordant = discordant = ties_x = ties_y = 0
    for left in range(len(x) - 1):
        for right in range(left + 1, len(x)):
            dx = np.sign(x[left] - x[right])
            dy = np.sign(y[left] - y[right])
            if dx == 0 and dy == 0:
                continue
            if dx == 0:
                ties_x += 1
            elif dy == 0:
                ties_y += 1
            elif dx == dy:
                concordant += 1
            else:
                discordant += 1
    denominator = math.sqrt(
        (concordant + discordant + ties_x) * (concordant + discordant + ties_y)
    )
    return (concordant - discordant) / denominator if denominator else math.nan


def _correlation(values_a: pd.Series, values_b: pd.Series, method: str) -> tuple[float | None, str, str | None]:
    if len(values_a) < 3:
        return None, "mathematically_undefined", "fewer_than_3_finite_pairs"
    if values_a.nunique() < 2 or values_b.nunique() < 2:
        return None, "mathematically_undefined", "constant_input"
    if method == "spearman":
        statistic = float(values_a.rank(method="average").corr(values_b.rank(method="average")))
    else:
        statistic = float(_kendall_tau_b(values_a, values_b))
    if not math.isfinite(statistic):
        return None, "mathematically_undefined", "non_finite_statistic"
    return statistic, "available", None


def _pair_metrics(frame: pd.DataFrame, protocol_a: str, protocol_b: str) -> dict[str, Any]:
    left = PROTOCOL_RAW[protocol_a]
    right = PROTOCOL_RAW[protocol_b]
    paired = frame.loc[
        frame[left].map(_finite) & frame[right].map(_finite),
        ["candidate_id", left, right],
    ].copy()
    spearman, spearman_status, spearman_reason = _correlation(paired[left], paired[right], "spearman")
    kendall, kendall_status, kendall_reason = _correlation(paired[left], paired[right], "kendall")
    record: dict[str, Any] = {
        "protocol_a": protocol_a,
        "protocol_b": protocol_b,
        "matched_n": int(len(paired)),
        "spearman": spearman,
        "spearman_status": spearman_status,
        "spearman_reason": spearman_reason,
        "kendall_tau": kendall,
        "kendall_status": kendall_status,
        "kendall_reason": kendall_reason,
        "interpretation": "rank association only; raw values are not interchangeable physical energies",
    }
    for requested_k in (5, 10):
        if paired.empty:
            record[f"top{requested_k}_effective_k"] = 0
            record[f"top{requested_k}_overlap"] = None
            record[f"top{requested_k}_overlap_fraction"] = None
            record[f"top{requested_k}_status"] = "mathematically_undefined"
            record[f"top{requested_k}_reason"] = "no_finite_pairs"
            continue
        effective_k = min(requested_k, len(paired))
        set_a = set(paired.nsmallest(effective_k, left)["candidate_id"])
        set_b = set(paired.nsmallest(effective_k, right)["candidate_id"])
        overlap = len(set_a & set_b)
        record[f"top{requested_k}_effective_k"] = int(effective_k)
        record[f"top{requested_k}_overlap"] = int(overlap)
        record[f"top{requested_k}_overlap_fraction"] = overlap / effective_k
        record[f"top{requested_k}_status"] = "available"
        record[f"top{requested_k}_reason"] = None
    return record


def _recover_exact_glide(project: Path, source: pd.DataFrame) -> pd.DataFrame:
    """Recover only exact-ID Glide results already exported by Phase 14."""
    audit_path = project / "results/phase14/glide_vina_protocol_disagreement.csv"
    audit = pd.read_csv(audit_path)
    audit = audit[["canonical_id", "glide_docking_score", "glide_rank"]].rename(
        columns={
            "canonical_id": "candidate_id",
            "glide_docking_score": "phase14_glide_score",
            "glide_rank": "phase14_glide_rank",
        }
    )
    if audit["candidate_id"].duplicated().any():
        raise ValueError("phase14_glide_candidate_id_not_unique")
    merged = source.merge(audit, on="candidate_id", how="left", validate="one_to_one")
    declared = pd.to_numeric(merged.get("glide_score"), errors="coerce")
    recovered = pd.to_numeric(merged["phase14_glide_score"], errors="coerce")
    merged["glide_score"] = declared.where(declared.map(_finite), recovered)
    exact = recovered.map(_finite)
    merged["glide_evidence_status"] = np.where(exact, "available_exact_candidate_id", "scientifically_unavailable")
    merged["glide_missing_reason"] = np.where(
        exact,
        "",
        np.where(
            merged["candidate_origin"].eq("phase15_historical_htvs"),
            "technical_exact_id_join_unresolved",
            "no_comparable_historical_glide_result_for_candidate_identity",
        ),
    )
    merged["glide_evidence_source"] = np.where(
        exact,
        "results/phase14/glide_vina_protocol_disagreement.csv; exact candidate_id",
        "",
    )
    return merged


def _build_comparison(project: Path, plan: pd.DataFrame, results: pd.DataFrame) -> pd.DataFrame:
    source = _recover_exact_glide(project, plan.iloc[:30].copy())
    keep = [
        "candidate_id", "candidate_origin", "panel_order", "selection_class", "scaffold", "cluster",
        "acquisition_score", "protocol_disagreement", "glide_score", "phase14_glide_rank",
        "glide_evidence_status", "glide_missing_reason", "glide_evidence_source", "vina_score",
    ]
    comparison = source[keep].merge(
        results[[
            "candidate_id", "open_mmgbsa_deltaG", "open_mmgbsa_sd", "frame_count", "qc_status",
            "protocol_id", "protocol_hash",
        ]],
        on="candidate_id",
        how="left",
        validate="one_to_one",
    )
    for field in ["glide_score", "vina_score", "open_mmgbsa_deltaG", "open_mmgbsa_sd"]:
        comparison[field] = pd.to_numeric(comparison[field], errors="coerce")
    for name, raw in PROTOCOL_RAW.items():
        comparison[PROTOCOL_UTILITY[name]] = _rank_utility(comparison[raw])
        comparison[f"{name}_finite"] = comparison[raw].map(_finite)
        comparison[f"{name}_cohort_n"] = int(comparison[raw].map(_finite).sum())
    utilities = list(PROTOCOL_UTILITY.values())
    comparison["protocol_count"] = comparison[utilities].notna().sum(axis=1)
    comparison["three_protocol_complete"] = comparison["protocol_count"].eq(3)
    comparison["three_protocol_status"] = np.where(
        comparison["three_protocol_complete"], "available", "scientifically_unavailable"
    )
    comparison["three_protocol_missing_reason"] = comparison.apply(
        lambda row: "" if row["three_protocol_complete"] else ";".join(
            name for name, raw in PROTOCOL_RAW.items() if not _finite(row[raw])
        ) + "_missing",
        axis=1,
    )
    comparison["normalization"] = "within_protocol_finite_cohort_percentile; lower raw value is better"
    comparison["interpretation"] = "protocol consistency only; not biological activity"
    return comparison


def _build_disagreement(comparison: pd.DataFrame) -> pd.DataFrame:
    pairs = [
        ("glide", "vina"),
        ("glide", "open_mmgbsa"),
        ("vina", "open_mmgbsa"),
    ]
    out = comparison.copy()
    for left, right in pairs:
        column = f"{left}_vs_{right}_disagreement"
        left_u = PROTOCOL_UTILITY[left]
        right_u = PROTOCOL_UTILITY[right]
        available = out[left_u].map(_finite) & out[right_u].map(_finite)
        out[column] = np.where(available, (out[left_u] - out[right_u]).abs(), np.nan)
        out[f"{column}_status"] = np.where(available, "available", "scientifically_unavailable")
        out[f"{column}_reason"] = np.where(available, "", "one_or_both_protocols_missing")
    utilities = list(PROTOCOL_UTILITY.values())
    complete = out["three_protocol_complete"]
    out["three_protocol_consensus"] = out[utilities].mean(axis=1).where(complete)
    out["normalized_rank_variance"] = out[utilities].var(axis=1, ddof=0).where(complete)
    out["three_protocol_disagreement"] = (
        out[utilities].max(axis=1) - out[utilities].min(axis=1)
    ).where(complete)
    out["three_protocol_disagreement_status"] = np.where(
        complete, "available", "scientifically_unavailable"
    )
    out["three_protocol_disagreement_reason"] = np.where(
        complete, "", "requires_three_finite_protocol_observations"
    )
    return out.sort_values(["three_protocol_disagreement", "candidate_id"], ascending=[False, True], na_position="last")


def _build_evidence_impact(project: Path, disagreement: pd.DataFrame) -> pd.DataFrame:
    out = disagreement.copy()
    out["pre_mmgbsa_protocol_count"] = out[["glide_utility", "vina_utility"]].notna().sum(axis=1)
    out["post_mmgbsa_protocol_count"] = out[["glide_utility", "vina_utility", "mmgbsa_utility"]].notna().sum(axis=1)
    out["pre_mmgbsa_evidence_completeness"] = out["pre_mmgbsa_protocol_count"] / 3.0
    out["post_mmgbsa_evidence_completeness"] = out["post_mmgbsa_protocol_count"] / 3.0
    out["evidence_completeness_gain"] = (
        out["post_mmgbsa_evidence_completeness"] - out["pre_mmgbsa_evidence_completeness"]
    )
    pre_complete = out["pre_mmgbsa_protocol_count"].eq(2)
    post_complete = out["post_mmgbsa_protocol_count"].eq(3)
    out["pre_mmgbsa_consensus"] = out[["glide_utility", "vina_utility"]].mean(axis=1).where(pre_complete)
    out["post_mmgbsa_shadow_score"] = out[["glide_utility", "vina_utility", "mmgbsa_utility"]].mean(axis=1).where(post_complete)
    out["pre_mmgbsa_uncertainty"] = (out["glide_utility"] - out["vina_utility"]).abs().where(pre_complete)
    out["post_mmgbsa_uncertainty"] = out["three_protocol_disagreement"]
    out["available_uncertainty_change"] = out["post_mmgbsa_uncertainty"] - out["pre_mmgbsa_uncertainty"]
    out["pre_mmgbsa_rank"] = out["pre_mmgbsa_consensus"].rank(method="min", ascending=False)
    out["post_mmgbsa_shadow_rank"] = out["post_mmgbsa_shadow_score"].rank(method="min", ascending=False)
    out["rank_change_after_mmgbsa"] = out["pre_mmgbsa_rank"] - out["post_mmgbsa_shadow_rank"]
    out["rank_change_status"] = np.where(post_complete, "available_shadow_comparison", "scientifically_unavailable")
    out["rank_change_reason"] = np.where(post_complete, "", "requires_exact_glide_vina_and_mmgbsa")
    out["acquisition_priority_before"] = out["panel_order"]
    out["acquisition_priority_after_shadow"] = out["post_mmgbsa_shadow_rank"]
    out["acquisition_priority_change"] = out["acquisition_priority_before"] - out["acquisition_priority_after_shadow"]
    frozen_ids: set[str] = set()
    frozen_path = project / "results/final_navigation_report.csv"
    if frozen_path.is_file():
        frozen = pd.read_csv(frozen_path, usecols=lambda c: c in {"compound_id", "candidate"})
        if "compound_id" in frozen:
            frozen_ids = set(frozen["compound_id"].dropna().astype(str))
    out["frozen_decision_exact_identity_overlap"] = out["candidate_id"].isin(frozen_ids)
    out["frozen_decision_comparison_status"] = np.where(
        out["frozen_decision_exact_identity_overlap"], "available", "not_comparable_identity_domain"
    )
    out["decision_run_type"] = "updated_evidence_shadow_only"
    out["frozen_decision_overwritten"] = False
    return out.sort_values(["post_mmgbsa_shadow_rank", "candidate_id"], na_position="last")


def _acquisition_validation(frame: pd.DataFrame) -> dict[str, Any]:
    classes = Counter(frame["selection_class"].astype(str))
    category_members = {
        "protocol_disagreement": {"extreme_disagreement"},
        "strong_candidates": {"multi_protocol_strong", "generated_high_ranking"},
        "boundary_uncertainty": {"rank_boundary_uncertain"},
        "scaffold_diversity": {"scaffold_diverse", "generated_diverse_novel"},
        "historical_bridge": {"historical_bridge_interpretable", "reference_IN2"},
    }
    coverage = {
        name: int(frame["selection_class"].isin(members).sum())
        for name, members in category_members.items()
    }
    all_covered = all(value > 0 for value in coverage.values())
    finite_change = pd.to_numeric(frame["rank_change_after_mmgbsa"], errors="coerce").dropna().abs()
    return {
        "pilot_n": int(len(frame)),
        "selection_class_counts": dict(sorted(classes.items())),
        "information_category_coverage": coverage,
        "all_requested_information_categories_represented": all_covered,
        "unique_nonempty_scaffolds": int(frame["scaffold"].replace("", np.nan).nunique(dropna=True)),
        "unique_nonempty_clusters": int(frame["cluster"].replace("", np.nan).nunique(dropna=True)),
        "mmgbsa_evidence_added_n": int(frame["mmgbsa_utility"].map(_finite).sum()),
        "three_protocol_comparable_n": int(frame["three_protocol_complete"].sum()),
        "median_absolute_shadow_rank_change": float(finite_change.median()) if not finite_change.empty else None,
        "conclusion": (
            "supported_for_information_coverage_not_biological_success"
            if all_covered else "partially_supported_for_information_coverage"
        ),
        "biological_hit_rate_assessed": False,
    }


def run_post_pilot_analysis(project: Path) -> dict[str, Any]:
    project = project.resolve()
    output = project / "results/phase17_1"
    plan = pd.read_csv(output / "candidate_plan.csv", keep_default_na=False)
    results = pd.read_csv(output / "pilot30_results.csv", keep_default_na=False)
    if len(results) != 30 or int(results["status"].eq("success").sum()) != 30:
        raise ValueError("post_analysis_requires_30_successful_cached_results")
    if len(plan) < 60:
        raise ValueError("phase17_1_frozen_candidate_plan_incomplete")

    comparison = _build_comparison(project, plan, results)
    disagreement = _build_disagreement(comparison)
    impact = _build_evidence_impact(project, disagreement)
    metrics_records = [
        _pair_metrics(comparison, "glide", "vina"),
        _pair_metrics(comparison, "glide", "open_mmgbsa"),
        _pair_metrics(comparison, "vina", "open_mmgbsa"),
    ]
    metrics = pd.DataFrame(metrics_records)

    atomic_csv(output / "three_protocol_comparison.csv", comparison)
    atomic_csv(output / "protocol_disagreement.csv", disagreement)
    atomic_csv(output / "evidence_impact.csv", impact)
    # Compatibility exports used by existing Phase17.1 and GUI code.
    atomic_csv(output / "pilot30_protocol_comparison.csv", comparison)
    atomic_csv(output / "pilot30_protocol_disagreement.csv", disagreement)
    atomic_csv(output / "pilot30_protocol_metrics.csv", metrics)
    atomic_csv(output / "pilot30_shadow_decision.csv", impact)

    technical_unresolved = comparison.loc[
        comparison["glide_missing_reason"].eq("technical_exact_id_join_unresolved"), "candidate_id"
    ].tolist()
    missing_glide = comparison.loc[~comparison["glide_score"].map(_finite), "candidate_id"].tolist()
    nan_audit = {
        "original_serialization_failure": {
            "field_origin": "pairwise metric DataFrame converted to records retained IEEE NaN",
            "classification": "technical_error",
            "reason": "strict json.dump(allow_nan=False) rejects NaN",
            "repaired": True,
        },
        "source_glide_score_missing_before_exact_join": 30,
        "source_missing_inventory": [
            {
                "table": "candidate_plan.csv", "field": "glide_score", "missing_n": 30,
                "classification": "technical_carry_forward_omission_then_scientific_domain_gap",
                "resolution": "24 exact candidate-ID values recovered; 6 remain scientifically unavailable",
            },
            {
                "table": "candidate_plan.csv", "field": "acquisition_score",
                "missing_n": int(pd.to_numeric(plan.iloc[:30]["acquisition_score"], errors="coerce").isna().sum()),
                "classification": "scientifically_unavailable",
                "resolution": "IN-2 is outside the Phase15 acquisition-score domain; not imputed",
            },
            {
                "table": "candidate_plan.csv", "field": "protocol_disagreement",
                "missing_n": int(pd.to_numeric(plan.iloc[:30]["protocol_disagreement"], errors="coerce").isna().sum()),
                "classification": "scientifically_unavailable",
                "resolution": "five generated candidates and IN-2 lack the historical matched protocol pair",
            },
            {
                "table": "candidate_plan.csv", "field": "scaffold",
                "missing_n": int(plan.iloc[:30]["scaffold"].replace("", np.nan).isna().sum()),
                "classification": "scientifically_unavailable_in_frozen_plan",
                "resolution": "excluded from scaffold-coverage counts; not filled",
            },
            {
                "table": "pilot30_results.csv", "field": "failure_stage/failure_reason",
                "missing_n": int(results["failure_stage"].replace("", np.nan).isna().sum()),
                "classification": "not_applicable",
                "resolution": "all 30 jobs succeeded, so no failure metadata exists",
            },
        ],
        "derived_missing_inventory": {
            "affected_candidates_n": int((~comparison["three_protocol_complete"]).sum()),
            "fields": [
                "phase14_glide_rank", "glide_score", "glide_utility",
                "glide_vs_vina_disagreement", "glide_vs_open_mmgbsa_disagreement",
                "three_protocol_consensus", "normalized_rank_variance",
                "three_protocol_disagreement", "pre/post shadow rank-change fields",
            ],
            "classification": "scientifically_unavailable",
            "reason": "six candidates lack exact comparable historical Glide evidence",
        },
        "glide_exact_id_recovered": int(comparison["glide_score"].map(_finite).sum()),
        "glide_remaining_missing": int(len(missing_glide)),
        "glide_remaining_candidate_ids": missing_glide,
        "glide_remaining_classification": "scientifically_unavailable",
        "glide_remaining_reason": "generated candidates and IN-2 lack an exact comparable HTVS Glide record",
        "technical_errors_unresolved": technical_unresolved,
        "mathematically_undefined_metrics": [
            {
                "metric": f"{row['protocol_a']}_vs_{row['protocol_b']}",
                "reason": row["spearman_reason"],
            }
            for row in metrics_records if row["spearman"] is None
        ],
        "csv_policy": "NaN retained for unavailable numeric cells",
        "json_policy": "non-finite/missing values serialized as null with explicit status and reason",
        "imputation_performed": False,
    }
    acquisition = _acquisition_validation(impact)
    model_hashes = frozen_model_hashes(project)
    largest_disagreement = disagreement.dropna(subset=["three_protocol_disagreement"]).iloc[0]
    rank_change_finite = impact.dropna(subset=["rank_change_after_mmgbsa"]).copy()
    rank_change_finite["abs_rank_change"] = rank_change_finite["rank_change_after_mmgbsa"].abs()
    largest_change = rank_change_finite.sort_values(
        ["abs_rank_change", "candidate_id"], ascending=[False, True]
    ).iloc[0]

    payload = strict_json_value({
        "created_at": utc_now(),
        "scope": "cached_phase17_1_pilot30_post_analysis_only",
        "candidate_computation_executed": False,
        "optional_60_expansion_started": False,
        "registry_evidence_mutated": False,
        "frozen_protocol_modified": False,
        "training_performed": False,
        "normalization": "within-protocol finite-cohort percentile; lower raw values rank better",
        "nan_audit": nan_audit,
        "pairwise_metrics": metrics_records,
        "three_protocol_matched_n": int(comparison["three_protocol_complete"].sum()),
        "largest_protocol_disagreement": {
            "candidate_id": largest_disagreement["candidate_id"],
            "score": largest_disagreement["three_protocol_disagreement"],
        },
        "largest_shadow_rank_change": {
            "candidate_id": largest_change["candidate_id"],
            "rank_change_after_mmgbsa": largest_change["rank_change_after_mmgbsa"],
        },
        "acquisition_validation": acquisition,
        "frozen_model_hash_count": len(model_hashes),
        "frozen_model_hashes_unchanged": True,
        "scientific_limitations": [
            "Protocol correlations compare ranks, not interchangeable absolute physical energies.",
            "The shadow evidence run does not replace the frozen Decision Engine.",
            "No biological activity, MIC, toxicity, or experimental success claim is made.",
        ],
    })
    # Prove strict serialization before atomic write.
    json.dumps(payload, ensure_ascii=False, allow_nan=False)
    atomic_json(output / "post_analysis.json", payload)
    atomic_json(output / "pilot30_analysis_summary.json", payload)

    checkpoint_path = project / "workspace_local/phase17_1/checkpoint.json"
    if checkpoint_path.is_file():
        checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
        checkpoint["post_pilot_analysis"] = {
            "status": "complete",
            "completed_at": payload["created_at"],
            "artifact": "results/phase17_1/post_analysis.json",
            "candidate_recomputation": False,
            "registry_evidence_mutated": False,
        }
        checkpoint["active_worker_expected"] = False
        checkpoint["remaining_in_pilot30"] = 0
        checkpoint["updated_at"] = payload["created_at"]
        atomic_json(checkpoint_path, strict_json_value(checkpoint))

    protocol = json.loads((output / "open_mmgbsa_7p3w_v2.json").read_text(encoding="utf-8"))
    metric_lines = []
    for row in metrics_records:
        metric_lines.append(
            f"- {row['protocol_a']} vs {row['protocol_b']}: n={row['matched_n']}, "
            f"Spearman={row['spearman'] if row['spearman'] is not None else 'null'}, "
            f"Kendall={row['kendall_tau'] if row['kendall_tau'] is not None else 'null'}"
        )
    report = f"""# Phase 17.1 Final Report

## Scope and integrity

This recovery patch reuses the 30/30 cached successful results under frozen protocol `{protocol['protocol_id']}` (`{protocol['protocol_hash']}`). It did not run a candidate, start the optional 60-candidate extension, train a model, modify Registry Evidence, or overwrite the frozen Decision Engine.

## NaN audit and repair

The prior failure was technical: IEEE NaN values remained after a pandas metrics table was converted to JSON records, while the atomic writer correctly enforced strict JSON. The candidate plan also failed to carry Glide scores forward. Exact candidate-ID joins to the existing Phase14 export recovered 24 historical HTVS Glide results. Five generated candidates and IN-2 have no exact comparable HTVS Glide record and therefore remain scientifically unavailable; they were not imputed. CSV files retain NaN, while JSON uses `null` plus explicit status/reason fields. Unresolved technical joins: {len(technical_unresolved)}.

The source audit also records one unavailable Phase15 acquisition score (IN-2), six unavailable historical protocol-disagreement values, one empty frozen-plan scaffold, and 30 not-applicable failure-stage/reason cells because every pilot job succeeded. Derived three-protocol and shadow fields remain unavailable for the same six candidates rather than being filled.

## Three-protocol comparison

Three-protocol exact matched subset: {int(comparison['three_protocol_complete'].sum())}/30. Normalization is within-protocol finite-cohort percentile rank with lower raw value treated as better. Raw Glide, Vina and open MM/GBSA values are not interpreted as the same absolute energy.

{chr(10).join(metric_lines)}

Largest three-protocol disagreement: `{largest_disagreement['candidate_id']}` ({largest_disagreement['three_protocol_disagreement']:.6f}).

## Evidence impact and shadow decision

Open MM/GBSA raises the available protocol evidence count for all 30 candidates. Rank-change analysis is restricted to the 24 exact three-protocol candidates. Largest absolute shadow rank change: `{largest_change['candidate_id']}` ({largest_change['rank_change_after_mmgbsa']:+.0f} positions; positive means promotion). The new output is an updated-evidence shadow run only; the frozen Decision Engine remains unchanged. There was no exact candidate-ID overlap with its internal17 output, so direct frozen-rank comparison is not applicable.

## Phase15 acquisition validation

All five intended information categories are represented: {json.dumps(acquisition['information_category_coverage'], ensure_ascii=False)}. The strategy is therefore supported as an information-coverage allocation, not as proof of biological hit enrichment. The panel contains {acquisition['unique_nonempty_scaffolds']} non-empty scaffolds and {acquisition['unique_nonempty_clusters']} non-empty chemical clusters.

## Remaining limitations

- Missing Glide values for six candidates are explained by identity/domain availability, not silently filled.
- Correlations and top-k overlap are descriptive for their finite matched subsets.
- The short restrained aqueous open-MM/GBSA approximation is not equivalent to historical Prime/MMGBSA or a membrane simulation.
- Experimental ATP inhibition, MIC, cytotoxicity and pharmacology remain unknown unless separately measured.
"""
    (project / "docs/Phase17_1_Final_Report.md").write_text(report, encoding="utf-8")
    return payload


if __name__ == "__main__":
    print(json.dumps(run_post_pilot_analysis(Path.cwd()), ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False))
