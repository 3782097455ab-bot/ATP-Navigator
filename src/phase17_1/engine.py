"""Checkpointed Phase 17.1 qualification and gated expansion runner.

This module consumes the frozen Phase 17 candidate pool and the frozen
``open_mmgbsa_7p3w_v2`` protocol.  It never invents numerical output: every
successful value is parsed from a completed tool execution by ``worker.py``.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from collections import Counter, deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from src.high_cost.engine import build_candidate_pool, qualification_set
from src.phase17_1.protocol import stable_hash
from src.workspace.state import State, digest, encode, now


PROTOCOL_ID = "open_mmgbsa_7p3w_v2"
PROJECT_ID = "atp_synthase"
STAGES = (("qualification", 8), ("pilot30", 30), ("expanded60", 60))


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
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


def verify_protocol(protocol: dict[str, Any]) -> None:
    recorded = protocol.get("protocol_hash", "")
    unhashed = {key: value for key, value in protocol.items() if key != "protocol_hash"}
    if stable_hash(unhashed) != recorded:
        raise ValueError("frozen_protocol_hash_mismatch")
    if protocol.get("protocol_id") != PROTOCOL_ID:
        raise ValueError("unexpected_protocol_id")
    if protocol.get("status") != "ready_for_qualification":
        raise ValueError("protocol_not_ready_for_qualification")
    if protocol.get("resource_policy", {}).get("concurrent_jobs") != 1:
        raise ValueError("qualification_concurrency_must_remain_one")


def execution_policy(project: Path) -> dict[str, Any]:
    path = project / "configs/phase17_1_execution_policy.json"
    policy = json.loads(path.read_text(encoding="utf-8"))
    if policy.get("qualification_target") != 8 or policy.get("pilot_target") != 30:
        raise ValueError("phase17_1_execution_targets_changed")
    if policy.get("scientific_protocol_changed") is not False:
        raise ValueError("execution_policy_cannot_change_scientific_protocol")
    if policy.get("training_allowed") is not False:
        raise ValueError("phase17_1_training_must_remain_disabled")
    return policy


def frozen_model_hashes(project: Path) -> dict[str, str]:
    expected = json.loads(
        (project / "results/phase14/model_hashes_after.json").read_text(encoding="utf-8")
    )
    actual: dict[str, str] = {}
    for relative, expected_hash in expected.items():
        path = project / relative.replace("\\", "/")
        if not path.is_file():
            raise FileNotFoundError(f"frozen_model_missing:{relative}")
        actual[relative] = sha256(path)
        if actual[relative] != expected_hash:
            raise ValueError(f"frozen_model_hash_changed:{relative}")
    return actual


def _round_robin_expansion(pool: pd.DataFrame, excluded: set[str], count: int) -> pd.DataFrame:
    """Choose from the existing Phase 17 pool without replacing its members.

    Each source selection class is ordered by its already-computed acquisition
    score.  Round-robin traversal prevents the expanded panel from collapsing
    onto a single class; it does not select candidates for easier computation.
    """
    available = pool.loc[~pool["candidate_id"].isin(excluded)].copy()
    available["_score"] = pd.to_numeric(available["acquisition_score"], errors="coerce").fillna(-math.inf)
    groups: dict[str, deque[dict[str, Any]]] = {}
    for class_name, group in available.groupby("selection_class", sort=True):
        ordered = group.sort_values(["_score", "candidate_id"], ascending=[False, True])
        groups[str(class_name)] = deque(ordered.drop(columns=["_score"]).to_dict("records"))
    selected: list[dict[str, Any]] = []
    while len(selected) < count and any(groups.values()):
        for class_name in sorted(groups):
            if groups[class_name] and len(selected) < count:
                selected.append(groups[class_name].popleft())
    if len(selected) != count:
        raise ValueError(f"insufficient_phase17_candidates:{len(selected)}/{count}")
    return pd.DataFrame(selected)


def build_cumulative_plan(project: Path) -> pd.DataFrame:
    pool = build_candidate_pool(project)
    qualification = qualification_set(pool).copy()
    qualification["stage_added"] = "qualification"
    qualification["panel_order"] = range(1, 9)
    expansion = _round_robin_expansion(pool, set(qualification["candidate_id"]), 52)
    expansion["panel_order"] = range(9, 61)
    expansion["stage_added"] = ["pilot30" if order <= 30 else "expanded60" for order in expansion["panel_order"]]
    qualification = qualification.drop(columns=["qualification_order"], errors="ignore")
    plan = pd.concat([qualification, expansion], ignore_index=True, sort=False)
    plan = plan.sort_values("panel_order").reset_index(drop=True)
    if len(plan) != 60 or plan["candidate_id"].nunique() != 60:
        raise ValueError("cumulative_panel_must_have_60_unique_candidates")
    return plan


def phase14_pose_index(project: Path) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    root = project / "workspace_local/phase14_vina/jobs"
    for result_path in root.glob("*/*/result.json"):
        try:
            payload = json.loads(result_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        candidate = payload.get("compound_id")
        pose = result_path.with_name("pose.pdbqt")
        if payload.get("status") == "success" and candidate and pose.is_file():
            index[candidate] = {
                "pose_path": pose,
                "source": "phase14_vina_success_cache",
                "source_result": result_path,
                "protocol_id": payload.get("protocol_id"),
                "pose_sha256_recorded": payload.get("pose_sha256"),
            }
    return index


def in2_pose(project: Path) -> dict[str, Any] | None:
    for result_path in (project / "workspace_local/multi_jobs").glob("*/attempt_*/result.json"):
        try:
            payload = json.loads(result_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if payload.get("compound_id") != "ATP-REF-IN2":
            continue
        pose = result_path.with_name("pose.pdbqt")
        evidence = payload.get("evidence", [])
        if pose.is_file() and any(item.get("evidence_type") == "vina_affinity" for item in evidence):
            return {
                "pose_path": pose,
                "source": "phase13_multi_protocol_execution_cache",
                "source_result": result_path,
                "protocol_id": "vina_7p3w_v1",
                "pose_sha256_recorded": next(
                    (
                        item.get("provenance", {}).get("output_pose_hash")
                        for item in evidence
                        if item.get("evidence_type") == "vina_affinity"
                    ),
                    None,
                ),
            }
    return None


def resolve_poses(project: Path, plan: pd.DataFrame) -> pd.DataFrame:
    phase14 = phase14_pose_index(project)
    internal = in2_pose(project)
    rows: list[dict[str, Any]] = []
    for row in plan.to_dict("records"):
        candidate = row["candidate_id"]
        resolved: dict[str, Any] | None = None
        declared = str(row.get("pose_path", "") or "").replace("\\", "/")
        if declared:
            path = project / declared
            if path.is_file():
                resolved = {
                    "pose_path": path,
                    "source": "phase16_declared_vina_pose",
                    "source_result": "",
                    "protocol_id": "vina_7p3w_v1",
                    "pose_sha256_recorded": None,
                }
        if candidate == "ATP-REF-IN2":
            resolved = internal
        elif candidate in phase14:
            resolved = phase14[candidate]
        if resolved is None:
            raise FileNotFoundError(f"frozen_vina_pose_not_resolved:{candidate}")
        path = Path(resolved["pose_path"]).resolve()
        observed_hash = sha256(path)
        recorded_hash = resolved.get("pose_sha256_recorded")
        if recorded_hash and recorded_hash != observed_hash:
            raise ValueError(f"frozen_pose_hash_mismatch:{candidate}")
        if resolved.get("protocol_id") != "vina_7p3w_v1":
            raise ValueError(f"unexpected_source_pose_protocol:{candidate}")
        row.update(
            {
                "resolved_pose_path": str(path),
                "pose_sha256": observed_hash,
                "pose_evidence_source": resolved["source"],
                "pose_source_result": str(resolved.get("source_result", "")),
                "source_pose_protocol": "vina_7p3w_v1",
            }
        )
        rows.append(row)
    return pd.DataFrame(rows).sort_values("panel_order").reset_index(drop=True)


def _windows_path(path: Path) -> str:
    """Store shared registry paths in the repository host's canonical form."""
    resolved = str(path.resolve())
    if resolved.startswith("/mnt/") and len(resolved) > 6:
        drive = resolved[5].upper()
        tail = resolved[6:].replace("/", "\\")
        return f"{drive}:\\{tail}"
    return resolved


