from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import resource
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


OPENMM_PREFIX = Path("/home/lenovojlu/.local/share/atpnav/envs/atpnav-openmm")
MMGBSA_PREFIX = Path("/home/lenovojlu/.local/share/atpnav/envs/atpnav-mmgbsa")
CACHE_ROOT = Path("/home/lenovojlu/.cache/atpnav/phase17_1")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def run(command: list[str], cwd: Path, timeout: int = 3600) -> dict[str, Any]:
    started = time.perf_counter()
    result = subprocess.run(
        command,
        cwd=cwd,
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )
    return {
        "command": command,
        "return_code": result.returncode,
        "stdout": result.stdout[-12000:],
        "stderr": result.stderr[-12000:],
        "elapsed_seconds": time.perf_counter() - started,
    }


def _tool(executable: str, prefix: Path) -> str:
    path = prefix / "bin" / executable
    if not path.is_file():
        raise FileNotFoundError(path)
    return str(path)


def build_reference_peptide(work: Path) -> dict[str, Any]:
    leap_input = work / "build_peptide.leap"
    leap_input.write_text(
        "source leaprc.protein.ff14SB\n"
        "pep = sequence { ACE ALA ALA ALA NME }\n"
        "savepdb pep peptide.pdb\n"
        "saveamberparm pep peptide.prmtop peptide.inpcrd\n"
        "quit\n",
        encoding="utf-8",
    )
    result = run([_tool("tleap", MMGBSA_PREFIX), "-f", str(leap_input)], work)
    expected = [work / "peptide.pdb", work / "peptide.prmtop", work / "peptide.inpcrd"]
    result["artifacts"] = {path.name: sha256(path) for path in expected if path.is_file()}
    result["passed"] = result["return_code"] == 0 and len(result["artifacts"]) == 3
    return result


