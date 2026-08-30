from __future__ import annotations

import hashlib
import io
import json
import math
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROTOCOL_ID = "open_mmgbsa_7p3w_v2"
OPENMM_PREFIX = Path("/home/lenovojlu/.local/share/atpnav/envs/atpnav-openmm")
MMGBSA_PREFIX = Path("/home/lenovojlu/.local/share/atpnav/envs/atpnav-mmgbsa")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def stable_hash(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()


def atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _heavy_coordinates(topology, positions) -> dict[tuple[str, str, str, str], tuple[float, ...]]:
    from openmm import unit

    xyz = positions.value_in_unit(unit.angstrom)
    output = {}
    for atom, point in zip(topology.atoms(), xyz):
        if atom.element is None or atom.element.symbol == "H":
            continue
        residue = atom.residue
        key = (residue.chain.id, residue.id, residue.name, atom.name)
        if key in output:
            raise ValueError(f"duplicate_heavy_atom_identity:{key}")
        output[key] = tuple(float(value) for value in point)
    return output


def prepare_receptor(project: Path, runtime: Path) -> dict[str, Any]:
    """Preserve source heavy atoms, replace incompatible legacy hydrogens, and certify ff14SB."""
    os.environ["PATH"] = (
        str(MMGBSA_PREFIX / "bin")
        + os.pathsep
        + str(OPENMM_PREFIX / "bin")
        + os.pathsep
        + os.environ.get("PATH", "")
    )
    from pdbfixer import PDBFixer
    from openmm import app

    source = project / "configs/projects/ab_atp_synthase/vina_7p3w_v1/assets/ATP_e_g_prepared.pdb"
    source_pdb = app.PDBFile(str(source))
    source_heavy = _heavy_coordinates(source_pdb.topology, source_pdb.positions)

    # The historical PDB contains a duplicate H name and HXT termini that do not
    # match Amber templates. Only hydrogens are removed here; heavy atoms remain.
    modeller = app.Modeller(source_pdb.topology, source_pdb.positions)
    modeller.delete(
        [
            atom
            for atom in modeller.topology.atoms()
            if atom.element is not None and atom.element.symbol == "H"
        ]
    )
    buffer = io.StringIO()
    app.PDBFile.writeFile(modeller.topology, modeller.positions, buffer, keepIds=True)
    buffer.seek(0)
    fixer = PDBFixer(pdbfile=buffer)
    fixer.findMissingResidues()
    missing_residues = {
        str(key): list(value) for key, value in sorted(fixer.missingResidues.items())
    }
    if missing_residues:
        raise ValueError(f"internal_missing_residue_rebuild_forbidden:{missing_residues}")
    fixer.findMissingAtoms()
    missing_atom_residue_count = len(fixer.missingAtoms)
    missing_terminal_count = len(fixer.missingTerminals)
    fixer.addMissingAtoms()
    fixer.addMissingHydrogens(7.4)

    forcefield = app.ForceField("amber14/protein.ff14SB.xml")
    system = forcefield.createSystem(
        fixer.topology, nonbondedMethod=app.NoCutoff, constraints=None
    )
    if system.getNumParticles() != fixer.topology.getNumAtoms():
        raise ValueError("receptor_system_atom_count_mismatch")

    prepared = runtime / "shared/receptor_amber_prepared.pdb"
    prepared.parent.mkdir(parents=True, exist_ok=True)
    with prepared.open("w", encoding="utf-8") as handle:
        app.PDBFile.writeFile(fixer.topology, fixer.positions, handle, keepIds=True)
    prepared_pdb = app.PDBFile(str(prepared))
    prepared_heavy = _heavy_coordinates(prepared_pdb.topology, prepared_pdb.positions)
    shared = sorted(set(source_heavy).intersection(prepared_heavy))
    if len(shared) != len(source_heavy):
        missing = sorted(set(source_heavy).difference(prepared_heavy))
        raise ValueError(f"source_heavy_atoms_not_preserved:{missing[:10]}")
    squared = []
    maximum = 0.0
    for key in shared:
        delta2 = sum(
            (source_heavy[key][i] - prepared_heavy[key][i]) ** 2 for i in range(3)
        )
        squared.append(delta2)
        maximum = max(maximum, math.sqrt(delta2))
    rmsd = math.sqrt(sum(squared) / len(squared)) if squared else float("nan")
    if not math.isfinite(rmsd) or rmsd > 1e-6:
        raise ValueError(f"source_heavy_coordinates_changed:rmsd={rmsd}")

    return {
        "status": "passed",
        "source_path": str(source.relative_to(project)).replace("\\", "/"),
        "source_sha256": sha256(source),
        "prepared_runtime_path": str(prepared),
        "prepared_sha256": sha256(prepared),
        "source_atom_count": source_pdb.topology.getNumAtoms(),
        "prepared_atom_count": prepared_pdb.topology.getNumAtoms(),
        "source_heavy_atom_count": len(source_heavy),
        "shared_heavy_atom_count": len(shared),
        "added_heavy_terminal_atoms": len(prepared_heavy) - len(source_heavy),
        "heavy_atom_rmsd_angstrom": rmsd,
        "maximum_shared_heavy_atom_shift_angstrom": maximum,
        "missing_internal_residues_added": 0,
        "missing_atom_residue_count_before_terminal_repair": missing_atom_residue_count,
        "terminal_repairs": missing_terminal_count,
        "hydrogen_policy": "remove legacy hydrogens; OpenMM/PDBFixer add hydrogens at pH 7.4",
        "forcefield_match": "amber14/protein.ff14SB.xml createSystem passed",
        "receptor_scope": "7P3W subunits e and g only",
    }


def historical_context(project: Path) -> dict[str, Any]:
    root = project.parent
    systems = {
        "IN2": root / "运行/运行/ATP-Ref-MD1/ATP-Ref-MD1-out.cms",
        "Hit3": root / "运行/运行/ATP-Top1-MD2/ATP-Top1-MD2-out.cms",
    }
    keywords = [b"MEMBRANE PROTEIN", b"POPC", b"POPE", b"DPPC", b"SPC ", b"OPLS_2005"]
    records = {}
    for name, path in systems.items():
        if not path.is_file():
            records[name] = {"status": "missing", "path": str(path)}
            continue
        raw = path.read_bytes()
        records[name] = {
            "status": "present",
            "path": str(path),
            "sha256": sha256(path),
            "size_bytes": path.stat().st_size,
            "keyword_counts": {key.decode(): raw.count(key) for key in keywords},
        }
    return records


def build_protocol(
    project: Path,
    receptor: dict[str, Any],
    certification: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    historical = historical_context(project)
    certification_passed = certification.get("status") == "passed"
    receptor_passed = receptor.get("status") == "passed"
    ready = certification_passed and receptor_passed
    membrane_keywords = {
        key: record.get("keyword_counts", {})
        for key, record in historical.items()
        if record.get("status") == "present"
    }
    audit = {
        "created_at": utc_now(),
        "status": "ready_for_qualification" if ready else "protocol_design_blocked",
        "scientific_scope": "screening-level restrained aqueous relaxation and endpoint MM/GBSA",
        "questions": {
            "mmgbsa_structure": {
                "answer": "Use the frozen 7P3W e/g receptor heavy-atom coordinates and each candidate's frozen vina_7p3w_v1 rank-1 pose. Do not reuse the Vina PDBQT charge model as a molecular-mechanics topology.",
                "reason": "The historical prepared complex exists only for IN-2; using it for every ligand would not provide candidate-specific bound poses.",
            },
            "membrane_requirement": {
                "answer": "A membrane is required for a physically faithful long-timescale model of membrane-associated ATP synthase subunits. Phase17.1 does not claim that level of simulation.",
                "evidence": membrane_keywords,
            },
            "membrane_omission_boundary": {
                "answer": "The frozen protocol omits membrane lipids because neither the Vina receptor nor the available historical system contains POPC/POPE/DPPC coordinates. Protein heavy atoms are restrained and sampling is short; resulting values are protocol-specific comparative rescoring evidence only, not absolute affinity, conformational stability, biological activity, or membrane-mechanism evidence.",
            },
            "difference_from_historical_prime": {
                "answer": "Historical static Prime/MMGBSA and MD-derived MMGBSA used Schrodinger/OPLS-era inputs and incomplete protocol metadata. v2 uses Amber ff14SB, GAFF2/AM1-BCC, TIP3P, explicit restrained sampling, and gmx_MMPBSA GB igb=5. Values remain separate endpoints and must not be numerically pooled or substituted.",
            },
        },
        "receptor_qualification": receptor,
        "backend_certification_status": certification.get("status", "missing"),
        "historical_system_audit": historical,
        "blocking_reason": "" if ready else "backend_or_receptor_certification_failed",
        "training_performed": False,
        "simulated_results_allowed": False,
    }
    protocol: dict[str, Any] = {
        "protocol_id": PROTOCOL_ID,
        "status": "ready_for_qualification" if ready else "protocol_design_blocked",
        "frozen_for_qualification": ready,
        "source_pose_protocol": "vina_7p3w_v1",
        "source_pose_selection": "rank_1_pose_only",
        "source_pose_identity_policy": "Meeko SMILES atom-map reconstruction plus canonical connectivity equality; no name-based mapping",
        "receptor": {
            "source": receptor.get("source_path"),
            "source_sha256": receptor.get("source_sha256"),
            "prepared_runtime_path": receptor.get("prepared_runtime_path"),
            "prepared_sha256": receptor.get("prepared_sha256"),
            "scope": "7P3W subunits e and g only",
            "heavy_atom_policy": "source coordinates preserved; only terminal heavy repair and pH 7.4 hydrogen normalization",
        },
        "scientific_interpretation": "comparative screening-level high-cost computational evidence; not activity, experimental affinity, or membrane-mechanism validation",
        "topology_route": "OpenMM SystemGenerator -> ParmEd GROMACS topology -> gmx_MMPBSA",
        "protein_force_field": "Amber ff14SB (amber14/protein.ff14SB.xml)",
        "ligand_force_field": "GAFF 2.11",
        "ligand_charge_model": "AM1-BCC via OpenFF Toolkit and AmberTools",
        "receptor_protonation": "PDBFixer/OpenMM at pH 7.4 after removal of legacy hydrogens",
        "solvent": {
            "model": "TIP3P explicit water",
            "padding_nm": 1.0,
            "ionic_strength_molar": 0.15,
            "neutralize": True,
            "membrane": "omitted; no lipid coordinates available",
        },
        "sampling": {
            "ensemble": "restrained NPT",
            "temperature_kelvin": 300.0,
            "pressure_atmosphere": 1.0,
            "friction_per_ps": 1.0,
            "time_step_fs": 2.0,
            "constraints": "HBonds",
            "rigid_water": True,
            "nonbonded_method": "PME",
            "nonbonded_cutoff_nm": 1.0,
            "minimization_max_iterations": 5000,
            "equilibration_steps": 25000,
            "equilibration_ps": 50.0,
            "production_steps": 50000,
            "production_ps": 100.0,
            "frame_interval_steps": 1000,
            "expected_frames": 50,
            "protein_heavy_restraint_kcal_mol_angstrom2": 2.0,
            "base_random_seed": 20260829,
        },
        "analysis": {
            "tool": "gmx_MMPBSA 1.6.5",
            "trajectory_approximation": "single trajectory",
            "gb_model": "igb=5, mbondi2",
            "salt_concentration_molar": 0.15,
            "entropy": "not included",
            "output": "open_mmgbsa_deltaG",
            "unit": "kcal/mol",
            "minimum_finite_frames": 40,
        },
        "resource_policy": {
            "concurrent_jobs": 1,
            "openmm_cpu_threads": 12,
            "checkpoint_after_each_candidate": True,
            "resume_success_without_recompute": True,
        },
        "gates": {
            "qualification": {
                "requested": 8,
                "minimum_success": 7,
                "require_finite_parser": True,
                "forbid_systematic_corruption": True,
            },
            "pilot30": {
                "cumulative_target": 30,
                "minimum_success": 27,
                "require_finite_parser": True,
                "forbid_systematic_corruption": True,
            },
            "expanded60": {"cumulative_target": 60},
        },
        "forbidden_equivalences": [
            "historical_prime_mmgbsa",
            "historical_md_mmgbsa",
            "biological_activity",
            "experimental_binding_affinity",
        ],
        "tool_environments": {
            "openmm": str(OPENMM_PREFIX),
            "gmx_mmpbsa": str(MMGBSA_PREFIX),
        },
    }
    protocol["protocol_hash"] = stable_hash(protocol)
    audit["protocol_id"] = PROTOCOL_ID
    audit["protocol_hash"] = protocol["protocol_hash"]
    return protocol, audit
