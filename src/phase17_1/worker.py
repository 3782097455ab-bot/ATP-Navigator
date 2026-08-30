from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import subprocess
import time
import traceback
from pathlib import Path
from typing import Any

from .certification import MMGBSA_PREFIX, OPENMM_PREFIX, sha256
from .protocol import atomic_json, stable_hash, utc_now


def stage(checkpoint: Path, name: str, **values: Any) -> None:
    current = json.loads(checkpoint.read_text(encoding="utf-8")) if checkpoint.is_file() else {}
    current.update({"stage": name, "updated_at": utc_now(), **values})
    atomic_json(checkpoint, current)


def run_command(argv: list[str], cwd: Path, timeout: int = 7200) -> dict[str, Any]:
    started = time.perf_counter()
    result = subprocess.run(
        argv,
        cwd=cwd,
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )
    return {
        "argv": argv,
        "return_code": result.returncode,
        "stdout": result.stdout[-16000:],
        "stderr": result.stderr[-16000:],
        "elapsed_seconds": time.perf_counter() - started,
    }


def reconstruct_pose(path: Path, expected_smiles: str):
    from meeko import PDBQTMolecule, RDKitMolCreate
    from rdkit import Chem

    pdbqt = PDBQTMolecule.from_file(str(path), poses_to_read=1)
    molecules = RDKitMolCreate.from_pdbqt_mol(pdbqt)
    if len(molecules) != 1 or molecules[0] is None:
        raise ValueError("rank1_pose_reconstruction_failed")
    posed = molecules[0]
    observed = Chem.RemoveHs(posed)
    expected = Chem.MolFromSmiles(expected_smiles)
    if expected is None:
        raise ValueError("invalid_expected_smiles")
    observed_smiles = Chem.MolToSmiles(observed, isomericSmiles=True)
    expected_canonical = Chem.MolToSmiles(expected, isomericSmiles=True)
    observed_key = Chem.MolToInchiKey(observed)
    expected_key = Chem.MolToInchiKey(expected)
    if observed_key != expected_key or observed_smiles != expected_canonical:
        raise ValueError(
            "pose_identity_mismatch:"
            f"observed={observed_smiles}:{observed_key};"
            f"expected={expected_canonical}:{expected_key}"
        )
    return posed, {
        "expected_canonical_smiles": expected_canonical,
        "observed_canonical_smiles": observed_smiles,
        "expected_inchikey": expected_key,
        "observed_inchikey": observed_key,
        "exact_structure_match": True,
        "pose_sha256": sha256(path),
    }