def build_and_sample_openmm(work: Path) -> dict[str, Any]:
    # OpenFF discovers AmberTools through PATH. Calling the environment's Python
    # by absolute path does not activate that prefix automatically.
    os.environ["PATH"] = (
        str(MMGBSA_PREFIX / "bin")
        + os.pathsep
        + str(OPENMM_PREFIX / "bin")
        + os.pathsep
        + os.environ.get("PATH", "")
    )
    from openff.toolkit import Molecule
    from openff.units import unit as offunit
    from openmm import LangevinMiddleIntegrator, Platform, unit
    from openmm import app
    from openmmforcefields.generators import SystemGenerator
    import mdtraj as md
    import numpy as np
    import parmed as pmd

    started = time.perf_counter()
    peptide = app.PDBFile(str(work / "peptide.pdb"))
    modeller = app.Modeller(peptide.topology, peptide.positions)
    receptor_atom_count = modeller.topology.getNumAtoms()

    ligand = Molecule.from_smiles("c1ccccc1", allow_undefined_stereo=True)
    ligand.name = "LIG"
    ligand.generate_conformers(n_conformers=1)
    ligand.assign_partial_charges(partial_charge_method="am1bcc")
    charge_sum = float(sum(ligand.partial_charges).m_as(offunit.elementary_charge))
    for atom in ligand.atoms:
        atom.metadata["residue_name"] = "LIG"
        atom.metadata["residue_number"] = "1"
        atom.metadata["chain_id"] = "L"

    lig_topology = ligand.to_topology().to_openmm()
    ligand_atom_count = lig_topology.getNumAtoms()
    positions = ligand.conformers[0].to_openmm()
    protein_xyz = np.asarray(peptide.positions.value_in_unit(unit.nanometer), dtype=float)
    center = protein_xyz.mean(axis=0)
    ligand_xyz = np.asarray(positions.value_in_unit(unit.nanometer), dtype=float)
    ligand_center = ligand_xyz.mean(axis=0)
    translated = (ligand_xyz - ligand_center + center + [0.45, 0.0, 0.0]) * unit.nanometer
    modeller.add(lig_topology, translated)

    generator = SystemGenerator(
        forcefields=["amber14/protein.ff14SB.xml", "amber14/tip3p.xml"],
        small_molecule_forcefield="gaff-2.11",
        molecules=[ligand],
        cache=str(work / "gaff-template-cache.json"),
        forcefield_kwargs={
            # Export all bonds explicitly so the GROMACS bridge retains their
            # force constants instead of receiving OpenMM-only constraints.
            "constraints": None,
            # Flexible water avoids an OpenMM->ParmEd SETTLE export ambiguity.
            # This is a certification micro-system, not an ATP evidence protocol.
            "rigidWater": False,
            "removeCMMotion": True,
        },
        periodic_forcefield_kwargs={
            "nonbondedMethod": app.PME,
            "nonbondedCutoff": 0.9 * unit.nanometer,
            "ewaldErrorTolerance": 5e-4,
        },
    )
    modeller.addSolvent(
        generator.forcefield,
        model="tip3p",
        padding=0.75 * unit.nanometer,
        ionicStrength=0.05 * unit.molar,
        neutralize=True,
    )
    system = generator.create_system(modeller.topology, molecules=[ligand])
    integrator = LangevinMiddleIntegrator(
        300 * unit.kelvin, 1.0 / unit.picosecond, 0.001 * unit.picoseconds
    )
    integrator.setRandomNumberSeed(20260829)
    platform = Platform.getPlatformByName("CPU")
    simulation = app.Simulation(modeller.topology, system, integrator, platform)
    simulation.context.setPositions(modeller.positions)
    simulation.minimizeEnergy(maxIterations=1000)
    simulation.context.setVelocitiesToTemperature(300 * unit.kelvin, 20260829)
    simulation.step(1000)

    dcd = work / "toolchain.dcd"
    simulation.reporters.append(app.DCDReporter(str(dcd), 100))
    simulation.reporters.append(
        app.StateDataReporter(
            str(work / "sampling.csv"),
            100,
            step=True,
            potentialEnergy=True,
            temperature=True,
            speed=True,
            separator=",",
        )
    )
    simulation.step(1000)
    state = simulation.context.getState(getPositions=True, getEnergy=True)
    potential = float(state.getPotentialEnergy().value_in_unit(unit.kilojoule_per_mole))

    with (work / "system.pdb").open("w", encoding="utf-8") as handle:
        app.PDBFile.writeFile(modeller.topology, state.getPositions(), handle, keepIds=True)
    structure = pmd.openmm.load_topology(modeller.topology, system, xyz=state.getPositions())
    structure.save(str(work / "system.top"), overwrite=True)
    structure.save(str(work / "system.gro"), overwrite=True)

    trajectory = md.load_dcd(str(dcd), top=str(work / "system.pdb"))
    trajectory.save_xtc(str(work / "toolchain.xtc"))
    finite_coordinates = bool(math.isfinite(float(trajectory.xyz.mean())))

    receptor_indices = list(range(1, receptor_atom_count + 1))
    ligand_indices = list(
        range(receptor_atom_count + 1, receptor_atom_count + ligand_atom_count + 1)
    )
    all_indices = list(range(1, modeller.topology.getNumAtoms() + 1))
    index_lines = ["[ System ]"]
    index_lines.extend(
        " ".join(map(str, all_indices[i : i + 15]))
        for i in range(0, len(all_indices), 15)
    )
    index_lines.append("[ Receptor ]")
    index_lines.extend(
        " ".join(map(str, receptor_indices[i : i + 15]))
        for i in range(0, len(receptor_indices), 15)
    )
    index_lines.append("[ Ligand ]")
    index_lines.extend(
        " ".join(map(str, ligand_indices[i : i + 15]))
        for i in range(0, len(ligand_indices), 15)
    )
    (work / "index.ndx").write_text("\n".join(index_lines) + "\n", encoding="utf-8")

    return {
        "passed": (
            abs(charge_sum) < 1e-5
            and math.isfinite(potential)
            and finite_coordinates
            and trajectory.n_frames == 10
        ),
        "ligand": "benzene",
        "ligand_smiles": "c1ccccc1",
        "charge_method": "AM1-BCC through OpenFF Toolkit/AmberTools",
        "ligand_charge_sum_e": charge_sum,
        "ligand_atom_count": ligand_atom_count,
        "receptor_atom_count": receptor_atom_count,
        "system_atom_count": modeller.topology.getNumAtoms(),
        "minimization": "OpenMM minimizeEnergy(maxIterations=1000)",
        "equilibration_steps": 1000,
        "sampling_steps": 1000,
        "time_step_fs": 1.0,
        "trajectory_frames": trajectory.n_frames,
        "trajectory_read": finite_coordinates,
        "final_potential_energy_kj_mol": potential,
        "platform": platform.getName(),
        "elapsed_seconds": time.perf_counter() - started,
        "artifacts": {
            name: sha256(work / name)
            for name in [
                "gaff-template-cache.json",
                "sampling.csv",
                "system.pdb",
                "system.top",
                "system.gro",
                "toolchain.dcd",
                "toolchain.xtc",
                "index.ndx",
            ]
            if (work / name).is_file()
        },
    }


