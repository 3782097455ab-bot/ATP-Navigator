"""Open, stage-gated workflow entry for reconstructed IN-2 libraries.

Only actually available tools are executed.  Vina evidence remains Vina
evidence; unavailable commercial stages and unrequested high-cost physics are
represented as explicit gates rather than fabricated numbers.
"""
from __future__ import annotations

import concurrent.futures
import hashlib
import json
import shutil
from pathlib import Path

import numpy as np
import pandas as pd

from input_processor import CandidateInputProcessor, atomic_csv
from phase14_full_library_vina import _existing_result, _worker
from workspace.state import State, digest, encode, file_hash, now, write_json

from .engine import ReconstructedLibraryGenerator


PROJECT_ID = "in2_reconstructed_open_workflow"
VINA_PROTOCOL_ID = "vina_7p3w_v1"


def _sha(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def _percentile(values: pd.Series, lower_is_better: bool) -> pd.Series:
    numeric = pd.to_numeric(values, errors="coerce")
    ranks = numeric.rank(method="average", ascending=True)
    n = int(numeric.notna().sum())
    if n <= 1:
        return pd.Series(np.where(numeric.notna(), 0.5, np.nan), index=values.index)
    utility = (n - ranks) / (n - 1) if lower_is_better else (ranks - 1) / (n - 1)
    return utility


class ReproducibleWorkflow:
    def __init__(self, project: str | Path, config_path: str | Path):
        self.project = Path(project).resolve()
        self.generator = ReconstructedLibraryGenerator(self.project, config_path)

    def _vina_assets(self) -> tuple[dict, Path, Path]:
        protocol = json.loads((self.project / "configs/projects/ab_atp_synthase/vina_7p3w_v1/vina_protocol.json").read_text(encoding="utf-8"))
        receptor = self.project / "workspace_local/artifacts/e5e92ede1b1d000b00a7e5dbe3f3b02f0df0cd63b47dd8a421eeb8bddb1083ed/receptor.pdbqt"
        vina = self.project / "workspace_local/tools/vina-1.2.7/vina_1.2.7_win.exe"
        if not vina.is_file() or not receptor.is_file():
            raise RuntimeError("real_vina_backend_or_frozen_receptor_unavailable")
        if file_hash(receptor) != "e5e92ede1b1d000b00a7e5dbe3f3b02f0df0cd63b47dd8a421eeb8bddb1083ed":
            raise RuntimeError("frozen_vina_receptor_hash_mismatch")
        if file_hash(vina) != "e0c4b2715e0c1a74f6e92d0f3be0328ac97542eafbc111e6b1efad897a73cce5":
            raise RuntimeError("vina_executable_hash_mismatch")
        return protocol, receptor, vina

    def _run_vina(self, run_id: str, library: pd.DataFrame, workers: int) -> tuple[pd.DataFrame, dict]:
        protocol, receptor, vina = self._vina_assets()
        protocol_hash = digest(protocol)
        root = self.generator._run_dir(run_id) / "vina_jobs"
        tasks = []
        for row in library.to_dict("records"):
            signature = _sha({"compound_id": row["compound_id"], "canonical_smiles": row["canonical_smiles"],
                              "protocol_hash": protocol_hash, "receptor_hash": file_hash(receptor), "tool_hash": file_hash(vina)})
            tasks.append({"compound_id": row["compound_id"], "smiles": row["canonical_smiles"], "signature": signature,
                          "folder": str(root / signature[:2] / signature), "protocol": protocol,
                          "vina": str(vina), "receptor": str(receptor), "timeout": 1800,
                          "retry_failed": False, "attempt": 1})
        results, pending = [], []
        for task in tasks:
            existing = _existing_result(task)
            (results if existing else pending).append(existing or task)
        if pending:
            with concurrent.futures.ProcessPoolExecutor(max_workers=max(1, min(int(workers), 8))) as executor:
                results.extend(executor.map(_worker, pending))
        task_by_id = {task["compound_id"]: task for task in tasks}
        for result in results:
            result.setdefault("folder", task_by_id[result["compound_id"]]["folder"])
        frame = pd.DataFrame(results).sort_values("compound_id").reset_index(drop=True)
        atomic_csv(frame, self.generator._run_dir(run_id) / "vina_results.csv")
        summary = {"protocol_id": VINA_PROTOCOL_ID, "protocol_hash": protocol_hash,
                   "tool": "AutoDock Vina", "tool_version": "1.2.7",
                   "historical_glide_equivalence": False, "total": len(tasks),
                   "success": int(frame["status"].eq("success").sum()),
                   "failed": int(frame["status"].eq("failed").sum()),
                   "cached": int(frame.get("cached", pd.Series(False, index=frame.index)).astype(bool).sum()),
                   "newly_executed_this_invocation": len(pending),
                   "actual_jobs_executed_in_run": int(frame["attempt"].fillna(0).astype(int).ge(1).sum())}
        write_json(self.generator._run_dir(run_id) / "vina_summary.json", summary)
        return frame, summary

    def _register_vina(self, run_id: str, library_path: Path, results: pd.DataFrame) -> int:
        successful = results.loc[results["status"].eq("success")]
        if successful.empty:
            return 0
        protocol, receptor, vina = self._vina_assets()
        state = State(self.project)
        state.project_id(PROJECT_ID)
        # Reuse the already-frozen registry manifest.  Its path fields were
        # normalized to absolute paths during the original registration, while
        # the repository JSON keeps relative paths.  Scientific parameters must
        # match; the immutable registry row itself is never replaced.
        frozen = state.protocol(VINA_PROTOCOL_ID)
        for field in ["box", "exhaustiveness", "num_modes", "energy_range", "seed", "cpu"]:
            if frozen.get(field) != protocol.get(field):
                raise RuntimeError(f"frozen_vina_protocol_mismatch:{field}")
        batch = state.batch(PROJECT_ID, {"workflow":"reconstructed_IN2_open_route", "run_id":run_id,
                                        "scope":"Vina docking evidence; not Glide and not biological activity"})
        source_artifact = state.artifact(library_path)
        receptor_artifact = state.artifact(receptor)
        for result in successful.to_dict("records"):
            state.candidate(PROJECT_ID, result["compound_id"], result["canonical_smiles"], alias="reconstructed_IN2_derivative")
            pose_path = Path(result["folder"]) / "pose.pdbqt"
            pose_artifact = state.artifact(pose_path)
            command = {"action":"reconstructed_library_vina", "run_id":run_id, "signature":result["signature"],
                       "protocol_hash":digest(frozen), "tool_sha256":file_hash(vina),
                       "receptor_hash":file_hash(receptor), "ligand_hash":result["ligand_sha256"]}
            job = state.job(batch, PROJECT_ID, result["compound_id"], "vina", VINA_PROTOCOL_ID,
                            [source_artifact, receptor_artifact], command)
            with state.connect() as db:
                db.execute("""UPDATE calculation_job SET status='completed',started_at=?,completed_at=?,return_code=0,
                    stdout_path=?,stderr_path=?,output_artifacts=?,attempt=CASE WHEN attempt<1 THEN 1 ELSE attempt END
                    WHERE job_id=?""", (result["started_at"], result["completed_at"],
                    str(Path(result["folder"]) / "stdout.txt"), str(Path(result["folder"]) / "stderr.txt"),
                    encode([pose_artifact]), job))
            provenance = {"origin":"tool_execution", "tool_id":"autodock_vina", "run_id":run_id,
                          "protocol_id":VINA_PROTOCOL_ID, "receptor_hash":file_hash(receptor),
                          "ligand_hash":result["ligand_sha256"], "pose_hash":result["pose_sha256"],
                          "scope":"open docking evidence; not Glide and not biological activity"}
            state.register_many(PROJECT_ID, job, pose_artifact["artifact_hash"], [
                {"compound_id":result["compound_id"], "evidence_type":"vina_affinity",
                 "raw_value":float(result["vina_affinity"]), "unit":"kcal/mol", "tool_version":"1.2.7", "provenance":provenance},
                {"compound_id":result["compound_id"], "evidence_type":"pose_qc",
                 "raw_value":{"status":"pass", "pose_count":int(result["pose_count"]), "pose_centroid":result["pose_centroid"]},
                 "unit":"qc_record", "tool_version":"1.2.7", "provenance":provenance},
            ], "tool_execution")
        with state.connect() as db:
            return int(db.execute("SELECT COUNT(*) FROM evidence WHERE project_id=? AND protocol_id=?", (PROJECT_ID, VINA_PROTOCOL_ID)).fetchone()[0])

    def _shadow_decision(self, run_id: str, library: pd.DataFrame, vina: pd.DataFrame) -> pd.DataFrame:
        root = self.generator._run_dir(run_id)
        input_frame = library[["compound_id", "canonical_smiles"]].rename(columns={"canonical_smiles":"SMILES"})
        input_frame["docking_score"] = ""
        input_frame["mmgbsa_score"] = ""
        input_frame["source"] = "reconstructed_reproducible_derivative_library"
        atomic_csv(input_frame, root / "decision_input.csv")
        processed = CandidateInputProcessor(self.project).process(root / "decision_input.csv", root / "processed_candidates.csv")
        joined = processed.merge(vina[["compound_id", "vina_affinity", "pose_qc", "status"]], on="compound_id", how="left")
        joined["vina_utility"] = _percentile(joined["vina_affinity"], lower_is_better=True)
        joined["structure_model_utility"] = _percentile(joined["model_score"], lower_is_better=True)
        rule_cols = ["desc_mol_wt", "desc_logp", "desc_tpsa", "desc_hbd", "desc_hba", "desc_rotatable_bonds"]
        rules = ((joined["desc_mol_wt"] <= 500) & (joined["desc_logp"] <= 5) & (joined["desc_tpsa"] <= 140)
                 & (joined["desc_hbd"] <= 5) & (joined["desc_hba"] <= 10) & (joined["desc_rotatable_bonds"] <= 10))
        joined["property_rule_utility"] = rules.astype(float)
        joined["open_route_shadow_priority"] = (0.55 * joined["vina_utility"] +
                                                  0.30 * joined["structure_model_utility"] +
                                                  0.15 * joined["property_rule_utility"])
        joined.loc[joined["status"].ne("success"), "open_route_shadow_priority"] = np.nan
        joined["shadow_rank"] = joined["open_route_shadow_priority"].rank(method="min", ascending=False).astype("Int64")
        joined["frozen_decision_status"] = "unknown_missing_MMGBSA_Glide_QuickProp_ADMET"
        joined["interpretation"] = "shadow evidence-acquisition priority; not Model v3 full decision and not biological activity"
        columns = ["compound_id", "canonical_smiles", "vina_affinity", "pose_qc", "model_score", "model_used",
                   "vina_utility", "structure_model_utility", "property_rule_utility", "open_route_shadow_priority",
                   "shadow_rank", "frozen_decision_status", "missing_computational_fields", "interpretation"]
        panel = joined[columns].sort_values("shadow_rank", na_position="last")
        atomic_csv(panel, root / "candidate_panel.csv")
        return panel

    def run_smoke(self, target_unique: int, run_id: str, workers: int = 4) -> dict:
        manifest = self.generator.generate(target_unique, run_id)
        if manifest["status"] != "completed":
            raise RuntimeError("library_generation_not_complete")
        root = self.generator._run_dir(run_id)
        library_path = root / "library.csv"
        library = pd.read_csv(library_path, keep_default_na=False)
        vina, vina_summary = self._run_vina(run_id, library, workers)
        evidence_count = self._register_vina(run_id, library_path, vina)
        panel = self._shadow_decision(run_id, library, vina)
        stage_rows = [
            {"stage":"Target + IN-2", "tool_protocol":"registered 7P3W + confirmed IN-2", "status":"completed", "input_count":1, "output_count":1, "output":"parent manifest", "provenance":self.generator.parent["structure_hash"]},
            {"stage":"Library Generation", "tool_protocol":"RDKit reconstructed library v1", "status":"completed", "input_count":1, "output_count":len(library), "output":"library.csv", "provenance":manifest["library_hash"]},
            {"stage":"Preparation / Filtering", "tool_protocol":"RDKit sanitize + FragmentParent + rule/warning QC", "status":"completed", "input_count":manifest["counts"]["raw_processed"], "output_count":len(library), "output":"library.csv + rejections.csv", "provenance":manifest["config_hash"]},
            {"stage":"Docking", "tool_protocol":"AutoDock Vina vina_7p3w_v1", "status":"completed" if vina_summary["failed"] == 0 else "completed_with_failures", "input_count":len(library), "output_count":vina_summary["success"], "output":"vina_results.csv + registered poses", "provenance":vina_summary["protocol_hash"]},
            {"stage":"Refinement", "tool_protocol":"evidence-acquisition ranking only", "status":"completed_selection_only", "input_count":vina_summary["success"], "output_count":min(20, vina_summary["success"]), "output":"candidate_panel.csv", "provenance":"no additional physics score generated"},
            {"stage":"MM/GBSA", "tool_protocol":"open_mmgbsa_7p3w_v2", "status":"not_run_budget_confirmation_required", "input_count":min(20, vina_summary["success"]), "output_count":0, "output":"none", "provenance":"no simulated values"},
            {"stage":"Evidence Integration", "tool_protocol":"shared Evidence Registry", "status":"completed_partial_evidence", "input_count":vina_summary["success"], "output_count":evidence_count, "output":"workspace.sqlite3", "provenance":"tool-execution records"},
            {"stage":"AI Decision", "tool_protocol":"frozen structure model + transparent open-route shadow", "status":"partial_missing_required_evidence", "input_count":len(panel), "output_count":int(panel["open_route_shadow_priority"].notna().sum()), "output":"candidate_panel.csv", "provenance":"historical models unchanged"},
            {"stage":"Candidate Panel", "tool_protocol":"researcher-review gate", "status":"ready_for_evidence_acquisition_review", "input_count":len(panel), "output_count":min(10, int(panel["shadow_rank"].notna().sum())), "output":"candidate_panel.csv", "provenance":"not an experimental recommendation"},
        ]
        stages = pd.DataFrame(stage_rows)
        atomic_csv(stages, root / "workflow_stages.csv")
        summary = {"workflow":"reconstructed open reproducible workflow", "run_id":run_id,
                   "library_classification":manifest["classification"], "historical_library_equivalence":False,
                   "library":manifest, "vina":vina_summary, "evidence_records":evidence_count,
                   "full_model_v3_decision_available":False,
                   "decision_limitation":"required Glide/MMGBSA/complete QuickProp-ADMET evidence is unavailable for reconstructed structures",
                   "mmgbsa_executed":False, "training_performed":False, "stages":stage_rows}
        write_json(root / "workflow_summary.json", summary)
        public = {"updated_at":now(), "workflow_name":"IN-2 可复现开放虚拟筛选入口",
                  "scientific_scope":"重建衍生库与真实开放工具证据；不等同历史十万库", "run_id":run_id,
                  "stage_counts":stage_rows, "library_hash":manifest["library_hash"], "config_hash":manifest["config_hash"],
                  "protocol_id":VINA_PROTOCOL_ID, "outputs":{"workflow":str((root/"workflow_summary.json").relative_to(self.project)).replace("\\","/"),
                  "library":str(library_path.relative_to(self.project)).replace("\\","/"),
                  "candidate_panel":str((root/"candidate_panel.csv").relative_to(self.project)).replace("\\","/")}}
        write_json(self.project / "results/library_generation/workflow_public_summary.json", public)
        return summary
