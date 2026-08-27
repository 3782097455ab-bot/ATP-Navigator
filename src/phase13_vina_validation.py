"""Phase 13 real 7P3W Vina validation; no training and no score substitution."""
from __future__ import annotations

import argparse
import json
import math
import shutil
import sys
from pathlib import Path

import pandas as pd
from scipy.stats import kendalltau, spearmanr

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "src"))

from tools.tool_registry import discover
from workspace.multi_evidence import enriched
from workspace.multi_workflow import MultiBackendWorkspace
from workspace.state import encode, file_hash, now, write_json


PROJECT_ID = "ab_atp_phase13"
PROTOCOL_ID = "vina_7p3w_v1"
CONFIG_REL = Path("configs/projects/ab_atp_synthase/vina_7p3w_v1")
HISTORICAL_PROTOCOL = {
    "protocol_id": "historical_glide_vsw_v1",
    "protocol_kind": "historical_computational_import",
    "target_reference": "7P3W",
    "tool_family": "glide",
    "source": "results/ranking_output.csv",
    "source_scope": "historical VSW Glide/static MMGBSA and frozen Model v3 outputs",
    "training": False,
}


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def model_hashes(project: Path, baseline: dict[str, str]) -> dict[str, str]:
    return {name: file_hash(project / Path(name)) for name in baseline}


def initial_model_snapshot(project: Path) -> dict[str, str]:
    payload = load_json(project / "results/phase12/internal_17_run2/execution_summary.json")
    baseline = payload["model_hashes"]
    current = model_hashes(project, baseline)
    if current != baseline:
        changed = sorted(key for key in baseline if baseline[key] != current.get(key))
        raise ValueError("Protected model hash mismatch before Phase 13: " + ",".join(changed))
    return baseline


def protocol(project: Path) -> dict:
    cfg = load_json(project / CONFIG_REL / "vina_protocol.json")
    if cfg["protocol_id"] != PROTOCOL_ID or cfg["protocol_status"] != "ready":
        raise ValueError("Phase 13 protocol is not frozen/ready")
    return cfg


def write_csv(frame: pd.DataFrame, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False, encoding="utf-8")


def identity_qc(project: Path, destination: Path) -> dict:
    from rdkit import Chem
    from rdkit.Chem import rdMolDescriptors

    manifest = pd.read_csv(project / CONFIG_REL / "candidate_identity_manifest.csv", dtype=str)
    ranking = pd.read_csv(project / "results/ranking_output.csv", dtype=str)
    checks = []
    for row in manifest.itertuples(index=False):
        mol = Chem.MolFromSmiles(row.SMILES)
        if mol is None:
            raise ValueError("Invalid manifest structure: " + row.compound_id)
        match = ranking.loc[ranking["compound_id"].eq(row.compound_id)]
        registry_match = True
        if row.compound_id != "ATP-REF-IN2":
            registry_match = len(match) == 1 and Chem.MolToSmiles(Chem.MolFromSmiles(match.iloc[0]["smiles"])) == Chem.MolToSmiles(mol)
        checks.append({
            "compound_id": row.compound_id,
            "historical_alias": row.historical_alias,
            "canonical_smiles": Chem.MolToSmiles(mol),
            "formula": rdMolDescriptors.CalcMolFormula(mol),
            "registry_identity_match": bool(registry_match),
            "identity_status": row.identity_status,
        })
    if not all(row["registry_identity_match"] for row in checks):
        raise ValueError("Internal candidate identity mismatch")

    complex_path = project / CONFIG_REL / "assets/ATP-Ref_IN2_complex.pdb"
    complex_mol = Chem.MolFromPDBFile(str(complex_path), removeHs=False, sanitize=False)
    fragments = Chem.GetMolFrags(complex_mol, asMols=True, sanitizeFrags=False)
    ligand = max((mol for mol in fragments if mol.GetNumAtoms() < 200), key=lambda mol: mol.GetNumAtoms())
    Chem.SanitizeMol(ligand)
    pose_smiles = Chem.MolToSmiles(Chem.RemoveHs(ligand))
    manifest_smiles = checks[-1]["canonical_smiles"]
    pose_identity_match = pose_smiles == manifest_smiles
    if not pose_identity_match:
        raise ValueError("IN-2 pose connectivity/protonation identity mismatch")

    external = project.parent / "ATP_Navigator_Data_Release_v1/compound_aliases.csv"
    external_qc = {"status": "not_available"}
    if external.is_file():
        table = pd.read_csv(external, dtype=str, keep_default_na=False)
        rows = table.loc[table.astype(str).apply(lambda col: col.str.contains("ATP Synthesis-IN-2", regex=False)).any(axis=1)]
        candidates = []
        for value in rows.get("corrected_smiles", pd.Series(dtype=str)).drop_duplicates():
            mol = Chem.MolFromSmiles(value)
            if mol:
                candidates.append({
                    "source_smiles": value,
                    "canonical_smiles": Chem.MolToSmiles(mol),
                    "matches_historical_pose": Chem.MolToSmiles(mol) == manifest_smiles,
                })
        external_qc = {
            "status": "audited",
            "rows": int(len(rows)),
            "structures": candidates,
            "use_in_phase13": False,
            "issue_class": "compound identity / provenance QC",
            "action": "isolated from docking; original release remains unchanged",
        }

    result = {
        "candidate_checks": checks,
        "in2_pose_smiles": pose_smiles,
        "in2_manifest_smiles": manifest_smiles,
        "in2_pose_identity_match": pose_identity_match,
        "external_release_in2_qc": external_qc,
        "training": False,
    }
    write_json(destination, result)
    return result