def create_gromacs_tpr(work: Path) -> dict[str, Any]:
    mdp = work / "analysis.mdp"
    mdp.write_text(
        "integrator = md\n"
        "dt = 0.002\n"
        "nsteps = 0\n"
        "constraints = none\n"
        "cutoff-scheme = Verlet\n"
        "coulombtype = PME\n"
        "rcoulomb = 0.9\n"
        "rvdw = 0.9\n"
        "pbc = xyz\n",
        encoding="utf-8",
    )
    result = run(
        [
            _tool("gmx", MMGBSA_PREFIX),
            "grompp",
            "-f",
            str(mdp),
            "-c",
            str(work / "system.gro"),
            "-p",
            str(work / "system.top"),
            "-o",
            str(work / "system.tpr"),
            "-maxwarn",
            "2",
        ],
        work,
    )
    result["passed"] = result["return_code"] == 0 and (work / "system.tpr").is_file()
    if result["passed"]:
        result["artifact_sha256"] = sha256(work / "system.tpr")
    return result


def run_mmgbsa(work: Path) -> dict[str, Any]:
    input_file = work / "mmpbsa.in"
    input_file.write_text(
        "&general\n"
        "  sys_name=\"phase17_1_toolchain_certification\",\n"
        "  startframe=1, endframe=10, interval=1, keep_files=0,\n"
        "/\n"
        "&gb\n"
        "  igb=5, saltcon=0.050,\n"
        "/\n",
        encoding="utf-8",
    )
    result = run(
        [
            _tool("gmx_MMPBSA", MMGBSA_PREFIX),
            "-O",
            "-nogui",
            "-i",
            str(input_file),
            "-cs",
            str(work / "system.tpr"),
            "-ci",
            str(work / "index.ndx"),
            "-cg",
            "1",
            "2",
            "-ct",
            str(work / "toolchain.xtc"),
            "-cp",
            str(work / "system.top"),
            "-o",
            str(work / "FINAL_RESULTS_MMPBSA.dat"),
            "-eo",
            str(work / "FINAL_RESULTS_MMPBSA.csv"),
        ],
        work,
        timeout=3600,
    )
    output = work / "FINAL_RESULTS_MMPBSA.dat"
    delta_total = None
    if output.is_file():
        for line in output.read_text(encoding="utf-8", errors="replace").splitlines():
            normalized = line.replace("Δ", "DELTA ").strip()
            if normalized.startswith("DELTA TOTAL") or line.strip().startswith("ΔTOTAL"):
                fields = line.split()
                for field in fields[1:]:
                    try:
                        delta_total = float(field)
                        break
                    except ValueError:
                        continue
    result.update(
        {
            "finite_delta_total": delta_total is not None and math.isfinite(delta_total),
            "delta_total_kcal_mol": delta_total,
            "passed": result["return_code"] == 0
            and delta_total is not None
            and math.isfinite(delta_total),
            "artifacts": {
                path.name: sha256(path)
                for path in [output, work / "FINAL_RESULTS_MMPBSA.csv"]
                if path.is_file()
            },
        }
    )
    return result


def certify(work: Path) -> dict[str, Any]:
    work.mkdir(parents=True, exist_ok=True)
    started = utc_now()
    steps: dict[str, Any] = {}
    try:
        steps["protein_topology"] = build_reference_peptide(work)
        if not steps["protein_topology"]["passed"]:
            raise RuntimeError("protein_topology_failed")
        steps["parameterization_and_sampling"] = build_and_sample_openmm(work)
        if not steps["parameterization_and_sampling"]["passed"]:
            raise RuntimeError("parameterization_or_sampling_failed")
        steps["gromacs_topology"] = create_gromacs_tpr(work)
        if not steps["gromacs_topology"]["passed"]:
            raise RuntimeError("gromacs_topology_failed")
        steps["mmgbsa_analysis"] = run_mmgbsa(work)
        if not steps["mmgbsa_analysis"]["passed"]:
            raise RuntimeError("mmgbsa_analysis_failed")
        status = "passed"
        reason = ""
    except Exception as exc:
        status = "failed"
        reason = f"{type(exc).__name__}:{exc}"
    result = {
        "test_id": "phase17_1_synthetic_protein_ligand_full_chain_v1",
        "scope": "tool-chain certification only; not ATP-Navigator scientific evidence",
        "started_at": started,
        "completed_at": utc_now(),
        "status": status,
        "failure_reason": reason,
        "steps": steps,
        "peak_child_memory_kb": resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss,
        "environment": {
            "openmm_prefix": str(OPENMM_PREFIX),
            "mmgbsa_prefix": str(MMGBSA_PREFIX),
        },
    }
    target = work / "toolchain_certification.json"
    target.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--work", type=Path, default=CACHE_ROOT / "full_chain")
    parser.add_argument("--clean", action="store_true")
    args = parser.parse_args()
    if args.clean and args.work.is_dir():
        shutil.rmtree(args.work)
    result = certify(args.work)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