def build_system(request: dict[str, Any], work: Path):
    os.environ["PATH"] = (
        str(MMGBSA_PREFIX / "bin")
        + os.pathsep
        + str(OPENMM_PREFIX / "bin")
        + os.pathsep
        + os.environ.get("PATH", "")
    )
    os.environ["OPENMM_CPU_THREADS"] = str(request["protocol"]["resource_policy"]["openmm_cpu_threads"])

    from openff.toolkit import Molecule
    from openff.units import unit as offunit
    from openmm import CustomExternalForce, MonteCarloBarostat, XmlSerializer, app, unit
    from openmmforcefields.generators import SystemGenerator

    receptor = app.PDBFile(request["receptor_path"])
    receptor_count = receptor.topology.getNumAtoms()
    posed, identity = reconstruct_pose(Path(request["pose_path"]), request["canonical_smiles"])
    ligand = Molecule.from_rdkit(
        posed, hydrogens_are_explicit=True, allow_undefined_stereo=True
    )
    ligand.name = "LIG"
    ligand.assign_partial_charges(partial_charge_method="am1bcc")
    charge = float(sum(ligand.partial_charges).m_as(offunit.elementary_charge))
    formal_charge = int(round(float(ligand.total_charge.m_as(offunit.elementary_charge))))
    if abs(charge - formal_charge) > 1e-4:
        raise ValueError(f"am1bcc_charge_normalization_failed:{charge}:{formal_charge}")
    for atom in ligand.atoms:
        atom.metadata["residue_name"] = "LIG"
        atom.metadata["residue_number"] = "1"
        atom.metadata["chain_id"] = "L"

    modeller = app.Modeller(receptor.topology, receptor.positions)
    ligand_topology = ligand.to_topology().to_openmm()
    ligand_count = ligand_topology.getNumAtoms()
    modeller.add(ligand_topology, ligand.conformers[0].to_openmm())

    protocol = request["protocol"]
    solvent = protocol["solvent"]
    sampling = protocol["sampling"]
    cache = work / "gaff-template-cache.json"
    generator = SystemGenerator(
        forcefields=["amber14/protein.ff14SB.xml", "amber14/tip3p.xml"],
        small_molecule_forcefield="gaff-2.11",
        molecules=[ligand],
        cache=str(cache),
        forcefield_kwargs={
            "constraints": app.HBonds,
            "rigidWater": True,
            "removeCMMotion": True,
        },
        periodic_forcefield_kwargs={
            "nonbondedMethod": app.PME,
            "nonbondedCutoff": sampling["nonbonded_cutoff_nm"] * unit.nanometer,
            "ewaldErrorTolerance": 5e-4,
        },
    )
    modeller.addSolvent(
        generator.forcefield,
        model="tip3p",
        padding=solvent["padding_nm"] * unit.nanometer,
        ionicStrength=solvent["ionic_strength_molar"] * unit.molar,
        neutralize=bool(solvent["neutralize"]),
    )
    system = generator.create_system(modeller.topology, molecules=[ligand])
    system.addForce(
        MonteCarloBarostat(
            sampling["pressure_atmosphere"] * unit.atmosphere,
            sampling["temperature_kelvin"] * unit.kelvin,
            25,
        )
    )
    restraint = CustomExternalForce("0.5*k*periodicdistance(x,y,z,x0,y0,z0)^2")
    restraint.addGlobalParameter(
        "k",
        sampling["protein_heavy_restraint_kcal_mol_angstrom2"]
        * 418.4
        * unit.kilojoule_per_mole
        / unit.nanometer**2,
    )
    for parameter in ["x0", "y0", "z0"]:
        restraint.addPerParticleParameter(parameter)
    positions_nm = modeller.positions.value_in_unit(unit.nanometer)
    restrained = 0
    for atom in modeller.topology.atoms():
        if atom.index >= receptor_count:
            break
        if atom.element is not None and atom.element.symbol != "H":
            point = positions_nm[atom.index]
            restraint.addParticle(atom.index, [float(point[0]), float(point[1]), float(point[2])])
            restrained += 1
    system.addForce(restraint)
    (work / "system.xml").write_text(XmlSerializer.serialize(system), encoding="utf-8")
    return modeller, system, ligand, identity, {
        "receptor_atom_count": receptor_count,
        "ligand_atom_count": ligand_count,
        "system_atom_count": modeller.topology.getNumAtoms(),
        "protein_heavy_atoms_restrained": restrained,
        "ligand_formal_charge_e": formal_charge,
        "ligand_am1bcc_charge_sum_e": charge,
        "gaff_cache_sha256": sha256(cache),
    }