def candidate_inputs(project: Path, output: Path) -> tuple[Path, Path]:
    manifest = pd.read_csv(project / CONFIG_REL / "candidate_identity_manifest.csv", dtype=str)
    five = manifest[["compound_id", "historical_alias", "SMILES"]].copy()
    five_path = output / "validation_5_candidates.csv"
    write_csv(five, five_path)

    ranking = pd.read_csv(project / "results/ranking_output.csv", dtype=str)
    if len(ranking) != 17 or ranking["compound_id"].duplicated().any():
        raise ValueError("Internal frozen ranking is not the expected 17 unique candidates")
    internal = ranking[["compound_id", "historical_alias", "smiles"]].rename(columns={"smiles": "SMILES"})
    internal_path = output / "internal_17_candidates.csv"
    write_csv(internal, internal_path)
    return five_path, internal_path


def job_rows(workspace: MultiBackendWorkspace, run_id: str, node_id: str) -> dict[str, dict]:
    node = workspace.node(run_id, node_id)
    return {candidate: workspace.state.get_job(job) for candidate, job in json.loads(node["jobs"]).items()}


def candidate_success(workspace: MultiBackendWorkspace, run_id: str) -> dict[str, dict]:
    state = workspace.state
    docking = job_rows(workspace, run_id, "docking")
    pose_qc = job_rows(workspace, run_id, "pose_qc")
    records = enriched(state, PROJECT_ID)
    output = {}
    for candidate in json.loads(workspace.get_run(run_id)["candidate_ids"]):
        affinity = [row for row in records if row["compound_id"] == candidate and row["protocol_id"] == PROTOCOL_ID and row["evidence_type"] == "vina_affinity"]
        qc = [row for row in records if row["compound_id"] == candidate and row["protocol_id"] == PROTOCOL_ID and row["evidence_type"] == "pose_qc"]
        output[candidate] = {
            "docking_job": docking.get(candidate, {}).get("status", "missing"),
            "pose_qc_job": pose_qc.get(candidate, {}).get("status", "missing"),
            "affinity": affinity[-1]["value"] if affinity else None,
            "registry_affinity_records": len(affinity),
            "pose_qc_records": len(qc),
            "pose_qc_pass": bool(qc and qc[-1]["value"].get("status") == "pass"),
            "success": bool(affinity and qc and qc[-1]["value"].get("status") == "pass"),
        }
    return output