def _runtime_receptor_on_host(project: Path, protocol: dict[str, Any]) -> Path:
    value = str(protocol["receptor"]["prepared_runtime_path"])
    if os.name == "nt" and value.startswith("/mnt/"):
        return Path(value[5].upper() + ":/" + value[7:])
    return Path(value)


def prepare_registry(project: Path) -> dict[str, Any]:
    """Create one immutable shared-registry plan before the WSL worker starts."""
    project = project.resolve()
    output = project / "results/phase17_1"
    runtime = project / "workspace_local/phase17_1"
    record_path = runtime / "registry_plan.json"
    protocol = json.loads((output / f"{PROTOCOL_ID}.json").read_text(encoding="utf-8"))
    verify_protocol(protocol)
    plan = resolve_poses(project, build_cumulative_plan(project))
    if record_path.is_file():
        existing = json.loads(record_path.read_text(encoding="utf-8"))
        if existing.get("protocol_hash") != protocol["protocol_hash"]:
            raise ValueError("registry_plan_protocol_changed")
        if set(existing.get("jobs", {})) != set(plan["candidate_id"]):
            raise ValueError("registry_plan_candidate_set_changed")
        return existing

    state = State(project)
    state.project_id(PROJECT_ID)
    state.freeze_protocol(protocol)
    receptor = _runtime_receptor_on_host(project, protocol)
    if not receptor.is_file() or sha256(receptor) != protocol["receptor"]["prepared_sha256"]:
        raise ValueError("prepared_receptor_artifact_missing_or_changed")
    receptor_artifact = state.artifact(receptor)
    batch = state.batch(
        PROJECT_ID,
        {
            "phase": "17.1",
            "purpose": "gated_open_mmgbsa_qualification_and_expansion",
            "targets": [8, 30, 60],
            "training": False,
        },
    )
    jobs: dict[str, str] = {}
    for row in plan.to_dict("records"):
        state.candidate(PROJECT_ID, row["candidate_id"], row["canonical_smiles"])
        pose_artifact = state.artifact(Path(row["resolved_pose_path"]))
        command = {
            "action": "phase17_1_open_mmgbsa_execution",
            "stage": row["stage_added"],
            "panel_order": int(row["panel_order"]),
            "protocol_hash": protocol["protocol_hash"],
            "prepared_pose_hash": row["pose_sha256"],
            "prepared_input": True,
            "training": False,
        }
        jobs[row["candidate_id"]] = state.job(
            batch,
            PROJECT_ID,
            row["candidate_id"],
            "open_mmgbsa",
            PROTOCOL_ID,
            [receptor_artifact, pose_artifact],
            command,
        )
    record = {
        "created_at": utc_now(),
        "batch_id": batch,
        "protocol_id": PROTOCOL_ID,
        "protocol_hash": protocol["protocol_hash"],
        "candidate_count": len(jobs),
        "jobs": jobs,
    }
    atomic_json(record_path, record)
    return record