def sample(request: dict[str, Any], work: Path, modeller, system) -> dict[str, Any]:
    from openmm import LangevinMiddleIntegrator, Platform, app, unit

    sampling = request["protocol"]["sampling"]
    seed = sampling["base_random_seed"] + int(
        hashlib.sha256(request["candidate_id"].encode()).hexdigest()[:6], 16
    ) % 1000000
    integrator = LangevinMiddleIntegrator(
        sampling["temperature_kelvin"] * unit.kelvin,
        sampling["friction_per_ps"] / unit.picosecond,
        sampling["time_step_fs"] * unit.femtoseconds,
    )
    integrator.setRandomNumberSeed(seed)
    platform = Platform.getPlatformByName("CPU")
    properties = {"Threads": str(request["protocol"]["resource_policy"]["openmm_cpu_threads"])}
    simulation = app.Simulation(modeller.topology, system, integrator, platform, properties)
    production_checkpoint = work / "production.chk"
    equilibration_checkpoint = work / "equilibrated.chk"
    progress_path = work / "simulation_progress.json"
    progress = (
        json.loads(progress_path.read_text(encoding="utf-8"))
        if progress_path.is_file()
        else {"completed_production_steps": 0, "chunks": []}
    )

    if production_checkpoint.is_file() and progress["completed_production_steps"] > 0:
        simulation.loadCheckpoint(str(production_checkpoint))
    elif equilibration_checkpoint.is_file():
        simulation.loadCheckpoint(str(equilibration_checkpoint))
    else:
        simulation.context.setPositions(modeller.positions)
        simulation.minimizeEnergy(maxIterations=sampling["minimization_max_iterations"])
        simulation.context.setVelocitiesToTemperature(
            sampling["temperature_kelvin"] * unit.kelvin, seed
        )
        simulation.step(sampling["equilibration_steps"])
        temporary = equilibration_checkpoint.with_suffix(".tmp")
        simulation.saveCheckpoint(str(temporary))
        os.replace(temporary, equilibration_checkpoint)

    chunk_steps = 5000
    target = sampling["production_steps"]
    completed = int(progress.get("completed_production_steps", 0))
    while completed < target:
        steps = min(chunk_steps, target - completed)
        end_step = completed + steps
        dcd = work / f"production_{end_step:09d}.dcd"
        if dcd.is_file() and end_step in progress.get("chunks", []):
            completed = end_step
            continue
        simulation.reporters = [
            app.DCDReporter(str(dcd), sampling["frame_interval_steps"]),
            app.StateDataReporter(
                str(work / f"production_{end_step:09d}.csv"),
                sampling["frame_interval_steps"],
                step=True,
                potentialEnergy=True,
                temperature=True,
                density=True,
                speed=True,
                separator=",",
            ),
        ]
        simulation.step(steps)
        temporary = production_checkpoint.with_suffix(".tmp")
        simulation.saveCheckpoint(str(temporary))
        os.replace(temporary, production_checkpoint)
        completed = end_step
        chunks = sorted(set(progress.get("chunks", []) + [end_step]))
        progress = {
            "completed_production_steps": completed,
            "target_production_steps": target,
            "chunks": chunks,
            "updated_at": utc_now(),
        }
        atomic_json(progress_path, progress)

    state = simulation.context.getState(getPositions=True, getEnergy=True)
    potential = float(state.getPotentialEnergy().value_in_unit(unit.kilojoule_per_mole))
    with (work / "system.pdb").open("w", encoding="utf-8") as handle:
        app.PDBFile.writeFile(modeller.topology, state.getPositions(), handle, keepIds=True)
    return {
        "random_seed": seed,
        "platform": platform.getName(),
        "completed_production_steps": completed,
        "chunk_count": len(progress["chunks"]),
        "final_potential_energy_kj_mol": potential,
        "finite_final_energy": math.isfinite(potential),
    }


