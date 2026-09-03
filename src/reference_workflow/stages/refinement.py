from __future__ import annotations

import json
import math
import subprocess
import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from rdkit import Chem, DataStructs
from rdkit.Chem import rdFingerprintGenerator

from input_processor import CandidateInputProcessor
from workspace.state import State, digest, encode, now

from ..util import atomic_csv, atomic_json, json_safe, sha256_file, stable_hash, utc_now


def _utility(series: pd.Series, lower_is_better: bool = True) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce")
    n = int(values.notna().sum())
    if n <= 1:
        return pd.Series(np.where(values.notna(), 0.5, np.nan), index=series.index)
    ranks = values.rank(method="average", ascending=lower_is_better)
    return (n - ranks) / (n - 1)


def acquisition_panel(
    project: Path,
    accepted_path: Path,
    vina_results_path: Path,
    output_dir: Path,
    panel_size: int,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    accepted = pd.read_csv(accepted_path, keep_default_na=False)
    vina = pd.read_csv(vina_results_path, keep_default_na=False)
    frame = accepted.merge(vina, on="compound_id", suffixes=("", "_vina"), how="inner")
    frame = frame.loc[frame["status"].eq("success") & frame["pose_qc"].eq("pass")].copy()
    reference_manifest = pd.read_csv(project / "configs/projects/ab_atp_synthase/vina_7p3w_v1/candidate_identity_manifest.csv")
    reference_smiles = reference_manifest.loc[reference_manifest["compound_id"].eq("ATP-REF-IN2"), "SMILES"].iloc[0]
    generator = rdFingerprintGenerator.GetMorganGenerator(radius=2, fpSize=2048, includeChirality=True)
    reference_fp = generator.GetFingerprint(Chem.MolFromSmiles(reference_smiles))
    fps = [generator.GetFingerprint(Chem.MolFromSmiles(value)) for value in frame["canonical_smiles"]]
    fp_by_candidate = dict(zip(frame["compound_id"], fps))
    frame["similarity_to_IN2"] = [DataStructs.TanimotoSimilarity(reference_fp, fp) for fp in fps]
    frame["vina_utility"] = _utility(frame["vina_affinity"], True)
    frame["rank_boundary_proximity"] = 1.0 - (frame["vina_utility"] - 0.80).abs().clip(upper=0.80) / 0.80
    scaffold_sizes = frame.groupby("scaffold")["compound_id"].transform("size")
    frame["scaffold_novelty"] = 1.0 / np.sqrt(scaffold_sizes.clip(lower=1))
    frame["evidence_completeness_before"] = 0.50
    frame["evidence_gap"] = 1.0 - frame["evidence_completeness_before"]
    frame["protocol_uncertainty"] = np.nan
    frame["protocol_uncertainty_status"] = "unavailable_single_docking_protocol"
    frame["acquisition_priority"] = (
        0.40 * frame["vina_utility"]
        + 0.20 * frame["rank_boundary_proximity"]
        + 0.20 * frame["scaffold_novelty"]
        + 0.10 * frame["similarity_to_IN2"]
        + 0.10 * frame["evidence_gap"]
    )
    frame["acquisition_scope"] = "next expensive evidence priority; NOT biological hit ranking"
    frame = frame.sort_values(["acquisition_priority", "compound_id"], ascending=[False, True]).reset_index(drop=True)
    frame["acquisition_rank"] = range(1, len(frame) + 1)
    prior_success_ids: set[str] = set()
    cache_root = project / "workspace_local/reference_workflow/mmgbsa_cache"
    if cache_root.is_dir():
        for result_path in cache_root.rglob("result.json"):
            try:
                cached_result = json.loads(result_path.read_text(encoding="utf-8"))
            except (OSError, ValueError, json.JSONDecodeError):
                continue
            if cached_result.get("status") == "success":
                prior_success_ids.add(str(cached_result.get("candidate_id", "")))
    frame["existing_open_mmgbsa_evidence"] = frame["compound_id"].isin(prior_success_ids)
    selected_indices: list[int] = []
    if len(frame) and panel_size > 0:
        bridge = frame.loc[frame["existing_open_mmgbsa_evidence"]]
        selected_indices.append(int(bridge.index[0]) if len(bridge) else 0)
        while len(selected_indices) < min(panel_size, len(frame)):
            candidates = frame.loc[~frame.index.isin(selected_indices)].copy()
            selected_fps = [fp_by_candidate[frame.loc[index, "compound_id"]] for index in selected_indices]
            candidates["min_distance_to_selected"] = [
                1.0 - max(DataStructs.TanimotoSimilarity(fp_by_candidate[candidates.loc[index, "compound_id"]], chosen) for chosen in selected_fps)
                for index in candidates.index
            ]
            candidates["balanced_selection_score"] = 0.65 * candidates["acquisition_priority"] + 0.35 * candidates["min_distance_to_selected"]
            selected_indices.append(int(candidates.sort_values(["balanced_selection_score", "compound_id"], ascending=[False, True]).index[0]))
    selected = frame.loc[selected_indices].copy() if selected_indices else frame.head(0).copy()
    selected["selection_order"] = range(1, len(selected) + 1)
    selected["selection_class"] = np.select(
        [selected["existing_open_mmgbsa_evidence"], selected["selection_order"].eq(1)],
        ["workflow_bridge_cached_evidence", "multi_objective_strong"],
        default="diversity_and_evidence_gap",
    )
    selected["why_selected"] = selected.apply(
        lambda row: f"Vina utility={row.vina_utility:.3f}; scaffold novelty={row.scaffold_novelty:.3f}; boundary={row.rank_boundary_proximity:.3f}; missing Open MM/GBSA",
        axis=1,
    )
    selected["recommended_next_calculation"] = "open_mmgbsa_7p3w_v2"
    atomic_csv(output_dir / "acquisition_all_candidates.csv", frame)
    panel_path = output_dir / "acquisition_panel.csv"
    atomic_csv(panel_path, selected)
    summary = {
        "status": "completed_selection_only",
        "input_count": len(frame),
        "output_count": len(selected),
        "panel_size_configured": int(panel_size),
        "protocol_id": "acquisition_refinement_v1",
        "second_docking_protocol": None,
        "sp_xp_claim": False,
        "exact_structure_high_cost_cache_reuse": True,
        "scope": "evidence acquisition priority; not biological hit ranking",
        "artifact": {"path": str(panel_path), "sha256": sha256_file(panel_path)},
    }
    atomic_json(output_dir / "refinement_summary.json", summary)
    return summary


def _wsl_path(path: Path) -> str:
    value = str(path.resolve())
    if len(value) >= 3 and value[1:3] == ":\\":
        return f"/mnt/{value[0].lower()}/{value[3:].replace(chr(92), '/')}"
    return value.replace("\\", "/")


def _register_mmgbsa(project: Path, run_id: str, panel_path: Path, rows: list[dict[str, Any]], protocol: dict[str, Any]) -> int:
    state = State(project)
    project_id = "in2_reconstructed_open_workflow"
    state.project_id(project_id)
    state.freeze_protocol(protocol)
    batch = state.batch(project_id, {"workflow": "in2_7p3w_reference", "run_id": run_id, "stage": "open_mmgbsa"})
    source_artifact = state.artifact(panel_path)
    registered = 0
    for row in rows:
        state.candidate(project_id, row["candidate_id"], row["canonical_smiles"], alias="reconstructed_IN2_derivative")
        command = {
            "action": "reference_workflow_open_mmgbsa",
            "run_id": run_id,
            "protocol_hash": protocol["protocol_hash"],
            "source_pose_hash": row.get("pose_sha256"),
            "training": False,
        }
        job_id = state.job(batch, project_id, row["candidate_id"], "open_mmgbsa", protocol["protocol_id"], [source_artifact], command)
        result_path = Path(row["result_path"])
        if row["status"] != "success":
            with state.connect() as db:
                db.execute(
                    "UPDATE calculation_job SET status='failed',completed_at=?,return_code=1,reason=? WHERE job_id=? AND status!='completed'",
                    (now(), row.get("failure_reason", "worker_failed"), job_id),
                )
            continue
        artifact = state.artifact(result_path)
        with state.connect() as db:
            db.execute(
                "UPDATE calculation_job SET status='completed',started_at=?,completed_at=?,return_code=0,output_artifacts=?,reason='' WHERE job_id=?",
                (row.get("started_at", now()), row.get("completed_at", now()), encode([artifact]), job_id),
            )
        provenance = {
            "origin": "tool_execution",
            "workflow": "in2_7p3w_reference",
            "run_id": run_id,
            "protocol_hash": protocol["protocol_hash"],
            "source_pose_protocol": "vina_7p3w_v1",
            "source_pose_hash": row.get("pose_sha256"),
            "scope": "comparative screening-level high-cost computational evidence; not activity",
            "training": False,
        }
        state.register_many(
            project_id,
            job_id,
            artifact["artifact_hash"],
            [
                {"compound_id": row["candidate_id"], "evidence_type": "open_mmgbsa_deltaG", "raw_value": float(row["open_mmgbsa_deltaG"]), "unit": "kcal/mol", "tool_version": "OpenMM 8.6.0 + gmx_MMPBSA 1.6.5", "provenance": provenance},
                {"compound_id": row["candidate_id"], "evidence_type": "open_mmgbsa_uncertainty", "raw_value": float(row["open_mmgbsa_sd"]), "unit": "kcal/mol", "tool_version": "OpenMM 8.6.0 + gmx_MMPBSA 1.6.5", "provenance": provenance},
            ],
            "tool_execution",
        )
        registered += 2
    return registered


def run_mmgbsa(
    project: Path,
    run_id: str,
    panel_path: Path,
    output_dir: Path,
    mmgbsa_config: dict[str, Any],
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    protocol = json.loads((project / mmgbsa_config["protocol_file"]).read_text(encoding="utf-8"))
    if protocol["protocol_id"] != mmgbsa_config["protocol_id"]:
        raise ValueError("open_mmgbsa_protocol_id_mismatch")
    panel = pd.read_csv(panel_path, keep_default_na=False)
    rows: list[dict[str, Any]] = []
    newly_executed = 0
    started = time.perf_counter()
    cache_root = project / "workspace_local/reference_workflow/mmgbsa_cache"
    for candidate in panel.to_dict("records"):
        pose = Path(candidate["folder"]) / "pose.pdbqt"
        signature = stable_hash(
            {
                "candidate_id": candidate["compound_id"],
                "canonical_smiles": candidate["canonical_smiles"],
                "pose_sha256": candidate["pose_sha256"],
                "protocol_hash": protocol["protocol_hash"],
            }
        )
        work = cache_root / signature[:2] / signature
        result_path = work / "result.json"
        cached = False
        if result_path.is_file():
            result = json.loads(result_path.read_text(encoding="utf-8"))
            cached = result.get("status") == "success" and result.get("request_hash") is not None
            preserve_failed = result.get("status") == "failed" and not bool(mmgbsa_config.get("retry_failed", False))
            preserve_running = result.get("status") == "running"
        else:
            result = {}
            preserve_failed = False
            preserve_running = False
        if not cached and not preserve_failed and not preserve_running:
            work.mkdir(parents=True, exist_ok=True)
            request = {
                "candidate_id": candidate["compound_id"],
                "canonical_smiles": candidate["canonical_smiles"],
                "candidate_origin": "reconstructed_reproducible_derivative_library",
                "selection_class": candidate["selection_class"],
                "pose_path": _wsl_path(pose),
                "pose_sha256": candidate["pose_sha256"],
                "receptor_path": protocol["receptor"]["prepared_runtime_path"],
                "protocol": protocol,
                "evidence_role": "comparative_high_cost_computational_evidence",
                "training": False,
            }
            request_path = work / "request.json"
            atomic_json(request_path, request)
            command = [
                "wsl.exe", "-d", "Ubuntu", "--cd", _wsl_path(project), "--",
                "/home/lenovojlu/.local/share/atpnav/envs/atpnav-openmm/bin/python",
                "-m", "src.phase17_1.worker", "--request", _wsl_path(request_path), "--output", _wsl_path(work),
            ]
            atomic_json(work / "command_manifest.json", {"argv": command, "protocol_hash": protocol["protocol_hash"], "created_at": utc_now()})
            try:
                completed = subprocess.run(
                    command,
                    cwd=project,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    capture_output=True,
                    timeout=int(mmgbsa_config["timeout_seconds_per_candidate"]),
                    check=False,
                )
                stdout, stderr = completed.stdout, completed.stderr
            except subprocess.TimeoutExpired as exc:
                # The WSL worker owns an atomic checkpoint and may continue after
                # the Windows bridge reaches its operational wait limit.  Never
                # launch a duplicate candidate while result.json says running.
                stdout = exc.stdout.decode("utf-8", errors="replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
                stderr = exc.stderr.decode("utf-8", errors="replace") if isinstance(exc.stderr, bytes) else (exc.stderr or "")
                stderr += "\ncontroller_wait_timeout; inspect result.json/checkpoint before resume"
            (work / "worker.stdout.log").write_text(stdout, encoding="utf-8")
            (work / "worker.stderr.log").write_text(stderr, encoding="utf-8")
            newly_executed += 1
            result = json.loads(result_path.read_text(encoding="utf-8")) if result_path.is_file() else {
                "status": "failed",
                "failure_stage": "worker_process",
                "failure_reason": f"worker_returned_without_result:return_code={completed.returncode}",
            }
        analysis = result.get("analysis", {})
        rows.append(
            {
                "candidate_id": candidate["compound_id"],
                "canonical_smiles": candidate["canonical_smiles"],
                "status": result.get("status", "failed"),
                "cached": cached or preserve_failed or preserve_running,
                "failure_stage": result.get("failure_stage", ""),
                "failure_reason": result.get("failure_reason", ""),
                "open_mmgbsa_deltaG": analysis.get("open_mmgbsa_deltaG"),
                "open_mmgbsa_sd": analysis.get("open_mmgbsa_sd"),
                "unit": analysis.get("unit", "kcal/mol"),
                "analyzed_frames": analysis.get("analyzed_frames", 0),
                "runtime_seconds": result.get("elapsed_seconds"),
                "protocol_id": protocol["protocol_id"],
                "protocol_hash": protocol["protocol_hash"],
                "source_pose_protocol": "vina_7p3w_v1",
                "pose_sha256": candidate["pose_sha256"],
                "result_path": str(result_path),
                "started_at": result.get("started_at"),
                "completed_at": result.get("completed_at"),
                "scientific_scope": protocol["scientific_interpretation"],
            }
        )
    results = pd.DataFrame(rows)
    results_path = output_dir / "open_mmgbsa_results.csv"
    atomic_csv(results_path, results)
    if len(results) and results["status"].eq("running").any():
        raise RuntimeError(
            "open_mmgbsa_worker_still_running; preserved checkpoint and refused duplicate execution"
        )
    registered = _register_mmgbsa(project, run_id, panel_path, rows, protocol) if len(rows) else 0
    summary = {
        "status": "completed" if len(results) and results["status"].eq("success").all() else "completed_with_failures" if len(results) else "not_run_empty_panel",
        "protocol_id": protocol["protocol_id"],
        "protocol_hash": protocol["protocol_hash"],
        "historical_prime_equivalence": False,
        "input_count": len(panel),
        "success": int(results["status"].eq("success").sum()) if len(results) else 0,
        "failed": int(results["status"].eq("failed").sum()) if len(results) else 0,
        "cached": int(results["cached"].sum()) if len(results) else 0,
        "newly_executed": newly_executed,
        "registry_records_added_or_verified": registered,
        "elapsed_seconds": time.perf_counter() - started,
        "artifact": {"path": str(results_path), "sha256": sha256_file(results_path)},
    }
    atomic_json(output_dir / "mmgbsa_summary.json", summary)
    return summary