def register_historical_baselines(workspace: MultiBackendWorkspace, batch_id: str, internal_path: Path) -> int:
    state = workspace.state
    state.freeze_protocol(HISTORICAL_PROTOCOL)
    source = state.artifact(workspace.state.project / "results/ranking_output.csv")
    command = {
        "action": "historical_baseline_import",
        "source_sha256": source["artifact_hash"],
        "endpoint_segregation": ["Glide docking", "static MMGBSA", "Model v3 rank"],
        "training": False,
    }
    job = state.job(batch_id, PROJECT_ID, "__library__", "historical_import", HISTORICAL_PROTOCOL["protocol_id"], [source], command)
    before = len(state.evidence_rows(PROJECT_ID))
    with state.connect() as db:
        db.execute(
            "UPDATE calculation_job SET status='completed',completed_at=?,return_code=0,output_artifacts=? WHERE job_id=?",
            (now(), encode([source]), job),
        )
        db.execute("INSERT OR IGNORE INTO workflow_job_link VALUES (?,?)", (batch_id, job))
    ranking = pd.read_csv(state.project / "results/ranking_output.csv")
    rows = []
    for row in ranking.to_dict("records"):
        rows.extend([
            {
                "compound_id": row["compound_id"],
                "evidence_type": "docking_score",
                "raw_value": float(row["glide_docking_score"]),
                "unit": "Glide_score",
                "provenance": {
                    "tool_id": "glide",
                    "tool_family": "glide",
                    "evidence_role": "historical_computational_evidence",
                    "historical_alias": row["historical_alias"],
                },
            },
            {
                "compound_id": row["compound_id"],
                "evidence_type": "docking",
                "raw_value": {
                    "raw_score": float(row["glide_docking_score"]),
                    "score_field": "glide_docking_score",
                    "historical_alias": row["historical_alias"],
                },
                "unit": "docking_result_bundle",
                "provenance": {
                    "tool_id": "glide",
                    "tool_family": "glide",
                    "evidence_role": "historical_computational_evidence",
                    "historical_alias": row["historical_alias"],
                },
            },
            {
                "compound_id": row["compound_id"],
                "evidence_type": "mmgbsa_score",
                "raw_value": float(row["reference_mmgbsa"]),
                "unit": "kcal/mol",
                "provenance": {
                    "tool_id": "prime_mmgbsa_historical",
                    "tool_family": "prime_mmgbsa",
                    "evidence_role": "historical_static_computational_evidence",
                },
            },
            {
                "compound_id": row["compound_id"],
                "evidence_type": "model_v3_rank",
                "raw_value": int(row["ai_rank"]),
                "unit": "rank",
                "provenance": {
                    "tool_id": "frozen_model_v3",
                    "tool_family": "frozen_model",
                    "evidence_role": "frozen_model_output",
                },
            },
        ])
    state.register_many(PROJECT_ID, job, source["artifact_hash"], rows, "historical_result")
    return len(state.evidence_rows(PROJECT_ID)) - before


def export_poses(workspace: MultiBackendWorkspace, run_id: str, output: Path) -> list[dict]:
    destination = output / "poses"
    destination.mkdir(parents=True, exist_ok=True)
    rows = []
    for candidate, job in job_rows(workspace, run_id, "docking").items():
        if job["status"] != "completed":
            continue
        for artifact in json.loads(job["output_artifacts"]):
            path = workspace.state.verify_artifact(artifact["artifact_hash"])
            if path.name != "pose.pdbqt":
                continue
            target = destination / f"{candidate}_vina_7p3w_v1.pdbqt"
            if not target.exists():
                shutil.copyfile(path, target)
            if file_hash(target) != artifact["artifact_hash"]:
                raise ValueError("Exported pose hash mismatch")
            rows.append({
                "compound_id": candidate,
                "job_id": job["job_id"],
                "workflow_run_id": run_id,
                "source_job_batch_id": job["batch_id"],
                "cache_reused_from_prior_batch": job["batch_id"] != run_id,
                "pose_path": str(target.relative_to(workspace.state.project)),
                "pose_sha256": artifact["artifact_hash"],
                "attempt": job["attempt"],
            })
    write_csv(pd.DataFrame(rows), output / "pose_artifact_manifest.csv")
    return rows