def export_and_analyze(request: dict[str, Any], work: Path, modeller, ligand) -> dict[str, Any]:
    from openmm import app, unit
    from openmmforcefields.generators import SystemGenerator
    import mdtraj as md
    import numpy as np
    import parmed as pmd

    sampling = request["protocol"]["sampling"]
    export_generator = SystemGenerator(
        forcefields=["amber14/protein.ff14SB.xml", "amber14/tip3p.xml"],
        small_molecule_forcefield="gaff-2.11",
        molecules=[ligand],
        cache=str(work / "gaff-template-cache.json"),
        forcefield_kwargs={"constraints": None, "rigidWater": False, "removeCMMotion": True},
        periodic_forcefield_kwargs={
            "nonbondedMethod": app.PME,
            "nonbondedCutoff": sampling["nonbonded_cutoff_nm"] * unit.nanometer,
            "ewaldErrorTolerance": 5e-4,
        },
    )
    export_system = export_generator.create_system(modeller.topology, molecules=[ligand])
    final_pdb = app.PDBFile(str(work / "system.pdb"))
    structure = pmd.openmm.load_topology(
        modeller.topology, export_system, xyz=final_pdb.positions
    )
    structure.save(str(work / "system.top"), overwrite=True)
    structure.save(str(work / "system.gro"), overwrite=True)

    chunks = sorted(work.glob("production_*.dcd"))
    if not chunks:
        raise ValueError("production_trajectory_missing")
    trajectories = [md.load_dcd(str(path), top=str(work / "system.pdb")) for path in chunks]
    trajectory = md.join(trajectories, check_topology=True)
    if trajectory.n_frames != sampling["expected_frames"]:
        raise ValueError(
            f"trajectory_frame_count:{trajectory.n_frames}!={sampling['expected_frames']}"
        )
    if not np.isfinite(trajectory.xyz).all():
        raise ValueError("trajectory_nonfinite_coordinates")
    trajectory.save_xtc(str(work / "production.xtc"))

    receptor_count = app.PDBFile(request["receptor_path"]).topology.getNumAtoms()
    ligand_count = ligand.n_atoms
    all_indices = list(range(1, modeller.topology.getNumAtoms() + 1))
    receptor_indices = list(range(1, receptor_count + 1))
    ligand_indices = list(range(receptor_count + 1, receptor_count + ligand_count + 1))
    lines = []
    for name, values in [
        ("System", all_indices),
        ("Receptor", receptor_indices),
        ("Ligand", ligand_indices),
    ]:
        lines.append(f"[ {name} ]")
        lines.extend(
            " ".join(map(str, values[i : i + 15])) for i in range(0, len(values), 15)
        )
    (work / "index.ndx").write_text("\n".join(lines) + "\n", encoding="utf-8")

    (work / "analysis.mdp").write_text(
        "integrator = md\n"
        "dt = 0.002\n"
        "nsteps = 0\n"
        "continuation = yes\n"
        "constraints = none\n"
        "cutoff-scheme = Verlet\n"
        "coulombtype = PME\n"
        "rcoulomb = 1.0\n"
        "rvdw = 1.0\n"
        "pbc = xyz\n",
        encoding="utf-8",
    )
    grompp = run_command(
        [
            str(MMGBSA_PREFIX / "bin/gmx"),
            "grompp",
            "-f",
            str(work / "analysis.mdp"),
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
    atomic_json(work / "grompp_command.json", grompp)
    if grompp["return_code"] != 0 or not (work / "system.tpr").is_file():
        raise RuntimeError("grompp_failed:" + grompp["stderr"][-1000:])

    (work / "mmpbsa.in").write_text(
        "&general\n"
        f"  sys_name=\"{request['candidate_id']}\",\n"
        f"  startframe=1, endframe={trajectory.n_frames}, interval=1, keep_files=0,\n"
        "/\n"
        "&gb\n"
        "  igb=5, saltcon=0.150,\n"
        "/\n",
        encoding="utf-8",
    )
    analysis = run_command(
        [
            str(MMGBSA_PREFIX / "bin/gmx_MMPBSA"),
            "-O",
            "-nogui",
            "-i",
            str(work / "mmpbsa.in"),
            "-cs",
            str(work / "system.tpr"),
            "-ci",
            str(work / "index.ndx"),
            "-cg",
            "1",
            "2",
            "-ct",
            str(work / "production.xtc"),
            "-cp",
            str(work / "system.top"),
            "-o",
            str(work / "FINAL_RESULTS_MMPBSA.dat"),
            "-eo",
            str(work / "FINAL_RESULTS_MMPBSA.csv"),
        ],
        work,
        timeout=7200,
    )
    atomic_json(work / "mmpbsa_command.json", analysis)
    if analysis["return_code"] != 0:
        raise RuntimeError("gmx_mmpbsa_failed:" + analysis["stderr"][-1200:])

    final = work / "FINAL_RESULTS_MMPBSA.dat"
    mean = standard_deviation = None
    for line in final.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.strip().startswith("ΔTOTAL"):
            fields = line.split()
            mean = float(fields[1])
            standard_deviation = float(fields[3])
            break
    if mean is None or not all(math.isfinite(value) for value in [mean, standard_deviation]):
        raise ValueError("finite_delta_total_not_parsed")

    protein_ca = trajectory.topology.select("protein and name CA")
    ligand_heavy = [
        atom.index
        for atom in trajectory.topology.atoms
        if receptor_count <= atom.index < receptor_count + ligand_count
        and atom.element is not None
        and atom.element.symbol != "H"
    ]
    protein_rmsd = md.rmsd(trajectory, trajectory, 0, atom_indices=protein_ca)
    aligned = trajectory.superpose(trajectory, 0, atom_indices=protein_ca)
    # The trajectory is already aligned on the receptor.  Calling md.rmsd with
    # ligand atoms here would align the ligand a second time and erase the
    # protein-relative motion that this QC quantity is meant to measure.
    ligand_delta = aligned.xyz[:, ligand_heavy, :] - aligned.xyz[0, ligand_heavy, :]
    ligand_rmsd = np.sqrt(np.square(ligand_delta).sum(axis=2).mean(axis=1))
    return {
        "open_mmgbsa_deltaG": mean,
        "open_mmgbsa_sd": standard_deviation,
        "unit": "kcal/mol",
        "analyzed_frames": trajectory.n_frames,
        "trajectory_finite": True,
        "protein_ca_rmsd_mean_nm": float(protein_rmsd.mean()),
        "protein_ca_rmsd_max_nm": float(protein_rmsd.max()),
        "ligand_heavy_rmsd_mean_nm": float(ligand_rmsd.mean()),
        "ligand_heavy_rmsd_max_nm": float(ligand_rmsd.max()),
        "analysis_artifacts": {
            name: sha256(work / name)
            for name in [
                "system.top",
                "system.gro",
                "system.tpr",
                "production.xtc",
                "FINAL_RESULTS_MMPBSA.dat",
                "FINAL_RESULTS_MMPBSA.csv",
                "grompp_command.json",
                "mmpbsa_command.json",
            ]
        },
    }


def run_candidate(request_path: Path, output_dir: Path) -> dict[str, Any]:
    request = json.loads(request_path.read_text(encoding="utf-8"))
    output_dir.mkdir(parents=True, exist_ok=True)
    result_path = output_dir / "result.json"
    request_hash = stable_hash(request)
    if result_path.is_file():
        existing = json.loads(result_path.read_text(encoding="utf-8"))
        if (
            existing.get("status") == "success"
            and existing.get("request_hash") == request_hash
            and existing.get("protocol_hash") == request["protocol"]["protocol_hash"]
        ):
            return {**existing, "cached": True}

    checkpoint = output_dir / "checkpoint.json"
    started = time.perf_counter()
    result: dict[str, Any] = {
        "candidate_id": request["candidate_id"],
        "protocol_id": request["protocol"]["protocol_id"],
        "protocol_hash": request["protocol"]["protocol_hash"],
        "request_hash": request_hash,
        "status": "running",
        "started_at": utc_now(),
        "cached": False,
        "training": False,
        "biological_activity_claim": False,
    }
    atomic_json(result_path, result)
    try:
        stage(checkpoint, "parameterization")
        modeller, system, ligand, identity, system_info = build_system(request, output_dir)
        stage(checkpoint, "sampling", system_info=system_info, identity=identity)
        sampling_info = sample(request, output_dir, modeller, system)
        if not sampling_info["finite_final_energy"]:
            raise ValueError("sampling_nonfinite_energy")
        stage(checkpoint, "analysis", sampling_info=sampling_info)
        analysis_info = export_and_analyze(request, output_dir, modeller, ligand)
        if analysis_info["analyzed_frames"] < request["protocol"]["analysis"]["minimum_finite_frames"]:
            raise ValueError("insufficient_finite_analysis_frames")
        result.update(
            {
                "status": "success",
                "completed_at": utc_now(),
                "elapsed_seconds": time.perf_counter() - started,
                "identity": identity,
                "system": system_info,
                "sampling": sampling_info,
                "analysis": analysis_info,
                "failure_stage": "",
                "failure_reason": "",
                "qc_status": "pass",
            }
        )
        stage(checkpoint, "completed", status="success")
    except Exception as exc:
        current_stage = (
            json.loads(checkpoint.read_text(encoding="utf-8")).get("stage", "unknown")
            if checkpoint.is_file()
            else "unknown"
        )
        result.update(
            {
                "status": "failed",
                "completed_at": utc_now(),
                "elapsed_seconds": time.perf_counter() - started,
                "failure_stage": current_stage,
                "failure_reason": f"{type(exc).__name__}:{exc}",
                "traceback": traceback.format_exc()[-12000:],
                "qc_status": "failed",
            }
        )
        stage(checkpoint, "failed", status="failed", reason=result["failure_reason"])
    atomic_json(result_path, result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run_candidate(args.request, args.output)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["status"] == "success" else 1


if __name__ == "__main__":
    raise SystemExit(main())
