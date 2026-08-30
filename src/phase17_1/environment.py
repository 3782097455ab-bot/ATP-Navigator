from __future__ import annotations

import importlib.metadata
import json
import os
import platform
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from .certification import CACHE_ROOT, MMGBSA_PREFIX, OPENMM_PREFIX, sha256
from .protocol import atomic_json, build_protocol, prepare_receptor, utc_now


PROJECT = Path("/mnt/d/tiaozhansai/ATP-Navigator")


def _command(argv: list[str]) -> dict[str, Any]:
    try:
        result = subprocess.run(argv, capture_output=True, text=True, timeout=30, check=False)
        return {
            "return_code": result.returncode,
            "stdout": result.stdout.strip()[-4000:],
            "stderr": result.stderr.strip()[-4000:],
        }
    except Exception as exc:
        return {"return_code": None, "stdout": "", "stderr": f"{type(exc).__name__}:{exc}"}


def _version(prefix: Path, executable: str, args: list[str]) -> dict[str, Any]:
    path = prefix / "bin" / executable
    probe = _command([str(path), *args]) if path.is_file() else {
        "return_code": None,
        "stdout": "",
        "stderr": "not_found",
    }
    text = (probe["stdout"] + "\n" + probe["stderr"]).strip()
    return {
        "path": str(path) if path.is_file() else None,
        "available": bool(path.is_file() and probe["return_code"] == 0),
        "version_output": text[:1200],
        "probe_return_code": probe["return_code"],
    }


def package_version(prefix: Path, distribution: str) -> str:
    site = prefix / "lib/python3.11/site-packages"
    for item in importlib.metadata.distributions(path=[str(site)]):
        name = str(item.metadata.get("Name", "")).lower().replace("-", "_")
        if name == distribution.lower().replace("-", "_"):
            return item.version
    return "not_found"


def parse_delta_total(path: Path) -> float | None:
    if not path.is_file():
        return None
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.strip().startswith("ΔTOTAL"):
            try:
                return float(line.split()[1])
            except (ValueError, IndexError):
                return None
    return None