def rank_series(frame: pd.DataFrame, column: str) -> pd.Series:
    return pd.to_numeric(frame[column], errors="raise").rank(method="min", ascending=True)


def shadow_comparison(workspace: MultiBackendWorkspace, output: Path) -> dict:
    records = enriched(workspace.state, PROJECT_ID)
    vina = {
        row["compound_id"]: float(row["value"])
        for row in records
        if row["protocol_id"] == PROTOCOL_ID and row["evidence_type"] == "vina_affinity"
    }
    historical = pd.read_csv(workspace.state.project / "results/ranking_output.csv")
    frame = historical[[
        "compound_id", "historical_alias", "glide_docking_score", "reference_mmgbsa", "ai_rank"
    ]].copy()
    frame["vina_affinity"] = frame["compound_id"].map(vina)
    frame = frame.loc[frame["vina_affinity"].notna()].copy()
    frame["vina_rank"] = rank_series(frame, "vina_affinity")
    frame["glide_rank"] = rank_series(frame, "glide_docking_score")
    frame["mmgbsa_rank"] = rank_series(frame, "reference_mmgbsa")
    frame["model_v3_rank"] = pd.to_numeric(frame["ai_rank"])
    for name in ["glide", "mmgbsa", "model_v3"]:
        frame[f"vina_vs_{name}_rank_shift"] = frame["vina_rank"] - frame[f"{name}_rank"]
        frame[f"vina_vs_{name}_abs_rank_shift"] = frame[f"vina_vs_{name}_rank_shift"].abs()
    write_csv(frame.sort_values("vina_rank"), output / "open_toolchain_shadow_analysis.csv")

    metrics = {
        "status": "complete" if len(frame) == 17 else "partial",
        "n": int(len(frame)),
        "scope": "descriptive protocol comparison only; not biological validation",
        "comparisons": {},
    }
    for name in ["glide", "mmgbsa", "model_v3"]:
        other = frame[f"{name}_rank"]
        spearman = spearmanr(frame["vina_rank"], other)
        kendall = kendalltau(frame["vina_rank"], other)
        top_vina = set(frame.nsmallest(5, "vina_rank")["compound_id"])
        top_other = set(frame.nsmallest(5, f"{name}_rank")["compound_id"])
        metrics["comparisons"][f"vina_vs_{name}"] = {
            "spearman": float(spearman.statistic),
            "spearman_pvalue": float(spearman.pvalue),
            "kendall": float(kendall.statistic),
            "kendall_pvalue": float(kendall.pvalue),
            "top5_overlap_count": len(top_vina & top_other),
            "top5_overlap_compounds": sorted(top_vina & top_other),
        }
    largest = frame.nlargest(min(10, len(frame)), "vina_vs_glide_abs_rank_shift")
    write_csv(largest, output / "largest_protocol_disagreements.csv")
    metrics["largest_vina_glide_disagreements"] = largest[[
        "compound_id", "historical_alias", "vina_rank", "glide_rank", "vina_vs_glide_abs_rank_shift"
    ]].to_dict("records")
    write_json(output / "shadow_comparison_metrics.json", metrics)
    return metrics


def export_registry(workspace: MultiBackendWorkspace, output: Path) -> int:
    rows = []
    for row in enriched(workspace.state, PROJECT_ID):
        provenance = json.loads(row["provenance"])
        rows.append({
            "evidence_id": row["evidence_id"],
            "compound_id": row["compound_id"],
            "evidence_type": row["evidence_type"],
            "raw_value": encode(row["value"]),
            "unit": row["unit"],
            "tool_id": row["tool_id"],
            "tool_family": provenance.get("tool_family", "unknown"),
            "protocol_id": row["protocol_id"],
            "run_id": row["run_id"],
            "job_id": row["job_id"],
            "artifact_hash": row["artifact_hash"],
            "timestamp": row["timestamp"],
            "provenance": row["provenance"],
        })
    write_csv(pd.DataFrame(rows), output / "evidence_registry_export.csv")
    return len(rows)


