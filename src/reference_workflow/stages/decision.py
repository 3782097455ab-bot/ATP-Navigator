from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from input_processor import CandidateInputProcessor
from workspace.state import State, digest, encode, now

from ..util import atomic_csv, atomic_json, sha256_file


def _utility(series: pd.Series, lower_is_better: bool = True) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce")
    n = int(values.notna().sum())
    if n == 0:
        return pd.Series(np.nan, index=series.index)
    if n == 1:
        return pd.Series(np.where(values.notna(), 0.5, np.nan), index=series.index)
    ranks = values.rank(method="average", ascending=lower_is_better)
    return (n - ranks) / (n - 1)


def _mean_available(frame: pd.DataFrame, columns: list[str]) -> pd.Series:
    return frame[columns].apply(pd.to_numeric, errors="coerce").mean(axis=1, skipna=True)


def run_decision(
    project: Path,
    acquisition_path: Path,
    mmgbsa_path: Path,
    output_dir: Path,
    decision_config: dict[str, Any],
    run_id: str,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    acquisition = pd.read_csv(acquisition_path, keep_default_na=False)
    mmgbsa = pd.read_csv(mmgbsa_path, keep_default_na=False)
    # The library/docking route uses compound_id, while the durable Evidence
    # Registry contract uses candidate_id.  Normalize only the identifier
    # label; never infer or alter chemical identity.
    if "candidate_id" not in acquisition and "compound_id" in acquisition:
        acquisition = acquisition.rename(columns={"compound_id": "candidate_id"})
    if "candidate_id" not in mmgbsa and "compound_id" in mmgbsa:
        mmgbsa = mmgbsa.rename(columns={"compound_id": "candidate_id"})
    if "candidate_id" not in acquisition or "candidate_id" not in mmgbsa:
        raise ValueError("candidate_identity_column_missing")
    merged = acquisition.merge(mmgbsa, on=["candidate_id", "canonical_smiles"], how="left", suffixes=("", "_mmgbsa"))
    eligible = merged.loc[
        merged["status_mmgbsa"].eq("success")
        & pd.to_numeric(merged["vina_affinity"], errors="coerce").notna()
        & pd.to_numeric(merged["open_mmgbsa_deltaG"], errors="coerce").notna()
    ].copy()
    input_frame = eligible[["candidate_id", "canonical_smiles", "vina_affinity", "open_mmgbsa_deltaG"]].rename(
        columns={"candidate_id": "compound_id", "canonical_smiles": "SMILES", "vina_affinity": "docking_score", "open_mmgbsa_deltaG": "mmgbsa_score"}
    )
    input_frame["source"] = "reconstructed_IN2_reference_workflow"
    input_path = output_dir / "decision_input.csv"
    atomic_csv(input_path, input_frame)
    if eligible.empty:
        empty = pd.DataFrame(
            columns=["candidate_id", "priority_rank", "final_score", "decision_status", "recommended_next_experiment"]
        )
        atomic_csv(output_dir / "candidate_panel.csv", empty)
        atomic_csv(output_dir / "candidate_panel_top5.csv", empty)
        atomic_csv(output_dir / "candidate_panel_top10.csv", empty)
        atomic_csv(output_dir / "candidate_panel_top_configured.csv", empty)
        atomic_json(output_dir / "candidate_panel.json", [])
        (output_dir / "candidate_panel.md").write_text(
            "# Computational pre-experimental prioritization\n\nNo candidate passed the declared Vina + Open MM/GBSA evidence gate.\n",
            encoding="utf-8",
        )
        summary = {"status": "insufficient_evidence", "input_count": len(acquisition), "evidence_gate_passed": 0, "output_count": 0, "decision_run_id": None}
        atomic_json(output_dir / "decision_summary.json", summary)
        return summary

    processor = CandidateInputProcessor(project)
    processed = processor.process(input_path, output_dir / "processed_candidates.csv")
    processed = processed.rename(columns={"compound_id": "candidate_id"})
    eligible = eligible.merge(processed, on="candidate_id", how="left", suffixes=("", "_processed"))
    eligible["vina_utility"] = _utility(eligible["vina_affinity"], True)
    eligible["mmgbsa_utility"] = _utility(eligible["open_mmgbsa_deltaG"], True)
    eligible["binding_score"] = 100 * (0.45 * eligible["vina_utility"] + 0.55 * eligible["mmgbsa_utility"])
    eligible["structure_model_utility"] = _utility(eligible["model_score"], True)
    atp_columns = [
        column
        for column in ["prior_task_b_pa_atp_ic50_log10_ug_ml", "prior_task_b_mtb_atp_ic50_log10_nm"]
        if column in eligible
    ]
    atp_raw = _mean_available(eligible, atp_columns) if atp_columns else pd.Series(np.nan, index=eligible.index)
    eligible["atp_prior_score"] = 100 * _utility(atp_raw, True)
    ab_column = "prior_task_a_ab_mic_log10_ug_ml"
    eligible["antibacterial_prior_score"] = 100 * _utility(eligible[ab_column], True) if ab_column in eligible else np.nan
    property_passes = (
        pd.to_numeric(eligible["molecular_weight"], errors="coerce").between(250, 500).astype(float)
        + pd.to_numeric(eligible["clogp"], errors="coerce").between(-1, 5).astype(float)
        + pd.to_numeric(eligible["tpsa"], errors="coerce").le(140).astype(float)
        + pd.to_numeric(eligible["hbd"], errors="coerce").le(5).astype(float)
        + pd.to_numeric(eligible["hba"], errors="coerce").le(10).astype(float)
        + pd.to_numeric(eligible["rotatable_bonds"], errors="coerce").le(10).astype(float)
    )
    eligible["druglikeness_score"] = 100 * property_passes / 6.0
    eligible["admet_evidence"] = "unknown"
    eligible["admet_status"] = "additional_evidence_required"
    weights = decision_config["weights"]
    eligible["final_score"] = (
        weights["binding"] * eligible["binding_score"]
        + weights["structure_model"] * 100 * eligible["structure_model_utility"]
        + weights["atp_prior"] * eligible["atp_prior_score"]
        + weights["antibacterial_prior"] * eligible["antibacterial_prior_score"]
        + weights["druglikeness"] * eligible["druglikeness_score"]
    )
    eligible["priority_rank"] = eligible["final_score"].rank(method="min", ascending=False).astype("Int64")
    eligible["protocol_disagreement"] = (eligible["vina_utility"] - eligible["mmgbsa_utility"]).abs()
    sd = pd.to_numeric(eligible["open_mmgbsa_sd"], errors="coerce")
    eligible["uncertainty"] = (0.6 * eligible["protocol_disagreement"] + 0.4 * (sd / 10.0).clip(0, 1)).clip(0, 1)
    eligible["evidence_completeness"] = 2 / 3
    eligible["evidence_missing"] = "ADMET"
    eligible["decision_status"] = "computational_pre_experimental_prioritization"
    eligible["rank_p05"] = eligible["priority_rank"]
    eligible["rank_p95"] = eligible["priority_rank"]
    if len(eligible) > 1:
        alternative_ranks = []
        for binding_weight in (0.35, 0.45, 0.55):
            remainder = 1.0 - binding_weight
            score = (
                binding_weight * eligible["binding_score"]
                + remainder * (
                    0.36 * 100 * eligible["structure_model_utility"]
                    + 0.27 * eligible["atp_prior_score"]
                    + 0.18 * eligible["antibacterial_prior_score"]
                    + 0.19 * eligible["druglikeness_score"]
                )
            )
            alternative_ranks.append(score.rank(method="min", ascending=False))
        rank_frame = pd.concat(alternative_ranks, axis=1)
        eligible["rank_p05"] = rank_frame.min(axis=1).astype("Int64")
        eligible["rank_p95"] = rank_frame.max(axis=1).astype("Int64")
    eligible["recommended_next_experiment"] = "ATP synthase biochemical inhibition assay; then MIC and cytotoxicity as separate endpoints"
    eligible["experimental_cost_class"] = "high_unpriced; actual laboratory cost unknown"
    eligible["reason_for_prioritization"] = eligible.apply(
        lambda row: f"Vina={row.vina_affinity} kcal/mol; Open MM/GBSA={row.open_mmgbsa_deltaG} kcal/mol; exact evidence gate passed; ADMET remains unknown",
        axis=1,
    )
    eligible["scope"] = decision_config["scope"]
    columns = [
        "candidate_id", "canonical_smiles", "parent_id", "scaffold", "vina_affinity", "open_mmgbsa_deltaG",
        "open_mmgbsa_sd", "admet_evidence", "atp_prior_score", "antibacterial_prior_score", "uncertainty",
        "protocol_disagreement", "evidence_completeness", "evidence_missing", "final_score", "priority_rank",
        "rank_p05", "rank_p95", "recommended_next_experiment", "experimental_cost_class", "reason_for_prioritization", "decision_status", "scope",
    ]
    panel = eligible[columns].sort_values(["priority_rank", "candidate_id"]).reset_index(drop=True)
    panel_path = output_dir / "candidate_panel.csv"
    atomic_csv(panel_path, panel)
    atomic_json(output_dir / "candidate_panel.json", panel.to_dict("records"))
    atomic_csv(output_dir / "candidate_panel_top5.csv", panel.head(5))
    atomic_csv(output_dir / "candidate_panel_top10.csv", panel.head(10))
    atomic_csv(output_dir / "candidate_panel_top_configured.csv", panel.head(int(decision_config["output_top_n"])))
    lines = [
        "# Computational pre-experimental prioritization",
        "",
        "> This is a computational priority panel for experimental validation, not a list of active compounds or validated inhibitors.",
        "",
    ]
    for row in panel.to_dict("records"):
        lines.extend(
            [
                f"## #{row['priority_rank']} {row['candidate_id']}",
                "",
                f"- Vina (`vina_7p3w_v1`): {row['vina_affinity']} kcal/mol",
                f"- Open MM/GBSA (`open_mmgbsa_7p3w_v2`): {row['open_mmgbsa_deltaG']} ± {row['open_mmgbsa_sd']} kcal/mol",
                f"- Evidence completeness: {row['evidence_completeness']:.3f}; missing: {row['evidence_missing']}",
                f"- Rationale: {row['reason_for_prioritization']}",
                f"- Next experiment: {row['recommended_next_experiment']}",
                "",
            ]
        )
    (output_dir / "candidate_panel.md").write_text("\n".join(lines), encoding="utf-8")
    state = State(project)
    project_id = "in2_reconstructed_open_workflow"
    state.project_id(project_id)
    batch_id = state.batch(project_id, {"workflow": "in2_7p3w_reference", "run_id": run_id, "stage": "decision"})
    evidence_ids: list[str] = []
    with state.connect() as db:
        for compound_id in panel["candidate_id"]:
            evidence_ids.extend(
                row[0]
                for row in db.execute(
                    "SELECT evidence_id FROM evidence WHERE project_id=? AND compound_id=? AND evidence_type IN ('vina_affinity','open_mmgbsa_deltaG','open_mmgbsa_uncertainty') ORDER BY evidence_id",
                    (project_id, compound_id),
                )
            )
    decision_run_id = "decision_" + digest([project_id, run_id, decision_config["profile_id"]])[:24]
    model_version = "frozen_existing_priors_plus_transparent_decision_v1"
    panel_hash = sha256_file(panel_path)
    with state.connect() as db:
        old = db.execute("SELECT output_sha256 FROM decision_run WHERE decision_run_id=?", (decision_run_id,)).fetchone()
        if old and old[0] != panel_hash:
            raise ValueError("immutable_decision_run_output_changed")
        db.execute(
            "INSERT OR IGNORE INTO decision_run VALUES (?,?,?,?,?,?,?,?,?,?)",
            (decision_run_id, project_id, batch_id, None, decision_config["profile_id"], model_version, encode(sorted(set(evidence_ids))), str(panel_path), panel_hash, now()),
        )
    inference_protocol = {
        "protocol_id": "reference_decision_" + digest({"profile": decision_config, "models": processor.model_hashes})[:12],
        "profile": decision_config,
        "model_version": model_version,
        "training": False,
        "protected_model_hashes": processor.model_hashes,
        "scope": decision_config["scope"],
    }
    state.freeze_protocol(inference_protocol)
    input_artifact = state.artifact(input_path)
    panel_artifact = state.artifact(panel_path)
    job_id = state.job(
        batch_id,
        project_id,
        "__library__",
        "frozen_model_and_transparent_decision",
        inference_protocol["protocol_id"],
        [input_artifact],
        {"action": "reference_workflow_decision", "decision_run_id": decision_run_id, "input_sha256": sha256_file(input_path)},
    )
    with state.connect() as db:
        db.execute(
            "UPDATE calculation_job SET status='completed',completed_at=?,return_code=0,output_artifacts=? WHERE job_id=?",
            (now(), encode([panel_artifact]), job_id),
        )
    decision_evidence = []
    for row in panel.to_dict("records"):
        decision_evidence.extend(
            [
                {"compound_id": row["candidate_id"], "evidence_type": "reference_workflow_priority_score", "raw_value": float(row["final_score"]), "unit": "computational_priority_not_probability", "tool_version": model_version, "provenance": {"decision_run_id": decision_run_id, "profile": decision_config["profile_id"]}},
                {"compound_id": row["candidate_id"], "evidence_type": "reference_workflow_rank", "raw_value": {"rank": int(row["priority_rank"]), "rank_min": int(row["rank_p05"]), "rank_max": int(row["rank_p95"])}, "unit": "rank", "tool_version": model_version, "provenance": {"decision_run_id": decision_run_id, "profile": decision_config["profile_id"]}},
            ]
        )
    state.register_many(project_id, job_id, panel_artifact["artifact_hash"], decision_evidence, "frozen_model_output")
    summary = {
        "status": "completed",
        "profile_id": decision_config["profile_id"],
        "scope": decision_config["scope"],
        "input_count": len(acquisition),
        "evidence_gate_passed": len(panel),
        "output_count": len(panel),
        "unknown_admet_count": int(panel["admet_evidence"].eq("unknown").sum()),
        "training_performed": False,
        "model_v3_modified": False,
        "decision_run_id": decision_run_id,
        "registered_input_evidence_count": len(set(evidence_ids)),
        "artifact": {"path": str(panel_path), "sha256": sha256_file(panel_path)},
    }
    atomic_json(output_dir / "decision_summary.json", summary)
    return summary