def result_row(candidate: dict[str, Any], result: dict[str, Any] | None) -> dict[str, Any]:
    result = result or {}
    analysis = result.get("analysis", {})
    sampling = result.get("sampling", {})
    return {
        "panel_order": candidate["panel_order"],
        "stage_added": candidate["stage_added"],
        "candidate_id": candidate["candidate_id"],
        "candidate_origin": candidate["candidate_origin"],
        "selection_class": candidate["selection_class"],
        "protocol_id": result.get("protocol_id", PROTOCOL_ID),
        "protocol_hash": result.get("protocol_hash", ""),
        "status": result.get("status", "planned"),
        "cached": bool(result.get("cached", False)),
        "failure_stage": result.get("failure_stage", ""),
        "failure_reason": result.get("failure_reason", ""),
        "runtime_seconds": result.get("elapsed_seconds"),
        "parameterization_success": bool(result.get("identity")),
        "sampling_success": bool(sampling.get("finite_final_energy", False)),
        "trajectory_integrity": analysis.get("trajectory_finite", False),
        "frame_count": analysis.get("analyzed_frames", 0),
        "finite_result": isinstance(analysis.get("open_mmgbsa_deltaG"), (int, float))
        and math.isfinite(analysis["open_mmgbsa_deltaG"]),
        "open_mmgbsa_deltaG": analysis.get("open_mmgbsa_deltaG"),
        "open_mmgbsa_sd": analysis.get("open_mmgbsa_sd"),
        "deltaG_unit": analysis.get("unit", "kcal/mol"),
        "protein_ca_rmsd_mean_nm": analysis.get("protein_ca_rmsd_mean_nm"),
        "ligand_heavy_rmsd_mean_nm": analysis.get("ligand_heavy_rmsd_mean_nm"),
        "qc_status": result.get("qc_status", "not_run"),
        "training": False,
        "activity_label": "not_applicable",
    }