def collect(project: Path = PROJECT) -> dict[str, Any]:
    output = project / "results/phase17_1"
    runtime = project / "workspace_local/phase17_1"
    output.mkdir(parents=True, exist_ok=True)
    runtime.mkdir(parents=True, exist_ok=True)

    synthetic_path = CACHE_ROOT / "full_chain/toolchain_certification.json"
    synthetic = (
        json.loads(synthetic_path.read_text(encoding="utf-8"))
        if synthetic_path.is_file()
        else {"status": "missing"}
    )
    official_result = (
        CACHE_ROOT
        / "gmx_test/gmx_MMPBSA_test/examples/Protein_ligand/ST/FINAL_RESULTS_MMPBSA.dat"
    )
    official_delta = parse_delta_total(official_result)
    official = {
        "test": "gmx_MMPBSA official Protein_ligand/ST example",
        "status": "passed" if official_delta is not None else "failed_or_missing",
        "finite_delta_total": official_delta,
        "unit": "kcal/mol",
        "artifact_path": str(official_result),
        "artifact_sha256": sha256(official_result) if official_result.is_file() else None,
        "scope": "official tool example only; excluded from ATP evidence",
    }
    toolchain = {
        "created_at": utc_now(),
        "official_analysis_test": official,
        "full_chain_synthetic_test": synthetic,
        "status": (
            "passed"
            if official["status"] == "passed" and synthetic.get("status") == "passed"
            else "failed"
        ),
        "training_performed": False,
        "atp_evidence_records": 0,
    }
    atomic_json(output / "toolchain_test_results.json", toolchain)

    tools = {
        "gromacs": _version(MMGBSA_PREFIX, "gmx", ["--version"]),
        "gmx_MMPBSA": _version(MMGBSA_PREFIX, "gmx_MMPBSA", ["--version"]),
        "antechamber": _version(MMGBSA_PREFIX, "antechamber", ["-h"]),
        "tleap": _version(MMGBSA_PREFIX, "tleap", ["-h"]),
        "parmed": {
            "available": package_version(MMGBSA_PREFIX, "parmed") != "not_found",
            "version": package_version(MMGBSA_PREFIX, "parmed"),
        },
        "openmm": {
            "available": package_version(OPENMM_PREFIX, "openmm") != "not_found",
            "version": package_version(OPENMM_PREFIX, "openmm"),
        },
        "openff_toolkit": {
            "available": package_version(OPENMM_PREFIX, "openff-toolkit") != "not_found",
            "version": package_version(OPENMM_PREFIX, "openff-toolkit"),
        },
        "openmmforcefields": {
            "available": package_version(OPENMM_PREFIX, "openmmforcefields") != "not_found",
            "version": package_version(OPENMM_PREFIX, "openmmforcefields"),
        },
        "meeko": {
            "available": package_version(OPENMM_PREFIX, "meeko") != "not_found",
            "version": package_version(OPENMM_PREFIX, "meeko"),
        },
        "rdkit": {
            "available": package_version(OPENMM_PREFIX, "rdkit") != "not_found",
            "version": package_version(OPENMM_PREFIX, "rdkit"),
        },
        "mdtraj": {
            "available": package_version(OPENMM_PREFIX, "mdtraj") != "not_found",
            "version": package_version(OPENMM_PREFIX, "mdtraj"),
        },
    }
    complete = all(record.get("available", False) for record in tools.values())
    backend = {
        "created_at": utc_now(),
        "selected_route": "OpenMM/OpenFF/GAFF sampling + ParmEd/GROMACS bridge + gmx_MMPBSA analysis",
        "status": "usable" if complete and toolchain["status"] == "passed" else "blocked",
        "tools": tools,
        "certification": toolchain["status"],
        "no_simulated_numerical_output": True,
    }
    atomic_json(output / "backend_certification.json", backend)

    os_release = {}
    release = Path("/etc/os-release")
    if release.is_file():
        for line in release.read_text(encoding="utf-8").splitlines():
            if "=" in line:
                key, value = line.split("=", 1)
                os_release[key] = value.strip('"')
    manifest = {
        "created_at": utc_now(),
        "wsl_status": "available",
        "wsl_version": 2,
        "distribution": os_release.get("PRETTY_NAME", "unknown"),
        "kernel": platform.release(),
        "architecture": platform.machine(),
        "python_openmm": _command([str(OPENMM_PREFIX / "bin/python"), "--version"]),
        "python_mmgbsa": _command([str(MMGBSA_PREFIX / "bin/python"), "--version"]),
        "openmm_environment_prefix": str(OPENMM_PREFIX),
        "mmgbsa_environment_prefix": str(MMGBSA_PREFIX),
        "isolation": "WSL user-local; Windows project .venv unchanged",
        "project_mount": str(project),
        "backend_status": backend["status"],
    }
    atomic_json(output / "wsl_environment_manifest.json", manifest)

    receptor = prepare_receptor(project, runtime)
    protocol, audit = build_protocol(project, receptor, toolchain)
    atomic_json(output / "atp_mmgbsa_protocol_audit.json", audit)
    atomic_json(output / "open_mmgbsa_7p3w_v2.json", protocol)

    profile = {
        "created_at": utc_now(),
        "logical_cpu_count": os.cpu_count(),
        "meminfo": Path("/proc/meminfo").read_text(encoding="utf-8").splitlines()[:6],
        "selected_concurrent_jobs": protocol["resource_policy"]["concurrent_jobs"],
        "openmm_cpu_threads": protocol["resource_policy"]["openmm_cpu_threads"],
        "certification_peak_child_memory_kb": synthetic.get("peak_child_memory_kb"),
        "qualification_runtime": "not_started",
    }
    atomic_json(output / "resource_profile.json", profile)
    return {
        "environment": manifest,
        "backend": backend,
        "toolchain": toolchain,
        "protocol": protocol,
        "audit": audit,
    }


if __name__ == "__main__":
    print(json.dumps(collect(), ensure_ascii=False, indent=2, sort_keys=True))
