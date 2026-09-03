from __future__ import annotations

import json
import platform
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pandas as pd
from rdkit import rdBase

from library_generation.engine import ReconstructedLibraryGenerator
from workspace.state import State

from .stages.decision import run_decision
from .stages.docking import estimate_vina, run_vina
from .stages.molecular_filtering import run_filter
from .stages.refinement import acquisition_panel, run_mmgbsa
from .stages.reporting import generate_reports, write_funnel
from .util import atomic_csv, atomic_json, ensure_link_or_copy, git_commit, sha256_file, stable_hash, utc_now, verify_file


DIRECTORIES = ["config", "manifests", "library", "filtering", "docking", "refinement", "mmgbsa", "evidence", "decision", "reports", "logs"]


class ReferencePipeline:
    """One-controller IN-2/7P3W workflow with immutable protocol identities."""

    def __init__(self, project: str | Path, config_path: str | Path):
        self.project = Path(project).resolve()
        self.config_path = Path(config_path)
        if not self.config_path.is_absolute():
            self.config_path = self.project / self.config_path
        # The configuration is JSON-compatible YAML on purpose: YAML readers
        # accept it, while the workflow does not require a new package.
        self.config = json.loads(self.config_path.read_text(encoding="utf-8"))
        self.config_hash = stable_hash(self.config)
        self._validate_config()
        self.model_baseline = json.loads((self.project / "results/phase14/model_hashes_before.json").read_text(encoding="utf-8"))

    def _validate_config(self) -> None:
        if self.config["generation"]["classification"] != "reconstructed reproducible derivative library":
            raise ValueError("generation_scientific_identity_invalid")
        if self.config["generation"]["historical_library_equivalence"] is not False:
            raise ValueError("historical_library_equivalence_must_be_false")
        if self.config["filtering"]["historical_quickprop_equivalence"] is not False:
            raise ValueError("RDKit_filtering_cannot_be_QuickProp")
        if self.config["docking"]["historical_glide_equivalence"] is not False:
            raise ValueError("Vina_cannot_be_Glide")
        if self.config["mmgbsa"]["historical_prime_equivalence"] is not False:
            raise ValueError("Open_MMGBSA_cannot_be_Prime")
        if abs(sum(self.config["decision"]["weights"].values()) - 1.0) > 1e-9:
            raise ValueError("decision_weights_must_sum_to_one")
        if not self.config["filtering"]["rules_frozen_before_reference_runs"]:
            raise ValueError("filter_rules_must_be_frozen")

    def _model_hashes(self) -> dict[str, str]:
        observed: dict[str, str] = {}
        for relative, expected in self.model_baseline.items():
            path = self.project / relative
            observed[relative] = verify_file(path, expected)
        return observed

    def _run_id(self, mode: str, provided: str | None) -> str:
        return provided or f"in2-7p3w-{mode}-reference-v1"

    def _directories(self, run_id: str) -> Path:
        run_dir = self.project / self.config["output_root"] / run_id
        for name in DIRECTORIES:
            (run_dir / name).mkdir(parents=True, exist_ok=True)
        return run_dir

    def _checkpoint(self, run_dir: Path, mode: str) -> dict[str, Any]:
        path = run_dir / "manifests/stage_state.json"
        if path.is_file():
            value = json.loads(path.read_text(encoding="utf-8"))
            if value["config_hash"] != self.config_hash or value["mode"] != mode:
                raise ValueError("checkpoint_config_or_mode_mismatch")
            return value
        value = {
            "schema_version": "reference_workflow_stage_state_v1",
            "run_id": run_dir.name,
            "mode": mode,
            "config_hash": self.config_hash,
            "status": "running",
            "created_at": utc_now(),
            "updated_at": utc_now(),
            "stages": {},
        }
        atomic_json(path, value)
        return value

    def _save_stage(self, run_dir: Path, checkpoint: dict[str, Any], row: dict[str, Any]) -> None:
        checkpoint["stages"][row["stage_id"]] = row
        checkpoint["updated_at"] = utc_now()
        atomic_json(run_dir / "manifests/stage_state.json", checkpoint)

    def _record_invocation(
        self,
        run_dir: Path,
        checkpoint: dict[str, Any],
        stop_after: str | None,
        retry_failed: bool,
    ) -> None:
        path = run_dir / "manifests/resume_history.json"
        history = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else []
        history.append(
            {
                "invoked_at": utc_now(),
                "status_before_invocation": checkpoint.get("status", "unknown"),
                "stages_already_checkpointed": sorted(checkpoint.get("stages", {})),
                "declared_stop_after": stop_after,
                "retry_failed": bool(retry_failed),
            }
        )
        atomic_json(path, history)

    def _reference_inputs(self, run_dir: Path) -> dict[str, Any]:
        target = self.project / self.config["target"]["prepared_pdb"]
        vina_receptor = self.project / self.config["target"]["vina_receptor"]
        target_hash = verify_file(target, self.config["target"]["prepared_pdb_sha256"])
        vina_hash = verify_file(vina_receptor, self.config["target"]["vina_receptor_sha256"])
        source = pd.read_csv(self.project / self.config["reference_ligand"]["source"], keep_default_na=False)
        row = source.loc[source["compound_id"].eq(self.config["reference_ligand"]["compound_id"])]
        if len(row) != 1:
            raise ValueError("reference_IN2_identity_not_unique")
        from rdkit import Chem

        canonical = Chem.MolToSmiles(Chem.MolFromSmiles(row.iloc[0]["SMILES"]), canonical=True, isomericSmiles=True)
        ligand_hash = __import__("hashlib").sha256(canonical.encode()).hexdigest()
        if ligand_hash != self.config["reference_ligand"]["canonical_smiles_sha256"]:
            raise ValueError("reference_IN2_hash_mismatch")
        payload = {
            "status": "completed_cached_prepared_assets",
            "target": self.config["target"],
            "target_hash": target_hash,
            "vina_receptor_hash": vina_hash,
            "reference_ligand_id": self.config["reference_ligand"]["compound_id"],
            "reference_ligand_canonical_smiles": canonical,
            "reference_ligand_hash": ligand_hash,
            "project_uuid": self.config["project"]["project_uuid"],
            "workflow_version": self.config["workflow_version"],
        }
        atomic_json(run_dir / "manifests/reference_inputs.json", payload)
        return payload

    def _generation(self, mode: str, run_dir: Path) -> dict[str, Any]:
        settings = self.config["generation"]
        generator = ReconstructedLibraryGenerator(self.project, self.project / settings["config"])
        if generator.config_hash != settings["expected_config_hash"]:
            raise ValueError("generation_config_hash_mismatch")
        cache_run = settings["cache_runs"][mode]
        target = int(self.config["modes"][mode]["library_size"])
        cache_manifest = self.project / "workspace_local/library_generation" / cache_run / "manifest.json"
        if cache_manifest.is_file() and settings["reuse_completed_cache"]:
            manifest = json.loads(cache_manifest.read_text(encoding="utf-8"))
        else:
            manifest = generator.generate(target, cache_run)
        if manifest["status"] != "completed" or int(manifest["counts"]["accepted_unique"]) != target:
            raise RuntimeError("library_generation_incomplete")
        if manifest["classification"] != settings["classification"] or manifest["historical_library_equivalence"] is not False:
            raise ValueError("library_scientific_identity_mismatch")
        source_root = self.project / "workspace_local/library_generation" / cache_run
        links = {}
        for source_name, destination_name in [("library.csv", "library.csv"), ("rejections.csv", "generation_rejections.csv")]:
            links[destination_name] = ensure_link_or_copy(source_root / source_name, run_dir / "library" / destination_name)
        snapshot = {**manifest, "source_cache_run": cache_run, "cache_reuse": True, "materialization": links}
        atomic_json(run_dir / "library/generation_manifest.json", snapshot)
        return snapshot

    def _stage_row(self, stage_id: str, status: str, input_count: int | None, output_count: int | None, protocol_id: str, runtime: float, **extra: Any) -> dict[str, Any]:
        completed = datetime.now(timezone.utc)
        return {
            "stage_id": stage_id,
            "status": status,
            "input_count": input_count,
            "output_count": output_count,
            "failed_count": extra.pop("failed_count", 0),
            "cached_count": extra.pop("cached_count", 0),
            "protocol_id": protocol_id,
            "runtime_seconds": float(runtime),
            "started_at": (completed - timedelta(seconds=float(runtime))).isoformat(),
            "completed_at": completed.isoformat(),
            **extra,
        }

    def _export_evidence(self, run_dir: Path, candidate_ids: set[str]) -> int:
        rows = [
            row
            for row in State(self.project).evidence_rows(self.config["project"]["project_id"])
            if row["compound_id"] in candidate_ids
        ]
        columns = [
            "evidence_id", "project_id", "compound_id", "evidence_type", "raw_value", "normalized_value",
            "unit", "protocol_id", "tool_version", "source_job_id", "artifact_hash", "timestamp", "provenance",
        ]
        atomic_csv(run_dir / "evidence/evidence_index.csv", pd.DataFrame(rows, columns=columns))
        return len(rows)

    def run(self, mode: str | None = None, run_id: str | None = None, stop_after: str | None = None, retry_failed: bool = False) -> dict[str, Any]:
        mode = mode or self.config["default_mode"]
        if mode not in self.config["modes"]:
            raise ValueError(f"unknown_mode:{mode}")
        run_id = self._run_id(mode, run_id)
        run_dir = self._directories(run_id)
        checkpoint = self._checkpoint(run_dir, mode)
        self._record_invocation(run_dir, checkpoint, stop_after, retry_failed)
        checkpoint["retry_failed_this_invocation"] = bool(retry_failed)
        checkpoint["updated_at"] = utc_now()
        atomic_json(run_dir / "manifests/stage_state.json", checkpoint)
        (run_dir / "config/config.snapshot.yaml").write_text(
            json.dumps(self.config, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8"
        )
        model_before = self._model_hashes()
        atomic_json(run_dir / "manifests/model_hashes_before.json", model_before)
        stages: list[dict[str, Any]] = []

        started = time.perf_counter()
        reference = self._reference_inputs(run_dir)
        row = self._stage_row("reference_inputs", reference["status"], 1, 1, "7P3W_prepared_assets + confirmed_IN2", time.perf_counter() - started, artifact="manifests/reference_inputs.json")
        stages.append(row); self._save_stage(run_dir, checkpoint, row)
        if stop_after == "reference_inputs":
            return self._paused(run_dir, checkpoint, stages)

        started = time.perf_counter()
        generation = self._generation(mode, run_dir)
        row = self._stage_row("library_generation", "completed_cache_hit", 1, int(generation["counts"]["accepted_unique"]), self.config["generation"]["protocol_id"], time.perf_counter() - started, cached_count=int(generation["counts"]["accepted_unique"]), artifact="library/library.csv")
        stages.append(row); self._save_stage(run_dir, checkpoint, row)
        if stop_after == "library_generation":
            return self._paused(run_dir, checkpoint, stages)

        started = time.perf_counter()
        filtering = run_filter(run_dir / "library/library.csv", run_dir / "filtering", self.config["filtering"], generation["library_hash"])
        row = self._stage_row("molecular_filtering", "completed_cache_hit" if filtering.get("cached") else filtering["status"], filtering["input_count"], filtering["accepted_count"], self.config["filtering"]["protocol_id"], time.perf_counter() - started, failed_count=filtering["rejected_count"], cached_count=filtering["input_count"] if filtering.get("cached") else 0, artifact="filtering/accepted_candidates.csv")
        stages.append(row); self._save_stage(run_dir, checkpoint, row)
        if stop_after == "molecular_filtering":
            return self._paused(run_dir, checkpoint, stages)

        estimate = estimate_vina(self.project, int(filtering["accepted_count"]), int(self.config["docking"]["workers"]))
        atomic_json(run_dir / "docking/vina_full_run_estimate.json", estimate)
        (run_dir / "reports/Vina_Full_Run_Estimate.md").write_text(
            "# Vina Full Run Estimate\n\n"
            f"- Candidate count after frozen cheap filter: {filtering['accepted_count']}\n"
            f"- Estimated wall time: {estimate.get('estimated_wall_seconds')} seconds\n"
            f"- Estimated CPU time: {estimate.get('estimated_cpu_seconds')} seconds\n"
            f"- Estimated disk: {estimate.get('estimated_disk_bytes')} bytes\n"
            f"- Estimated terminal checkpoint size: {estimate.get('estimated_checkpoint_bytes')} bytes\n"
            f"- Estimated failures from observed rate: {estimate.get('estimated_failures')}\n"
            f"- Configured concurrency: {estimate.get('requested_workers')} workers\n"
            f"- Source: real N=100 `vina_7p3w_v1` execution. This linear estimate is not a guarantee.\n",
            encoding="utf-8",
        )
        limit = float(self.config["docking"]["automatic_wall_time_limit_hours"][mode]) * 3600
        can_run = estimate.get("estimated_wall_seconds") is not None and float(estimate["estimated_wall_seconds"]) <= limit
        if not can_run:
            row = self._stage_row("docking", "blocked_by_resource_gate", filtering["accepted_count"], 0, self.config["docking"]["protocol_id"], 0.0, reason=f"estimated_wall_seconds={estimate.get('estimated_wall_seconds')} exceeds automatic_limit_seconds={limit}")
            stages.append(row); self._save_stage(run_dir, checkpoint, row)
            for stage_id, protocol in [("refinement", self.config["refinement"]["protocol_id"]), ("mmgbsa", self.config["mmgbsa"]["protocol_id"]), ("evidence_integration", "shared_evidence_registry"), ("decision", self.config["decision"]["profile_id"]), ("candidate_panel", self.config["decision"]["profile_id"])]:
                blocked = self._stage_row(stage_id, "not_run_upstream_resource_gate", 0, 0, protocol, 0.0)
                stages.append(blocked); self._save_stage(run_dir, checkpoint, blocked)
            return self._finalize(run_dir, checkpoint, mode, reference, generation, filtering, stages, 0)

        started = time.perf_counter()
        docking_config = {**self.config["docking"], "retry_failed": bool(retry_failed)}
        docking = run_vina(self.project, run_id, run_dir / "filtering/accepted_candidates.csv", run_dir / "docking", docking_config)
        row = self._stage_row("docking", docking["status"], docking["input_count"], docking["success"], docking["protocol_id"], time.perf_counter() - started, failed_count=docking["failed"], cached_count=docking["cached"], artifact="docking/vina_results.csv")
        stages.append(row); self._save_stage(run_dir, checkpoint, row)
        if stop_after == "docking":
            return self._paused(run_dir, checkpoint, stages)

        started = time.perf_counter()
        refinement = acquisition_panel(self.project, run_dir / "filtering/accepted_candidates.csv", run_dir / "docking/vina_results.csv", run_dir / "refinement", int(self.config["mmgbsa"]["panel_size"][mode]))
        row = self._stage_row("refinement", refinement["status"], refinement["input_count"], refinement["output_count"], refinement["protocol_id"], time.perf_counter() - started, artifact="refinement/acquisition_panel.csv")
        stages.append(row); self._save_stage(run_dir, checkpoint, row)
        if stop_after == "refinement":
            return self._paused(run_dir, checkpoint, stages)

        started = time.perf_counter()
        mmgbsa_config = {**self.config["mmgbsa"], "retry_failed": bool(retry_failed)}
        mmgbsa = run_mmgbsa(self.project, run_id, run_dir / "refinement/acquisition_panel.csv", run_dir / "mmgbsa", mmgbsa_config)
        row = self._stage_row("mmgbsa", mmgbsa["status"], mmgbsa["input_count"], mmgbsa["success"], mmgbsa["protocol_id"], time.perf_counter() - started, failed_count=mmgbsa["failed"], cached_count=mmgbsa["cached"], artifact="mmgbsa/open_mmgbsa_results.csv")
        stages.append(row); self._save_stage(run_dir, checkpoint, row)
        if stop_after == "mmgbsa":
            return self._paused(run_dir, checkpoint, stages)

        docking_rows = pd.read_csv(run_dir / "docking/vina_results.csv", keep_default_na=False)
        current_candidates = set(docking_rows.loc[docking_rows["status"].eq("success"), "compound_id"].astype(str))
        evidence_count = self._export_evidence(run_dir, current_candidates)
        evidence_row = self._stage_row("evidence_integration", "completed", docking["success"] + mmgbsa["success"], evidence_count, "shared_Evidence_Registry", 0.0, artifact="evidence/evidence_index.csv")
        stages.append(evidence_row); self._save_stage(run_dir, checkpoint, evidence_row)

        started = time.perf_counter()
        decision = run_decision(self.project, run_dir / "refinement/acquisition_panel.csv", run_dir / "mmgbsa/open_mmgbsa_results.csv", run_dir / "decision", self.config["decision"], run_id)
        row = self._stage_row("decision", decision["status"], decision["input_count"], decision["output_count"], self.config["decision"]["profile_id"], time.perf_counter() - started, artifact="decision/candidate_panel.csv")
        stages.append(row); self._save_stage(run_dir, checkpoint, row)
        row = self._stage_row("candidate_panel", "completed" if decision["output_count"] else "insufficient_evidence", decision["output_count"], min(decision["output_count"], int(self.config["decision"]["output_top_n"])), self.config["decision"]["profile_id"], 0.0, artifact="decision/candidate_panel.csv")
        stages.append(row); self._save_stage(run_dir, checkpoint, row)
        evidence_row["output_count"] = self._export_evidence(run_dir, current_candidates)
        evidence_row["completed_at"] = utc_now()
        self._save_stage(run_dir, checkpoint, evidence_row)
        return self._finalize(run_dir, checkpoint, mode, reference, generation, filtering, stages, decision["output_count"])

    def _paused(self, run_dir: Path, checkpoint: dict[str, Any], stages: list[dict[str, Any]]) -> dict[str, Any]:
        checkpoint["status"] = "paused_at_declared_stage_boundary"
        checkpoint["updated_at"] = utc_now()
        atomic_json(run_dir / "manifests/stage_state.json", checkpoint)
        return {"run_id": run_dir.name, "status": checkpoint["status"], "stages": stages, "resume_ready": True}

    def _finalize(self, run_dir: Path, checkpoint: dict[str, Any], mode: str, reference: dict[str, Any], generation: dict[str, Any], filtering: dict[str, Any], stages: list[dict[str, Any]], candidate_panel_count: int) -> dict[str, Any]:
        model_after = self._model_hashes()
        atomic_json(run_dir / "manifests/model_hashes_after.json", model_after)
        if model_after != self.model_baseline:
            raise RuntimeError("protected_model_hash_changed")
        docking_protocol = json.loads((self.project / self.config["docking"]["protocol_file"]).read_text(encoding="utf-8"))
        mmgbsa_protocol = json.loads((self.project / self.config["mmgbsa"]["protocol_file"]).read_text(encoding="utf-8"))
        computational_stages = [row for row in stages if row["stage_id"] in {"docking", "mmgbsa"}]
        docking_candidate_seconds = 0.0
        if (run_dir / "docking/vina_results.csv").is_file():
            docking_candidate_seconds = float(pd.to_numeric(pd.read_csv(run_dir / "docking/vina_results.csv").get("elapsed_seconds"), errors="coerce").sum())
        mmgbsa_candidate_seconds = 0.0
        if (run_dir / "mmgbsa/open_mmgbsa_results.csv").is_file():
            mmgbsa_candidate_seconds = float(pd.to_numeric(pd.read_csv(run_dir / "mmgbsa/open_mmgbsa_results.csv").get("runtime_seconds"), errors="coerce").sum())
        completed_at = utc_now()
        elapsed_wall = (datetime.fromisoformat(completed_at) - datetime.fromisoformat(checkpoint["created_at"])).total_seconds()
        if any(row["status"] == "blocked_by_resource_gate" for row in stages):
            run_status = "completed_with_declared_resource_gate"
        elif any(int(row.get("failed_count", 0) or 0) > 0 for row in computational_stages):
            run_status = "completed_with_computational_failures"
        elif any(row["stage_id"] == "decision" and row["status"] == "insufficient_evidence" for row in stages):
            run_status = "completed_with_insufficient_decision_evidence"
        else:
            run_status = "completed"
        manifest = {
            "schema_version": "in2_7p3w_reference_run_manifest_v1",
            "run_id": run_dir.name,
            "project_uuid": self.config["project"]["project_uuid"],
            "mode": mode,
            "status": run_status,
            "workflow_version": self.config["workflow_version"],
            "git_commit": git_commit(self.project),
            "config_hash": self.config_hash,
            "library_hash": generation["library_hash"],
            "filter_hash": filtering["filter_hash"],
            "filter_protocol_hash": filtering["filter_protocol_hash"],
            "reference_inputs": reference,
            "software_versions": {
                "python": platform.python_version(),
                "rdkit": rdBase.rdkitVersion,
                "pandas": pd.__version__,
                "vina": self.config["docking"]["tool_version"],
                "openmm_route": self.config["mmgbsa"]["tool"],
            },
            "protocol_hashes": {
                "generation": generation["config_hash"],
                "filtering": filtering["filter_protocol_hash"],
                "docking": stable_hash(docking_protocol),
                "refinement": stable_hash({"config": self.config["refinement"], "panel_size": self.config["mmgbsa"]["panel_size"][mode]}),
                "mmgbsa": mmgbsa_protocol["protocol_hash"],
                "decision": stable_hash(self.config["decision"]),
            },
            "random_seeds": {"generation": generation["random_seed"], "vina": 20260827, "open_mmgbsa_base": 20260829},
            "runtime_summary": {
                "run_wall_seconds_since_initial_checkpoint": elapsed_wall,
                "library_generation_source_seconds": float(generation.get("elapsed_seconds_total", 0.0)),
                "filtering_source_seconds": float(filtering.get("elapsed_seconds", 0.0)),
                "docking_summed_candidate_seconds": docking_candidate_seconds,
                "mmgbsa_summed_candidate_seconds": mmgbsa_candidate_seconds,
            },
            "stages": stages,
            "candidate_panel_count": int(candidate_panel_count),
            "evidence_record_count": int(next((row.get("output_count", 0) for row in stages if row["stage_id"] == "evidence_integration"), 0) or 0),
            "filtered_out_candidates": int(filtering["rejected_count"]),
            "failed_jobs": int(sum(int(row.get("failed_count", 0) or 0) for row in computational_stages)),
            "cached_jobs": int(sum(int(row.get("cached_count", 0) or 0) for row in computational_stages)),
            "cached_library_structures": int(generation["counts"]["accepted_unique"]),
            "artifact_hashes": {},
            "protected_model_count": len(model_after),
            "protected_model_hashes_unchanged": True,
            "training_performed": False,
            "retry_failed_this_invocation": bool(checkpoint.get("retry_failed_this_invocation", False)),
            "scientific_boundaries": {
                "historical_schrodinger_workflow": "historical evidence only",
                "reconstructed_library": "not the historical 2024 Auto_Enum library",
                "vina": "not Glide",
                "open_mmgbsa": "not Prime MM/GBSA or experimental affinity",
                "candidate_panel": "computational pre-experimental prioritization",
            },
            "started_at": checkpoint["created_at"],
            "completed_at": completed_at,
        }
        funnel = write_funnel(run_dir, stages)
        manifest["screening_funnel"] = funnel
        reports = generate_reports(run_dir, manifest)
        manifest["reports"] = reports
        checkpoint["status"] = manifest["status"]
        checkpoint["updated_at"] = utc_now()
        atomic_json(run_dir / "manifests/stage_state.json", checkpoint)
        manifest["artifact_hashes"] = {
            str(path.relative_to(run_dir)).replace("\\", "/"): sha256_file(path)
            for path in run_dir.rglob("*")
            if path.is_file() and path.name != "run_manifest.json" and not path.name.endswith(".tmp")
        }
        atomic_json(run_dir / "manifests/run_manifest.json", manifest)
        public = {
            "workflow_name": "IN-2 / 7P3W 可复现计算筛选工作流",
            "scientific_scope": self.config["project"]["scientific_scope"],
            "run_id": run_dir.name,
            "mode": mode,
            "status": manifest["status"],
            "run_manifest": str((run_dir / "manifests/run_manifest.json").relative_to(self.project)).replace("\\", "/"),
            "stage_counts": stages,
            "candidate_panel": str((run_dir / "decision/candidate_panel.csv").relative_to(self.project)).replace("\\", "/") if (run_dir / "decision/candidate_panel.csv").is_file() else None,
            "updated_at": utc_now(),
        }
        atomic_json(self.project / "results/library_generation/workflow_public_summary.json", public)
        return manifest
