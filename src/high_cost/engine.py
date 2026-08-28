from __future__ import annotations

import csv
import hashlib
import importlib.metadata
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import pandas as pd


PROTOCOL_ID = "open_mmgbsa_7p3w_v1"
BLOCK_REASON = (
    "complete_open_mmgbsa_route_unavailable: OpenMM is installed in the isolated "
    "Phase 17 environment, but no validated ligand-parameterization plus MM/GBSA "
    "analysis chain is available (OpenFF Toolkit/AmberTools and ParmEd or "
    "gmx_MMPBSA are unavailable)."
)


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def stable_hash(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


def write_json(path: Path, payload: Any) -> None:
    atomic_text(path, json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def write_csv(path: Path, frame: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    os.close(fd)
    try:
        frame.to_csv(tmp_name, index=False, encoding="utf-8")
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


def local_distributions(deps: Path) -> dict[str, str]:
    found: dict[str, str] = {}
    if not deps.is_dir():
        return found
    for distribution in importlib.metadata.distributions(path=[str(deps)]):
        name = str(distribution.metadata.get("Name", "")).lower().replace("-", "_")
        if name:
            found[name] = distribution.version
    return found


def _which(names: Iterable[str]) -> str | None:
    for name in names:
        value = shutil.which(name)
        if value:
            return str(Path(value).resolve())
    return None


def _version(executable: str | None, args: list[str]) -> tuple[str, str]:
    if not executable:
        return "unknown", "not_found"
    try:
        result = subprocess.run(
            [executable, *args], capture_output=True, text=True, timeout=20, check=False
        )
        text = (result.stdout + "\n" + result.stderr).strip().splitlines()
        return (text[0][:300] if text else "unknown"), f"return_code_{result.returncode}"
    except Exception as exc:  # capability audit must not crash the phase
        return "unknown", f"probe_error:{type(exc).__name__}:{exc}"


def _python_probe(python: Path, deps: Path, statement: str) -> dict[str, Any]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(deps) + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    try:
        result = subprocess.run(
            [str(python), "-c", statement], capture_output=True, text=True,
            timeout=30, check=False, env=env
        )
        return {
            "return_code": result.returncode,
            "stdout": result.stdout.strip()[:1000],
            "stderr": result.stderr.strip()[:1000],
            "passed": result.returncode == 0,
        }
    except Exception as exc:
        return {"return_code": None, "stdout": "", "stderr": str(exc), "passed": False}


def audit_backends(project: Path) -> dict[str, Any]:
    deps = project / "workspace_local/phase17/deps"
    python = project / ".venv/Scripts/python.exe"
    distributions = local_distributions(deps)
    openmm_probe = _python_probe(
        python, deps,
        "import openmm; print(openmm.__version__); print(','.join(openmm.Platform.getPlatform(i).getName() for i in range(openmm.Platform.getNumPlatforms())))",
    )
    forcefields_probe = _python_probe(
        python, deps,
        "import openmmforcefields; print(getattr(openmmforcefields,'__version__','import_ok'))",
    )
    rdkit_probe = _python_probe(
        python, Path("__no_phase17_deps__"),
        "import rdkit; print(rdkit.__version__)",
    )

    exe_specs = {
        "gromacs": (["gmx", "gmx.exe", "gmx_mpi", "gmx_mpi.exe"], ["--version"]),
        "gmx_MMPBSA": (["gmx_MMPBSA", "gmx_MMPBSA.exe"], ["--version"]),
        "ambertools_antechamber": (["antechamber", "antechamber.exe"], ["-h"]),
        "ambertools_tleap": (["tleap", "tleap.exe"], ["-h"]),
        "ambertools_sqm": (["sqm", "sqm.exe"], ["-h"]),
        "acpype": (["acpype", "acpype.exe"], ["--version"]),
    }
    backends: dict[str, Any] = {}
    for tool_id, (names, args) in exe_specs.items():
        executable = _which(names)
        version, probe_status = _version(executable, args)
        backends[tool_id] = {
            "installed": bool(executable), "executable_path": executable, "version": version,
            "dependencies": [], "usable": bool(executable),
            "blocking_reason": "" if executable else "executable_not_found", "probe": probe_status,
        }

    openmm_installed = "openmm" in distributions and openmm_probe["passed"]
    backends["openmm"] = {
        "installed": openmm_installed,
        "executable_path": str(python) if openmm_installed else None,
        "version": distributions.get("openmm", "unknown"),
        "dependencies": ["validated ligand force field", "MM/GBSA analysis implementation"],
        "usable": openmm_installed,
        "blocking_reason": "" if openmm_installed else "python_import_failed",
        "probe": openmm_probe,
        "installation_scope": "workspace_local/phase17/deps",
    }
    backends["openmmforcefields"] = {
        "installed": "openmmforcefields" in distributions and forcefields_probe["passed"],
        "executable_path": str(python),
        "version": distributions.get("openmmforcefields", "unknown"),
        "dependencies": ["OpenFF Toolkit or AmberTools for small-molecule parameterization"],
        "usable": False,
        "blocking_reason": "OpenFF Toolkit and AmberTools are unavailable",
        "probe": forcefields_probe,
        "installation_scope": "workspace_local/phase17/deps",
    }
    backends["parmed"] = {
        "installed": "parmed" in distributions, "executable_path": None,
        "version": distributions.get("parmed", "unknown"), "dependencies": [], "usable": False,
        "blocking_reason": "installation requires an unavailable Microsoft C++ build toolchain",
    }
    backends["openff_toolkit"] = {
        "installed": "openff_toolkit" in distributions, "executable_path": None,
        "version": distributions.get("openff_toolkit", "unknown"), "dependencies": [], "usable": False,
        "blocking_reason": "no compatible distribution is available from the configured package index",
    }
    backends["rdkit"] = {
        "installed": rdkit_probe["passed"], "executable_path": str(python),
        "version": rdkit_probe["stdout"].splitlines()[0] if rdkit_probe["stdout"] else "unknown",
        "dependencies": [], "usable": rdkit_probe["passed"],
        "blocking_reason": "" if rdkit_probe["passed"] else "python_import_failed", "probe": rdkit_probe,
    }

    system_caps_path = project / "results/system_capabilities.json"
    prime = {}
    if system_caps_path.is_file():
        prime = json.loads(system_caps_path.read_text(encoding="utf-8")).get("tools", {}).get("prime_mmgbsa", {})
    backends["schrodinger_prime_mmgbsa"] = {
        "installed": bool(prime.get("executable_path")),
        "executable_path": prime.get("executable_path"),
        "version": prime.get("tool_version", "unknown"),
        "dependencies": ["Schrödinger license entitlement"],
        "usable": False,
        "status": "license_unavailable",
        "blocking_reason": "existing audited license checkout failed; not retried in Phase 17",
        "prior_audit": str(system_caps_path.relative_to(project)) if system_caps_path.is_file() else None,
    }

    route_usable = bool(
        backends["gromacs"]["usable"]
        and backends["gmx_MMPBSA"]["usable"]
        and (backends["ambertools_antechamber"]["usable"] or backends["openff_toolkit"]["usable"])
    )
    # A future OpenMM implementation must pass all three capability layers; OpenMM alone is not MM/GBSA.
    openmm_route_usable = bool(
        backends["openmm"]["usable"]
        and (backends["ambertools_antechamber"]["usable"] or backends["openff_toolkit"]["usable"])
        and backends["parmed"]["usable"]
    )
    return {
        "created_at": now(),
        "audit_scope": "Phase 17 project-local and PATH capability audit",
        "backends": backends,
        "installation_attempts": [
            {"packages": ["openmm", "parmed"], "result": "failed_atomically", "reason": "ParmEd native extension requires Microsoft Visual C++ 14+"},
            {"packages": ["openmm"], "result": "installed_project_local", "version": distributions.get("openmm", "unknown")},
            {"packages": ["openmmforcefields"], "result": "installed_project_local", "version": distributions.get("openmmforcefields", "unknown")},
            {"packages": ["openff-toolkit"], "result": "unavailable", "reason": "no compatible package-index distribution"},
        ],
        "routes": {
            "gromacs_gmx_mmpbsa": {"usable": route_usable, "blocking_reason": "" if route_usable else BLOCK_REASON},
            "openmm_mmgbsa": {"usable": openmm_route_usable, "blocking_reason": "" if openmm_route_usable else BLOCK_REASON},
            "prime_mmgbsa": {"usable": False, "blocking_reason": "license_unavailable"},
        },
        "selected_route": None,
        "complete_open_source_route_usable": route_usable or openmm_route_usable,
        "scientific_gate": "blocked" if not (route_usable or openmm_route_usable) else "ready_for_qualification",
        "no_simulated_results": True,
    }


def build_candidate_pool(project: Path) -> pd.DataFrame:
    historical = pd.read_csv(project / "results/phase15/acquisition_panel_v1.csv", keep_default_na=False)
    generated = pd.read_csv(project / "results/phase16/generated_acquisition_panel_v1.csv", keep_default_na=False)
    h = pd.DataFrame({
        "candidate_id": historical["canonical_id"],
        "candidate_origin": "phase15_historical_htvs",
        "parent_id": "",
        "canonical_smiles": historical["canonical_smiles"],
        "scaffold": historical["scaffold"],
        "cluster": historical["chemical_space_cluster"],
        "selection_class": historical["acquisition_class"],
        "glide_score": pd.to_numeric(historical.get("glide_docking_score", pd.Series([None] * len(historical))), errors="coerce"),
        "glide_rank": historical["glide_rank"],
        "vina_score": pd.NA,
        "vina_rank": historical["vina_rank"],
        "acquisition_score": historical["hybrid_score"],
        "protocol_disagreement": historical["protocol_disagreement"],
        "novelty": historical["chemical_space_uncertainty"],
        "tractability": pd.NA,
        "pose_path": "",
    })
    # Resolve actual Vina scores from the Phase 14 ranking, without changing Phase 15.
    ranking = pd.read_csv(project / "results/phase14/full_library_vina_ranking.csv", keep_default_na=False)
    vina_score_col = "vina_affinity" if "vina_affinity" in ranking.columns else "score"
    h = h.merge(ranking[["canonical_id", vina_score_col]].rename(columns={"canonical_id": "candidate_id", vina_score_col: "_vina"}), on="candidate_id", how="left")
    h["vina_score"] = h["_vina"]; h = h.drop(columns=["_vina"])

    g = pd.DataFrame({
        "candidate_id": generated["generated_candidate_id"],
        "candidate_origin": "phase16_generated",
        "parent_id": generated["parent_candidate_id"],
        "canonical_smiles": generated["canonical_smiles"],
        "scaffold": generated["murcko_scaffold"],
        "cluster": "generated",
        "selection_class": "generated_acquisition",
        "glide_score": pd.NA,
        "glide_rank": pd.NA,
        "vina_score": generated["vina_affinity"],
        "vina_rank": generated["vina_rank_within_generated_pool"],
        "acquisition_score": generated["generated_candidate_score"],
        "protocol_disagreement": pd.NA,
        "novelty": generated["novelty_vs_htvs1633"],
        "tractability": generated["property_tractability"],
        "pose_path": generated["pose_path"],
    })
    pool = pd.concat([h, g], ignore_index=True)
    if pool["candidate_id"].duplicated().any():
        raise ValueError("phase17_pool_candidate_identity_collision")
    return pool


IN2_SMILES = "C[NH+](C)Cc1ccc(C[NH2+]Cc2cc3ccccc3nc2SCc2ccccc2)cc1"


def qualification_set(pool: pd.DataFrame) -> pd.DataFrame:
    selected: list[dict[str, Any]] = [{
        "candidate_id": "ATP-REF-IN2", "candidate_origin": "internal_reference",
        "parent_id": "", "canonical_smiles": IN2_SMILES, "scaffold": "",
        "cluster": "reference", "selection_class": "reference_IN2", "glide_score": pd.NA,
        "glide_rank": pd.NA, "vina_score": -8.212, "vina_rank": pd.NA,
        "acquisition_score": pd.NA, "protocol_disagreement": pd.NA,
        "novelty": pd.NA, "tractability": pd.NA,
        "pose_path": "results/phase13/poses/ATP-REF-IN2_vina_7p3w_v1.pdbqt",
    }]
    historical = pool.loc[pool["candidate_origin"].eq("phase15_historical_htvs")]
    generated = pool.loc[pool["candidate_origin"].eq("phase16_generated")].copy()
    for class_name, count in [("multi_protocol_strong", 2), ("extreme_disagreement", 2), ("medium_controls", 1)]:
        rows = historical.loc[historical["selection_class"].eq(class_name)].head(count)
        if len(rows) != count:
            raise ValueError(f"insufficient_qualification_class:{class_name}:{len(rows)}/{count}")
        selected.extend(rows.to_dict("records"))
    high = generated.sort_values(["acquisition_score", "candidate_id"], ascending=[False, True]).iloc[0]
    remaining = generated.loc[~generated["candidate_id"].eq(high["candidate_id"])].copy()
    diverse = remaining.sort_values(["novelty", "tractability", "candidate_id"], ascending=[False, False, True]).iloc[0]
    high_row = high.to_dict(); high_row["selection_class"] = "generated_high_ranking"
    diverse_row = diverse.to_dict(); diverse_row["selection_class"] = "generated_diverse_novel"
    selected.extend([high_row, diverse_row])
    result = pd.DataFrame(selected)
    if len(result) != 8 or result["candidate_id"].nunique() != 8:
        raise ValueError("qualification_set_must_contain_8_unique_candidates")
    result.insert(0, "qualification_order", range(1, 9))
    return result


def blocked_protocol(project: Path, backend: dict[str, Any]) -> dict[str, Any]:
    vina_dir = project / "configs/projects/ab_atp_synthase/vina_7p3w_v1"
    receptor_manifest = json.loads((vina_dir / "receptor_manifest.json").read_text(encoding="utf-8"))
    protocol: dict[str, Any] = {
        "protocol_id": PROTOCOL_ID,
        "status": "blocked_before_qualification",
        "frozen_for_batch_use": False,
        "scientific_parameters_established": False,
        "blocking_reason": BLOCK_REASON,
        "source_pose_protocol": "vina_7p3w_v1",
        "source_pose_protocol_hash": sha256(vina_dir / "vina_protocol.json"),
        "receptor_source": receptor_manifest,
        "receptor_preparation": "unresolved_for_open_mmgbsa; no run performed",
        "protonation_assumptions": "unresolved_for_open_mmgbsa; no run performed",
        "ligand_preparation": "unresolved_for_open_mmgbsa; no run performed",
        "ligand_charge_model": "unresolved",
        "force_field": "unresolved",
        "water_model": "unresolved",
        "ion_treatment": "unresolved",
        "minimization": "unresolved",
        "equilibration": "unresolved",
        "production_sampling": "unresolved",
        "frame_extraction": "unresolved",
        "gb_pb_model": "unresolved",
        "entropy_treatment": "unresolved",
        "tool_versions": {key: value.get("version", "unknown") for key, value in backend["backends"].items()},
        "random_seed": "unresolved",
        "output_field": "open_mmgbsa_deltaG",
        "forbidden_aliases": ["historical_prime_mmgbsa", "prime_mmgbsa"],
        "interpretation": "No numerical result exists; this manifest records a failed pre-qualification capability gate.",
    }
    protocol["protocol_hash"] = stable_hash(protocol)
    return protocol


RESULT_COLUMNS = [
    "job_id", "candidate_id", "candidate_origin", "protocol_id", "protocol_hash", "status",
    "attempt", "start_time", "end_time", "tool_version", "input_hash", "output_hash",
    "failure_stage", "failure_reason", "parameterization_success", "minimization_success",
    "sampling_success", "trajectory_integrity", "frame_count", "energy_parsing",
    "finite_result", "runtime_seconds", "open_mmgbsa_deltaG", "deltaG_unit", "qc_status",
]


def block_qualification_jobs(qualification: pd.DataFrame, protocol: dict[str, Any]) -> pd.DataFrame:
    completed = now()
    rows = []
    for row in qualification.to_dict("records"):
        input_payload = {
            "candidate_id": row["candidate_id"], "canonical_smiles": row["canonical_smiles"],
            "protocol_id": PROTOCOL_ID, "pose_path": row.get("pose_path", ""),
        }
        rows.append({
            "job_id": "phase17_qual_" + hashlib.sha256(row["candidate_id"].encode()).hexdigest()[:16],
            "candidate_id": row["candidate_id"], "candidate_origin": row["candidate_origin"],
            "protocol_id": PROTOCOL_ID, "protocol_hash": protocol["protocol_hash"],
            "status": "blocked", "attempt": 0, "start_time": "", "end_time": completed,
            "tool_version": "not_available", "input_hash": stable_hash(input_payload), "output_hash": "",
            "failure_stage": "backend_capability_gate", "failure_reason": BLOCK_REASON,
            "parameterization_success": False, "minimization_success": False,
            "sampling_success": False, "trajectory_integrity": "not_run", "frame_count": 0,
            "energy_parsing": "not_run", "finite_result": False, "runtime_seconds": 0.0,
            "open_mmgbsa_deltaG": pd.NA, "deltaG_unit": "kcal/mol", "qc_status": "not_run",
        })
    return pd.DataFrame(rows, columns=RESULT_COLUMNS)


def empty_table(columns: list[str], status: str, reason: str) -> pd.DataFrame:
    row = {column: "" for column in columns}
    if "status" in row:
        row["status"] = status
    if "reason" in row:
        row["reason"] = reason
    return pd.DataFrame([row], columns=columns)


def save_gate_figures(output: Path, backend: dict[str, Any], results: pd.DataFrame) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    figures = output / "figures"; figures.mkdir(parents=True, exist_ok=True)
    names = ["GROMACS route", "OpenMM route", "Prime route"]
    values = [
        int(backend["routes"]["gromacs_gmx_mmpbsa"]["usable"]),
        int(backend["routes"]["openmm_mmgbsa"]["usable"]),
        int(backend["routes"]["prime_mmgbsa"]["usable"]),
    ]
    fig, ax = plt.subplots(figsize=(7, 4)); ax.bar(names, values, color=["#4C78A8", "#F58518", "#999999"])
    ax.set_ylim(0, 1.15); ax.set_ylabel("Usable end-to-end route (1=yes)")
    ax.set_title("Phase 17 high-cost backend readiness")
    fig.tight_layout(); fig.savefig(figures / "backend_route_readiness.png", dpi=180); plt.close(fig)

    counts = results["status"].value_counts().reindex(["success", "failed", "blocked"], fill_value=0)
    fig, ax = plt.subplots(figsize=(6, 4)); ax.bar(counts.index, counts.values, color=["#54A24B", "#E45756", "#B279A2"])
    ax.set_ylabel("Qualification candidates"); ax.set_title("Qualification gate: real terminal states")
    for i, value in enumerate(counts.values): ax.text(i, value + 0.08, str(int(value)), ha="center")
    ax.set_ylim(0, max(8.8, counts.max() + 1)); fig.tight_layout()
    fig.savefig(figures / "qualification_gate.png", dpi=180); plt.close(fig)


@dataclass
class Phase17Engine:
    project: Path

    def __post_init__(self) -> None:
        self.project = self.project.resolve()
        self.output = self.project / "results/phase17"
        self.runtime = self.project / "workspace_local/phase17"
        self.output.mkdir(parents=True, exist_ok=True); self.runtime.mkdir(parents=True, exist_ok=True)

    def run(self) -> dict[str, Any]:
        timer = time.perf_counter()
        started = now()
        before = json.loads((self.project / "results/phase14/model_hashes_after.json").read_text(encoding="utf-8"))
        write_json(self.output / "model_hashes_before.json", before)

        backend = audit_backends(self.project)
        write_json(self.output / "high_cost_backend_status.json", backend)
        pool = build_candidate_pool(self.project)
        write_csv(self.output / "phase17_candidate_pool.csv", pool)
        qualification = qualification_set(pool)
        write_csv(self.output / "phase17_high_cost_panel.csv", qualification)
        protocol = blocked_protocol(self.project, backend)
        write_json(self.output / "open_mmgbsa_protocol.json", protocol)

        if backend["complete_open_source_route_usable"]:
            raise RuntimeError(
                "A complete route was detected, but no scientifically reviewed execution adapter is present. "
                "This is a fatal pre-qualification implementation gate; no calculation was started."
            )

        results = block_qualification_jobs(qualification, protocol)
        write_csv(self.output / "open_mmgbsa_results.csv", results)
        write_csv(self.runtime / "jobs.csv", results)
        gate = {
            "stage": "qualification", "requested": 8, "success": 0, "failed": 0, "blocked": 8,
            "success_threshold": 7, "qualified": False, "batch30_started": False,
            "batch60_started": False, "reason": BLOCK_REASON, "checked_at": now(),
        }
        write_json(self.runtime / "checkpoint.json", gate)
        write_json(self.output / "qualification_gate.json", gate)

        reason = "not_available: qualification gate did not run because no complete backend route was usable"
        write_csv(self.output / "protocol_comparison.csv", empty_table(
            ["protocol_a", "protocol_b", "n", "spearman", "kendall", "top5_overlap", "top10_overlap", "top20_overlap", "status", "reason"],
            "not_available", reason,
        ))
        write_csv(self.output / "three_protocol_robustness.csv", empty_table(
            ["candidate_id", "glide_rank", "vina_rank", "open_mmgbsa_rank", "protocol_consensus", "protocol_variance", "rank_entropy", "three_protocol_disagreement", "status", "reason"],
            "not_available", reason,
        ))
        write_csv(self.output / "parent_child_evidence_comparison.csv", empty_table(
            ["parent_id", "generated_candidate_id", "vina_delta", "open_mmgbsa_delta", "novelty", "tractability", "scaffold_relation", "warnings", "interpretation", "status", "reason"],
            "not_available", reason,
        ))
        write_csv(self.output / "phase17_shadow_decision.csv", empty_table(
            ["candidate_id", "phase15_rank", "phase17_shadow_rank", "rank_change", "high_cost_physics_evidence", "uncertainty_change", "status", "reason"],
            "not_available", reason,
        ))
        write_csv(self.output / "phase17_next20_acquisition.csv", empty_table(
            ["candidate_id", "current_evidence", "missing_evidence", "uncertainty", "voi_proxy", "reason", "status"],
            "not_generated", reason,
        ))
        save_gate_figures(self.output, backend, results)

        after = {name: sha256(self.project / name) for name in before}
        write_json(self.output / "model_hashes_after.json", after)
        if before != after:
            raise ValueError("protected_model_hash_changed_during_phase17")
        summary = {
            "phase": "Phase 17", "status": "completed_at_qualification_gate",
            "started_at": started, "completed_at": now(), "backend_status": backend["scientific_gate"],
            "qualification": gate, "qualification_runtime_seconds": 0.0,
            "qualification_runtime_status": "not_run_backend_capability_gate_blocked",
            "batch30": {"started": False, "success": 0, "failed": 0},
            "expanded_to_60": False, "high_cost_evidence_records": 0,
            "open_mmgbsa_distribution": "not_available", "three_protocol_correlation": "not_available",
            "generated_parent_comparison": "not_available", "shadow_decision": "not_available",
            "next20": "not_available", "candidate_pool": {"historical": 60, "generated": 30, "total": 90},
            "protocol_id": PROTOCOL_ID, "protocol_hash": protocol["protocol_hash"],
            "protocol_frozen": False, "historical_models_modified": False,
            "protected_model_count": len(before), "model_hashes_unchanged": before == after,
            "training_performed": False, "simulated_numerical_results": False,
            "biological_activity_claim": False, "stopped_before_phase18": True,
        }
        summary["total_workflow_runtime_seconds"] = time.perf_counter() - timer
        write_json(self.output / "phase17_execution_summary.json", summary)
        return summary