def systematic_corruption(rows: list[dict[str, Any]]) -> dict[str, Any]:
    failed = [row for row in rows if row["status"] == "failed"]
    stages = Counter(row["failure_stage"] for row in failed if row["failure_stage"])
    corruption_terms = ("nonfinite", "identity_mismatch", "frame_count", "corrupt")
    corrupt = [row for row in failed if any(term in row["failure_reason"].lower() for term in corruption_terms)]
    threshold = max(2, math.ceil(len(rows) * 0.20))
    systematic_stage = next((stage for stage, count in stages.items() if count >= threshold), "")
    return {
        "detected": bool(len(corrupt) >= threshold or systematic_stage),
        "detection_threshold": threshold,
        "same_failure_stage": systematic_stage,
        "corruption_failure_count": len(corrupt),
        "failure_stage_counts": dict(stages),
    }


class Engine:
    def __init__(self, project: Path, retry_failed: bool = False):
        self.project = project.resolve()
        self.output = self.project / "results/phase17_1"
        self.runtime = self.project / "workspace_local/phase17_1"
        self.requests = self.runtime / "requests"
        self.jobs = self.runtime / "jobs"
        self.checkpoint_path = self.runtime / "checkpoint.json"
        self.retry_failed = retry_failed
        self.protocol = json.loads((self.output / f"{PROTOCOL_ID}.json").read_text(encoding="utf-8"))
        verify_protocol(self.protocol)
        self.model_hashes = frozen_model_hashes(self.project)
        self.plan = resolve_poses(self.project, build_cumulative_plan(self.project))
        self.output.mkdir(parents=True, exist_ok=True)
        self.requests.mkdir(parents=True, exist_ok=True)
        self.jobs.mkdir(parents=True, exist_ok=True)
        atomic_csv(self.output / "candidate_plan.csv", self.plan)
        registry_path = self.runtime / "registry_plan.json"
        if not registry_path.is_file():
            raise RuntimeError("shared_registry_plan_missing_run_registry_plan_first")
        self.registry = json.loads(registry_path.read_text(encoding="utf-8"))
        if self.registry.get("protocol_hash") != self.protocol["protocol_hash"]:
            raise ValueError("shared_registry_protocol_hash_mismatch")

    def _registry_running(self, candidate_id: str, work: Path) -> None:
        job_id = self.registry["jobs"][candidate_id]
        with sqlite3.connect(self.project / "workspace_local/workspace.sqlite3", timeout=60) as db:
            row = db.execute(
                "SELECT status,attempt FROM calculation_job WHERE job_id=?", (job_id,)
            ).fetchone()
            if not row:
                raise ValueError(f"shared_registry_job_missing:{candidate_id}")
            if row[0] == "completed":
                return
            if row[0] == "failed" and not self.retry_failed:
                return
            db.execute(
                """UPDATE calculation_job SET status='running',started_at=?,completed_at=NULL,
                   return_code=NULL,stdout_path=?,stderr_path=?,reason='',attempt=? WHERE job_id=?""",
                (
                    now(),
                    _windows_path(work / "worker.stdout.log"),
                    _windows_path(work / "worker.stderr.log"),
                    int(row[1] or 0) + 1,
                    job_id,
                ),
            )

    def _archive_result(self, result_path: Path) -> dict[str, Any]:
        token = sha256(result_path)
        destination = self.project / "workspace_local/artifacts" / token / result_path.name
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.is_file() and sha256(destination) != token:
            raise ValueError("shared_registry_artifact_tampered")
        if not destination.is_file():
            shutil.copyfile(result_path, destination)
        artifact = {
            "artifact_hash": token,
            "path": _windows_path(destination),
            "original_path": _windows_path(result_path),
        }
        with sqlite3.connect(self.project / "workspace_local/workspace.sqlite3", timeout=60) as db:
            db.execute(
                "INSERT OR IGNORE INTO calculation_artifact VALUES (?,?,?,?,?)",
                (token, artifact["path"], result_path.stat().st_size, artifact["original_path"], now()),
            )
        return artifact

    def _registry_terminal(self, candidate_id: str, result: dict[str, Any], work: Path) -> None:
        job_id = self.registry["jobs"][candidate_id]
        db_path = self.project / "workspace_local/workspace.sqlite3"
        if result.get("status") != "success":
            with sqlite3.connect(db_path, timeout=60) as db:
                db.execute(
                    """UPDATE calculation_job SET status='failed',completed_at=?,return_code=1,
                       reason=? WHERE job_id=? AND status!='completed'""",
                    (now(), result.get("failure_reason", "worker_failed"), job_id),
                )
            return
        analysis = result.get("analysis", {})
        values = [analysis.get("open_mmgbsa_deltaG"), analysis.get("open_mmgbsa_sd")]
        if not all(isinstance(value, (int, float)) and math.isfinite(value) for value in values):
            raise ValueError(f"nonfinite_result_cannot_enter_registry:{candidate_id}")
        result_path = work / "result.json"
        artifact = self._archive_result(result_path)
        with sqlite3.connect(db_path, timeout=60) as db:
            db.execute(
                """UPDATE calculation_job SET status='completed',completed_at=?,return_code=0,
                   output_artifacts=?,reason='' WHERE job_id=?""",
                (now(), encode([artifact]), job_id),
            )
            for evidence_type, value in [
                ("open_mmgbsa_deltaG", values[0]),
                ("open_mmgbsa_uncertainty", values[1]),
            ]:
                key = [PROJECT_ID, candidate_id, evidence_type, PROTOCOL_ID, job_id, artifact["artifact_hash"]]
                evidence_id = "ev_" + digest(key)[:24]
                provenance = {
                    "origin": "tool_execution",
                    "phase": "17.1",
                    "scientific_scope": "comparative_high_cost_computational_evidence_not_activity",
                    "protocol_hash": self.protocol["protocol_hash"],
                    "source_pose_protocol": "vina_7p3w_v1",
                    "training": False,
                }
                db.execute(
                    """INSERT OR IGNORE INTO evidence VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        evidence_id,
                        PROJECT_ID,
                        candidate_id,
                        evidence_type,
                        encode(value),
                        None,
                        "kcal/mol",
                        PROTOCOL_ID,
                        "OpenMM 8.6.0 + gmx_MMPBSA 1.6.5",
                        job_id,
                        artifact["artifact_hash"],
                        now(),
                        encode(provenance),
                    ),
                )

    def checkpoint(self) -> dict[str, Any]:
        if self.checkpoint_path.is_file():
            return json.loads(self.checkpoint_path.read_text(encoding="utf-8"))
        value = {
            "phase": "17.1",
            "protocol_id": PROTOCOL_ID,
            "protocol_hash": self.protocol["protocol_hash"],
            "status": "running",
            "current_stage": "qualification",
            "started_at": utc_now(),
            "updated_at": utc_now(),
            "gates": {},
            "model_hash_count": len(self.model_hashes),
            "no_simulated_results": True,
            "training_performed": False,
        }
        atomic_json(self.checkpoint_path, value)
        return value

    def save_checkpoint(self, value: dict[str, Any]) -> None:
        value["updated_at"] = utc_now()
        atomic_json(self.checkpoint_path, value)

    def request_for(self, row: dict[str, Any]) -> Path:
        request = {
            "candidate_id": row["candidate_id"],
            "canonical_smiles": row["canonical_smiles"],
            "candidate_origin": row["candidate_origin"],
            "selection_class": row["selection_class"],
            "pose_path": row["resolved_pose_path"],
            "pose_sha256": row["pose_sha256"],
            "receptor_path": self.protocol["receptor"]["prepared_runtime_path"],
            "protocol": self.protocol,
            "evidence_role": "comparative_high_cost_computational_evidence",
            "training": False,
        }
        path = self.requests / f"{row['candidate_id']}.json"
        if path.is_file():
            old = json.loads(path.read_text(encoding="utf-8"))
            if stable_hash(old) != stable_hash(request):
                raise ValueError(f"immutable_candidate_request_changed:{row['candidate_id']}")
        else:
            atomic_json(path, request)
        return path

    def execute(self, row: dict[str, Any]) -> dict[str, Any]:
        candidate = row["candidate_id"]
        work = self.jobs / candidate
        result_path = work / "result.json"
        if result_path.is_file():
            existing = json.loads(result_path.read_text(encoding="utf-8"))
            if existing.get("status") == "success":
                return {**existing, "cached": True}
            if existing.get("status") == "failed" and not self.retry_failed:
                return existing
        request = self.request_for(row)
        command = [
            sys.executable,
            "-m",
            "src.phase17_1.worker",
            "--request",
            str(request),
            "--output",
            str(work),
        ]
        manifest = {
            "argv": command,
            "cwd": str(self.project),
            "protocol_id": PROTOCOL_ID,
            "protocol_hash": self.protocol["protocol_hash"],
            "created_at": utc_now(),
        }
        self._registry_running(candidate, work)
        atomic_json(work / "command_manifest.json", manifest)
        completed = subprocess.run(
            command,
            cwd=self.project,
            text=True,
            capture_output=True,
            check=False,
        )
        (work / "worker.stdout.log").write_text(completed.stdout, encoding="utf-8")
        (work / "worker.stderr.log").write_text(completed.stderr, encoding="utf-8")
        if result_path.is_file():
            result = json.loads(result_path.read_text(encoding="utf-8"))
            self._registry_terminal(candidate, result, work)
            return result
        failure = {
            "candidate_id": candidate,
            "protocol_id": PROTOCOL_ID,
            "protocol_hash": self.protocol["protocol_hash"],
            "status": "failed",
            "cached": False,
            "completed_at": utc_now(),
            "failure_stage": "worker_process",
            "failure_reason": f"worker_returned_without_result:return_code={completed.returncode}",
            "qc_status": "failed",
            "training": False,
            "biological_activity_claim": False,
        }
        atomic_json(result_path, failure)
        self._registry_terminal(candidate, failure, work)
        return failure

    def stage_results(self, target: int) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for candidate in self.plan.iloc[:target].to_dict("records"):
            result_path = self.jobs / candidate["candidate_id"] / "result.json"
            result = json.loads(result_path.read_text(encoding="utf-8")) if result_path.is_file() else None
            rows.append(result_row(candidate, result))
        return rows

    def gate(self, name: str, target: int, rows: list[dict[str, Any]]) -> dict[str, Any]:
        success = sum(row["status"] == "success" and row["finite_result"] for row in rows)
        failed = sum(row["status"] == "failed" for row in rows)
        pending = target - success - failed
        corruption = systematic_corruption(rows)
        minimum = 7 if name == "qualification" else 27 if name == "pilot30" else None
        passed = pending == 0 and (minimum is None or success >= minimum) and not corruption["detected"]
        return {
            "stage": name,
            "cumulative_target": target,
            "success": success,
            "failed": failed,
            "pending": pending,
            "minimum_success": minimum,
            "systematic_corruption": corruption,
            "passed": passed,
            "evaluated_at": utc_now(),
        }

    def export_stage(self, name: str, rows: list[dict[str, Any]]) -> None:
        filename = {
            "qualification": "qualification_results.csv",
            "pilot30": "pilot30_results.csv",
            "expanded60": "expanded60_results.csv",
        }[name]
        atomic_csv(self.output / filename, pd.DataFrame(rows))

    def run(self) -> dict[str, Any]:
        checkpoint = self.checkpoint()
        for stage_name, target in STAGES:
            checkpoint["current_stage"] = stage_name
            self.save_checkpoint(checkpoint)
            for row in self.plan.iloc[:target].to_dict("records"):
                result_path = self.jobs / row["candidate_id"] / "result.json"
                if result_path.is_file():
                    existing = json.loads(result_path.read_text(encoding="utf-8"))
                    if existing.get("status") == "success":
                        self._registry_terminal(row["candidate_id"], existing, result_path.parent)
                        continue
                    if existing.get("status") == "failed" and not self.retry_failed:
                        self._registry_terminal(row["candidate_id"], existing, result_path.parent)
                        continue
                checkpoint["current_candidate"] = row["candidate_id"]
                checkpoint["current_panel_order"] = int(row["panel_order"])
                self.save_checkpoint(checkpoint)
                self.execute(row)
                rows = self.stage_results(target)
                checkpoint["terminal_in_current_stage"] = sum(
                    item["status"] in {"success", "failed"} for item in rows
                )
                self.save_checkpoint(checkpoint)
            rows = self.stage_results(target)
            self.export_stage(stage_name, rows)
            gate = self.gate(stage_name, target, rows)
            checkpoint["gates"][stage_name] = gate
            self.save_checkpoint(checkpoint)
            policy = execution_policy(self.project)
            if stage_name == "pilot30" and not policy.get("auto_expand_to_60", False):
                analysis: dict[str, Any]
                if policy.get("run_post_pilot_analysis", True):
                    try:
                        from src.phase17_1.post_pilot import run_post_pilot_analysis

                        analysis = run_post_pilot_analysis(self.project)
                    except Exception as exc:
                        analysis = {
                            "status": "failed",
                            "reason": f"{type(exc).__name__}:{exc}",
                        }
                else:
                    analysis = {"status": "not_requested"}
                checkpoint.update(
                    {
                        "status": "awaiting_optional_extension_confirmation",
                        "current_stage": "pilot30_complete",
                        "current_candidate": "",
                        "automatic_expansion_stopped_at": 30,
                        "optional_extension_target": policy.get("optional_extension_target", 60),
                        "pilot30_gate_passed": gate["passed"],
                        "post_pilot_analysis": analysis,
                        "completed_at": utc_now(),
                    }
                )
                self.save_checkpoint(checkpoint)
                return checkpoint
            if not gate["passed"]:
                checkpoint.update(
                    {
                        "status": "stopped_at_gate",
                        "stop_reason": f"{stage_name}_gate_not_passed",
                        "completed_at": utc_now(),
                    }
                )
                self.save_checkpoint(checkpoint)
                return checkpoint
        after = frozen_model_hashes(self.project)
        checkpoint.update(
            {
                "status": "completed",
                "current_stage": "completed",
                "current_candidate": "",
                "completed_at": utc_now(),
                "model_hashes_unchanged": after == self.model_hashes,
                "model_hash_count": len(after),
            }
        )
        self.save_checkpoint(checkpoint)
        final_rows = self.stage_results(60)
        atomic_csv(self.output / "open_mmgbsa_results.csv", pd.DataFrame(final_rows))
        atomic_json(
            self.output / "phase17_1_execution_summary.json",
            {
                **checkpoint,
                "real_high_cost_evidence_count": sum(row["status"] == "success" for row in final_rows),
                "failed_count": sum(row["status"] == "failed" for row in final_rows),
                "interpretation": "comparative high-cost computational evidence; not an activity label",
            },
        )
        return checkpoint


def status(project: Path) -> dict[str, Any]:
    runtime = project / "workspace_local/phase17_1"
    checkpoint_path = runtime / "checkpoint.json"
    checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8")) if checkpoint_path.is_file() else {
        "status": "not_started"
    }
    counts = Counter()
    for result_path in (runtime / "jobs").glob("*/result.json"):
        try:
            counts[json.loads(result_path.read_text(encoding="utf-8")).get("status", "unknown")] += 1
        except Exception:
            counts["unreadable"] += 1
    return {"checkpoint": checkpoint, "terminal_counts": dict(counts)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["run", "status", "plan", "registry-plan"])
    parser.add_argument("--project", type=Path, default=Path.cwd())
    parser.add_argument("--retry-failed", action="store_true")
    args = parser.parse_args()
    if args.command == "status":
        print(json.dumps(status(args.project.resolve()), ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    if args.command == "registry-plan":
        print(json.dumps(prepare_registry(args.project.resolve()), ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    engine = Engine(args.project, retry_failed=args.retry_failed)
    if args.command == "plan":
        print(engine.plan[["panel_order", "stage_added", "candidate_id", "selection_class"]].to_csv(index=False))
        return 0
    result = engine.run()
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result.get("status") == "completed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