def job_fingerprint(workspace: MultiBackendWorkspace, run_id: str) -> dict:
    snapshot = {}
    for candidate, job in job_rows(workspace, run_id, "docking").items():
        if job["status"] != "completed":
            continue
        poses = [item["artifact_hash"] for item in json.loads(job["output_artifacts"]) if Path(item["path"]).name == "pose.pdbqt"]
        snapshot[candidate] = {"job_id": job["job_id"], "attempt": job["attempt"], "pose_hashes": poses}
    return snapshot


def resume_validation(before: dict, after: dict) -> dict:
    preserved = {
        candidate: before[candidate] == after.get(candidate)
        for candidate in before
    }
    return {
        "completed_before_pause": len(before),
        "completed_after_resume": len(after),
        "previous_jobs_unchanged": all(preserved.values()),
        "per_candidate_unchanged": preserved,
        "duplicate_execution_prevented": all(preserved.values()),
        "output_hashes_preserved": all(preserved.values()),
    }


def htvs_plan(output: Path, docking_jobs: dict[str, dict]):
    durations = []
    for job in docking_jobs.values():
        if job.get("started_at") and job.get("completed_at"):
            start = pd.Timestamp(job["started_at"])
            end = pd.Timestamp(job["completed_at"])
            durations.append((end - start).total_seconds())
    median = float(pd.Series(durations).median()) if durations else None
    count = 1633
    plan = {
        "status": "plan_only_not_executed",
        "candidate_count": count,
        "protocol_id": PROTOCOL_ID,
        "estimated_docking_jobs": count,
        "observed_median_seconds_per_docking_job": median,
        "estimated_serial_runtime_hours": (median * count / 3600) if median else "unknown",
        "recommended_batch_size": 25,
        "estimated_batches": math.ceil(count / 25),
        "cache_strategy": "content-addressed candidate/protocol/tool/worker signature; reuse only exact matches",
        "failure_recovery": "durable receipt + explicit retry; completed jobs never relaunched",
        "disk_usage_estimate": "measure Phase13 pose/log median before authorization; no fabricated estimate",
        "execution_authorized": False,
    }
    write_json(output / "HTVS1633_Vina_execution_plan.json", plan)


