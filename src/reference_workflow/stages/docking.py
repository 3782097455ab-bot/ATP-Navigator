from __future__ import annotations

import concurrent.futures
import json
import time
from pathlib import Path
from typing import Any

import pandas as pd

from library_generation.workflow import ReproducibleWorkflow, _sha
from phase14_full_library_vina import _existing_result, _worker
from workspace.state import digest, file_hash

from ..util import atomic_csv, atomic_json, sha256_file, utc_now


def observed_vina_profile(project: Path) -> dict[str, Any]:
    source = project / "workspace_local/library_generation/in2_smoke_100_v1/vina_results.csv"
    root = project / "workspace_local/library_generation/in2_smoke_100_v1/vina_jobs"
    if not source.is_file():
        return {"status": "unavailable", "reason": "N=100 observed Vina results missing"}
    frame = pd.read_csv(source)
    success = frame.loc[frame["status"].eq("success")].copy()
    if success.empty:
        return {"status": "unavailable", "reason": "N=100 run has no successful observations"}
    started = pd.to_datetime(success["started_at"], utc=True, errors="coerce")
    completed = pd.to_datetime(success["completed_at"], utc=True, errors="coerce")
    wall = (completed.max() - started.min()).total_seconds()
    cpu = pd.to_numeric(success["elapsed_seconds"], errors="coerce").sum()
    disk = sum(path.stat().st_size for path in root.rglob("*") if path.is_file()) if root.is_dir() else 0
    result_files = list(root.rglob("result.json")) if root.is_dir() else []
    checkpoint_bytes = sum(path.stat().st_size for path in result_files)
    return {
        "status": "observed",
        "source": str(source.relative_to(project)).replace("\\", "/"),
        "observed_candidates": len(success),
        "wall_seconds": float(wall),
        "summed_candidate_seconds": float(cpu),
        "disk_bytes": int(disk),
        "terminal_checkpoint_bytes": int(checkpoint_bytes),
        "failure_rate": float(1 - len(success) / max(len(frame), 1)),
        "workers": 4,
    }


def estimate_vina(project: Path, candidate_count: int, workers: int) -> dict[str, Any]:
    observed = observed_vina_profile(project)
    if observed["status"] != "observed":
        return {**observed, "candidate_count": candidate_count}
    scale = candidate_count / observed["observed_candidates"]
    worker_scale = observed["workers"] / max(int(workers), 1)
    return {
        **observed,
        "candidate_count": int(candidate_count),
        "estimated_wall_seconds": float(observed["wall_seconds"] * scale * worker_scale),
        "estimated_cpu_seconds": float(observed["summed_candidate_seconds"] * scale),
        "estimated_disk_bytes": int(observed["disk_bytes"] * scale),
        "estimated_checkpoint_bytes": int(observed["terminal_checkpoint_bytes"] * scale),
        "estimated_failures": float(candidate_count * observed["failure_rate"]),
        "requested_workers": int(workers),
        "estimate_scope": "linear estimate from the real N=100 vina_7p3w_v1 run; not a performance guarantee",
    }


def _legacy_folder(project: Path, signature: str) -> Path | None:
    for run_id in ("in2_smoke_100_v1", "in2_generation_1000_v1", "in2_reconstructed_100k_v1"):
        candidate = project / "workspace_local/library_generation" / run_id / "vina_jobs" / signature[:2] / signature
        if (candidate / "result.json").is_file():
            return candidate
    return None


def run_vina(
    project: Path,
    run_id: str,
    accepted_path: Path,
    output_dir: Path,
    docking_config: dict[str, Any],
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    workflow = ReproducibleWorkflow(project, project / "configs/library_generation/in2_reconstructed_v1.json")
    protocol, receptor, vina = workflow._vina_assets()
    protocol_hash = digest(protocol)
    frame = pd.read_csv(accepted_path, keep_default_na=False)
    global_cache = project / "workspace_local/reference_workflow/vina_cache"
    tasks: list[dict[str, Any]] = []
    for row in frame.to_dict("records"):
        signature = _sha(
            {
                "compound_id": row["compound_id"],
                "canonical_smiles": row["canonical_smiles"],
                "protocol_hash": protocol_hash,
                "receptor_hash": file_hash(receptor),
                "tool_hash": file_hash(vina),
            }
        )
        legacy = _legacy_folder(project, signature)
        folder = legacy or (global_cache / signature[:2] / signature)
        tasks.append(
            {
                "compound_id": row["compound_id"],
                "smiles": row["canonical_smiles"],
                "signature": signature,
                "folder": str(folder),
                "protocol": protocol,
                "vina": str(vina),
                "receptor": str(receptor),
                "timeout": int(docking_config["timeout_seconds_per_candidate"]),
                "retry_failed": bool(docking_config.get("retry_failed", False)),
                "attempt": 1,
            }
        )
    results: list[dict[str, Any]] = []
    pending: list[dict[str, Any]] = []
    for task in tasks:
        existing = _existing_result(task)
        (results if existing else pending).append(existing or task)
    started = time.perf_counter()
    if pending:
        with concurrent.futures.ProcessPoolExecutor(max_workers=max(1, min(int(docking_config["workers"]), 8))) as pool:
            results.extend(pool.map(_worker, pending))
    by_id = {task["compound_id"]: task for task in tasks}
    for result in results:
        result.setdefault("folder", by_id[result["compound_id"]]["folder"])
    result_frame = pd.DataFrame(results).sort_values("compound_id").reset_index(drop=True)
    # Register from the real local artifact path, then publish a project-relative
    # path in the portable run output.
    evidence_count = workflow._register_vina(run_id, accepted_path, result_frame)
    if "folder" in result_frame:
        result_frame["folder"] = result_frame["folder"].map(
            lambda value: str(Path(value).resolve().relative_to(project)).replace("\\", "/")
        )
    result_path = output_dir / "vina_results.csv"
    atomic_csv(result_path, result_frame)
    summary = {
        "status": "completed" if int(result_frame["status"].eq("failed").sum()) == 0 else "completed_with_failures",
        "protocol_id": docking_config["protocol_id"],
        "protocol_hash": protocol_hash,
        "tool": docking_config["tool"],
        "tool_version": docking_config["tool_version"],
        "historical_glide_equivalence": False,
        "input_count": len(tasks),
        "success": int(result_frame["status"].eq("success").sum()),
        "failed": int(result_frame["status"].eq("failed").sum()),
        "cached": int(result_frame.get("cached", pd.Series(False, index=result_frame.index)).astype(bool).sum()),
        "newly_executed": len(pending),
        "pose_qc_pass": int(result_frame.get("pose_qc", pd.Series("", index=result_frame.index)).eq("pass").sum()),
        "elapsed_seconds": time.perf_counter() - started,
        "receptor_hash": file_hash(receptor),
        "tool_hash": file_hash(vina),
        "registry_protocol_record_count": evidence_count,
        "artifact": {"path": "docking/vina_results.csv", "sha256": sha256_file(result_path)},
        "completed_at": utc_now(),
    }
    atomic_json(output_dir / "docking_summary.json", summary)
    return summary