def run(project: Path) -> dict:
    project = project.resolve()
    output = project / "results/phase13"
    output.mkdir(parents=True, exist_ok=True)
    baseline = initial_model_snapshot(project)
    write_json(output / "model_hashes_before.json", baseline)
    identity = identity_qc(project, output / "in2_and_candidate_identity_qc.json")
    five_path, internal_path = candidate_inputs(project, output)
    caps = discover(project, output / "system_capabilities.json", check_license=True)
    workspace = MultiBackendWorkspace(project, capabilities=caps)
    cfg = protocol(project)
    registry_path = output / "run_registry.json"
    registry = load_json(registry_path) if registry_path.is_file() else {}

    if "validation_5_run_id" not in registry:
        created = workspace.create(
            PROJECT_ID, five_path,
            "对接最多5个，MMGBSA最多0个，最终实验预算0个",
            mode="open_toolchain", protocol=cfg,
            source_metadata={"phase": 13, "cohort": "validation_5", "training": False},
        )
        registry["validation_5_run_id"] = created["run_id"]
        registry["session_id"] = created["session_id"]
        write_json(registry_path, registry)
    five_run = registry["validation_5_run_id"]
    five_result = workspace.resume(five_run, confirm=True, retry_failed=True)
    five = candidate_success(workspace, five_run)
    write_json(output / "validation_5_results.json", five)
    success_count = sum(row["success"] for row in five.values())
    gate = {
        "success_count": success_count,
        "candidate_count": len(five),
        "at_least_4_of_5": success_count >= 4,
        "in2_success": five.get("ATP-REF-IN2", {}).get("success", False),
        "parser_registry_pose_qc_all_successes": all(
            (not row["success"]) or (row["registry_affinity_records"] == 1 and row["pose_qc_records"] == 1 and row["pose_qc_pass"])
            for row in five.values()
        ),
    }
    gate["passed"] = all([gate["at_least_4_of_5"], gate["in2_success"], gate["parser_registry_pose_qc_all_successes"]])
    write_json(output / "validation_5_gate.json", gate)

    second_result = None
    resume_check = {"status": "not_run_gate_failed"}
    comparison = {"status": "not_available_gate_failed", "n": 0}
    historical_added = 0
    if gate["passed"]:
        if "internal_17_run_id" not in registry:
            created = workspace.create(
                PROJECT_ID, internal_path,
                "对接最多17个，MMGBSA最多0个，最终实验预算0个",
                mode="open_toolchain", protocol=cfg,
                source_metadata={"phase": 13, "cohort": "internal17_vina_7p3w_v1", "training": False},
                session_id=None,
            )
            registry["internal_17_run_id"] = created["run_id"]
            write_json(registry_path, registry)
        internal_run = registry["internal_17_run_id"]
        historical_added = register_historical_baselines(workspace, internal_run, internal_path)
        current = workspace.get_run(internal_run)
        if not current["confirmed"]:
            paused = workspace.resume(
                internal_run, confirm=True, retry_failed=True, max_new_docking_jobs=3
            )
            before = job_fingerprint(workspace, internal_run)
            write_json(output / "controlled_pause_snapshot.json", {"result": paused, "jobs": before})
        else:
            before_payload = load_json(output / "controlled_pause_snapshot.json") if (output / "controlled_pause_snapshot.json").is_file() else {"jobs": {}}
            before = before_payload["jobs"]
        second_result = workspace.resume(internal_run, retry_failed=True)
        after = job_fingerprint(workspace, internal_run)
        resume_check = resume_validation(before, after)
        resume_check["status"] = "pass" if resume_check["previous_jobs_unchanged"] else "fail"
        write_json(output / "resume_validation.json", resume_check)
        internal = candidate_success(workspace, internal_run)
        write_json(output / "internal_17_results.json", internal)
        export_poses(workspace, internal_run, output)
        if sum(row["success"] for row in internal.values()) == 17:
            comparison = shadow_comparison(workspace, output)
            htvs_plan(output, job_rows(workspace, internal_run, "docking"))
        else:
            comparison = {"status": "partial_or_failed", "n": sum(row["success"] for row in internal.values())}
            write_json(output / "shadow_comparison_metrics.json", comparison)

    registry_count = export_registry(workspace, output)
    from workspace.workflow_service import project_candidate_docking_evidence, project_vina_glide_disagreements
    query_examples = {
        "hit3": project_candidate_docking_evidence(workspace.state, PROJECT_ID, "Hit3"),
        "disagreements": project_vina_glide_disagreements(workspace.state, PROJECT_ID),
    }
    write_json(output / "agent_protocol_query_examples.json", query_examples)

    final_hashes = model_hashes(project, baseline)
    models_unchanged = final_hashes == baseline
    write_json(output / "model_hashes_after.json", final_hashes)
    summary = {
        "phase": "Phase 13",
        "protocol_id": PROTOCOL_ID,
        "historical_site_recovered": True,
        "box_source": "verbatim VSW.maegz historical gridbox center/range metadata",
        "validation_5": five,
        "validation_gate": gate,
        "internal_17_run": second_result,
        "comparison": comparison,
        "historical_registry_records_added_this_call": historical_added,
        "registry_record_count": registry_count,
        "resume_validation": resume_check,
        "commercial_tools": {
            name: caps["tools"][name]["availability"]
            for name in ["glide", "prime_mmgbsa", "qikprop", "ligprep"]
        },
        "models_checked": len(baseline),
        "models_unchanged": models_unchanged,
        "training": False,
        "decision_engine_changed": False,
        "identity_qc": identity,
    }
    write_json(output / "phase13_execution_summary.json", summary)
    if not models_unchanged:
        raise ValueError("Protected model files changed during Phase 13")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=PROJECT)
    args = parser.parse_args()
    result = run(args.project_root)
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
