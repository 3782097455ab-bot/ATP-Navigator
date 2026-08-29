"""Read-only adapters from frozen ATP-Navigator artifacts to the Phase 18A UI.

This module never retrains a model, changes a scientific protocol, or interprets
missing evidence as zero. It makes the existing registries and versioned results
queryable without creating a second scientific data store.
"""
from __future__ import annotations

import json
import sqlite3
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
from rdkit import Chem
from rdkit.Chem import Descriptors

from acquisition.engine import AcquisitionEngine
from experimental_feedback import FeedbackStore


UNKNOWN = "unknown"


def _read_csv(path: Path, **kwargs) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path, low_memory=False, **kwargs)


def _read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return {} if default is None else default
    return json.loads(path.read_text(encoding="utf-8"))


def _first(frame: pd.DataFrame, names: list[str], default=UNKNOWN):
    for name in names:
        if name in frame.columns:
            return frame[name]
    return pd.Series(default, index=frame.index)


class ProjectData:
    """One access layer for Phase 0-17 scientific artifacts."""

    def __init__(self, project: str | Path):
        self.project = Path(project).resolve()
        self.results = self.project / "results"
        self.runtime = self.project / "workspace_local"

    def historical_candidates(self) -> pd.DataFrame:
        frame = _read_csv(self.results / "phase14/full_library_vina_ranking.csv")
        if frame.empty:
            return frame
        frame = frame.rename(columns={"canonical_id": "compound_id"})
        frame["candidate_source"] = "HTVS 1633"
        frame["display_name"] = frame["compound_id"]
        frame["identity_status"] = "registered_htvs_structure"
        return frame

    def generated_candidates(self) -> pd.DataFrame:
        frame = _read_csv(self.results / "phase16/generated_candidate_registry.csv")
        if frame.empty:
            return frame
        for identifier in ["generated_candidate_id", "generated_id"]:
            if identifier in frame.columns and "compound_id" not in frame.columns:
                frame = frame.rename(columns={identifier: "compound_id"})
        if "parent_candidate_id" in frame.columns and "parent_id" not in frame.columns:
            frame = frame.rename(columns={"parent_candidate_id": "parent_id"})
        frame["candidate_source"] = "Phase 16 generated"
        frame["display_name"] = frame["compound_id"]
        frame["identity_status"] = "generated_structure"
        return frame

    def internal_candidates(self) -> pd.DataFrame:
        frame = _read_csv(self.project / "data/model_v3/training_table.csv")
        if frame.empty:
            return frame
        keep = [column for column in ["compound_id", "canonical_smiles", "docking_score", "mmgbsa_score", "source"] if column in frame]
        frame = frame[keep].drop_duplicates("compound_id").copy()
        audit = _read_csv(self.results / "phase14_1/internal17_identity_audit.csv")
        if not audit.empty:
            audit = audit.rename(columns={"query_compound_id": "compound_id", "query_id": "historical_alias"})
            cols = [column for column in ["compound_id", "historical_alias", "matched_htvs_id", "identity_relation", "exact_match", "confidence", "evidence_source", "notes"] if column in audit]
            frame = frame.merge(audit[cols], on="compound_id", how="left")
        frame["candidate_source"] = "Internal 17"
        frame["display_name"] = frame.get("historical_alias", frame["compound_id"])
        frame["identity_status"] = frame.get("identity_relation", "unresolved").fillna("unresolved")
        return frame

    def candidate_master(self) -> pd.DataFrame:
        frames: list[pd.DataFrame] = []
        for frame in (self.historical_candidates(), self.generated_candidates(), self.internal_candidates()):
            if frame.empty:
                continue
            selected = pd.DataFrame(index=frame.index)
            selected["compound_id"] = frame["compound_id"].astype(str)
            selected["display_name"] = _first(frame, ["display_name", "historical_alias", "compound_id"])
            selected["canonical_smiles"] = _first(frame, ["canonical_smiles"])
            selected["scaffold"] = _first(frame, ["scaffold", "murcko_scaffold"])
            selected["candidate_source"] = frame["candidate_source"]
            selected["identity_status"] = _first(frame, ["identity_status"])
            selected["vina_affinity"] = pd.to_numeric(_first(frame, ["vina_affinity"]), errors="coerce")
            selected["global_rank"] = pd.to_numeric(_first(frame, ["global_rank"]), errors="coerce")
            selected["docking_score"] = pd.to_numeric(_first(frame, ["glide_docking_score", "docking_score"]), errors="coerce")
            selected["mmgbsa_score"] = pd.to_numeric(_first(frame, ["mmgbsa_score"]), errors="coerce")
            selected["parent_id"] = _first(frame, ["parent_id", "parent_compound_id"])
            frames.append(selected)
        return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

    def _phase13_internal_vina_ids(self) -> set[str]:
        candidates: set[str] = set()
        for path in [self.results / "phase13/internal_17_results.csv", self.results / "phase13/internal17_vina_results.csv"]:
            frame = _read_csv(path)
            if not frame.empty:
                for column in ["compound_id", "candidate_id"]:
                    if column in frame:
                        candidates.update(frame[column].dropna().astype(str))
        return candidates

    def evidence_matrix(self) -> pd.DataFrame:
        master = self.candidate_master()
        if master.empty:
            return master
        generated_vina = _read_csv(self.results / "phase16/generated_vina_results.csv")
        generated_vina_ids: set[str] = set()
        if not generated_vina.empty:
            id_col = next((c for c in ["generated_candidate_id", "candidate_id", "compound_id"] if c in generated_vina), None)
            status = generated_vina.get("status", pd.Series("success", index=generated_vina.index)).astype(str)
            generated_vina_ids = set(generated_vina.loc[status.eq("success"), id_col].astype(str)) if id_col else set()
        internal_vina_ids = self._phase13_internal_vina_ids()
        open_mmgbsa_ids: set[str] = set()
        database = self.runtime / "workspace.sqlite3"
        if database.is_file():
            with sqlite3.connect(database) as connection:
                try:
                    open_mmgbsa_ids = {
                        str(row[0])
                        for row in connection.execute(
                            """SELECT DISTINCT compound_id FROM evidence
                               WHERE protocol_id='open_mmgbsa_7p3w_v2'
                               AND evidence_type='open_mmgbsa_deltaG'"""
                        )
                    }
                except Exception:
                    open_mmgbsa_ids = set()
        rows = []
        for record in master.to_dict("records"):
            source, cid = record["candidate_source"], record["compound_id"]
            if source == "HTVS 1633":
                values = dict(structure="available", glide="available", vina="available", mmgbsa="available" if cid in open_mmgbsa_ids else "missing",
                              admet="partial_property_only", literature_prior="missing", lineage="not_applicable", experiment="missing")
            elif source == "Phase 16 generated":
                values = dict(structure="available", glide="not_applicable", vina="available" if cid in generated_vina_ids else "missing",
                              mmgbsa="available" if cid in open_mmgbsa_ids else "missing", admet="partial_property_only", literature_prior="missing", lineage="available", experiment="missing")
            else:
                values = dict(structure="available", glide="available", vina="available" if cid in internal_vina_ids else "unknown",
                              mmgbsa="available" if pd.notna(record.get("mmgbsa_score")) else "missing",
                              admet="partial_property_only", literature_prior="available", lineage="not_applicable", experiment="missing")
            rows.append({"compound_id": cid, "source": source, **values})
        return pd.DataFrame(rows)

    def provenance(self, compound_id: str) -> pd.DataFrame:
        master = self.candidate_master()
        found = master.loc[master["compound_id"].eq(str(compound_id))]
        if found.empty:
            return pd.DataFrame()
        source = found.iloc[0]["candidate_source"]
        if source == "HTVS 1633":
            registry = _read_csv(self.results / "phase14/evidence_registry_export.csv")
            if not registry.empty:
                return registry.loc[registry["compound_id"].astype(str).eq(str(compound_id))].copy()
        if source == "Phase 16 generated":
            frame = self.generated_candidates()
            row = frame.loc[frame["compound_id"].astype(str).eq(str(compound_id))]
            return row.assign(evidence_type="generated_structure_and_lineage", protocol_id="phase16_registry",
                              source_job_id="not_applicable", artifact_hash=UNKNOWN)
        row = self.internal_candidates().loc[lambda x: x["compound_id"].astype(str).eq(str(compound_id))]
        return row.assign(evidence_type="frozen_internal_computational_record", protocol_id="historical_internal",
                          source_job_id="historical_import", artifact_hash=UNKNOWN)

    def candidate_detail(self, compound_id: str) -> dict:
        frame = self.candidate_master()
        row = frame.loc[frame["compound_id"].eq(str(compound_id))]
        if row.empty:
            return {}
        result = row.iloc[0].to_dict()
        smiles = str(result.get("canonical_smiles") or "")
        mol = Chem.MolFromSmiles(smiles)
        result["inchikey"] = Chem.MolToInchiKey(mol) if mol else UNKNOWN
        if mol:
            result.update(molecular_weight=round(Descriptors.MolWt(mol), 3), logp=round(Descriptors.MolLogP(mol), 3),
                          tpsa=round(Descriptors.TPSA(mol), 3), hbd=Descriptors.NumHDonors(mol), hba=Descriptors.NumHAcceptors(mol))
        return result

    def decision_ranking(self, profile: str = "balanced") -> pd.DataFrame:
        profiles = _read_csv(self.results / "phase10_workflow/profile_comparison.csv")
        details = _read_csv(self.results / "final_navigation_report.csv")
        if profiles.empty:
            return details
        chosen = profiles.loc[profiles["profile"].astype(str).eq(profile)].copy()
        join_cols = [column for column in ["compound_id", "binding_score", "ATP_score", "antibacterial_score", "drug_score", "risk", "decision_confidence", "evidence_coverage", "experimental_activity_status"] if column in details]
        if join_cols:
            chosen = chosen.merge(details[join_cols].drop_duplicates("compound_id"), on="compound_id", how="left")
        return chosen.sort_values("rank")

    def acquisition_recommendations(self, strategy: str, budget: int) -> pd.DataFrame:
        engine = AcquisitionEngine(self.project)
        frame, _ = engine.build_features()
        orders = engine._strategy_orders(frame)  # exact frozen Phase 15 strategy ordering
        if strategy not in orders:
            raise ValueError(f"Unknown acquisition strategy: {strategy}")
        ids = orders[strategy][: int(budget)]
        columns = ["canonical_id", "vina_rank", "glide_rank", "rank_delta", "protocol_uncertainty", "evidence_uncertainty",
                   "chemical_space_uncertainty", "distance_to_decision_boundary", "voi_proxy", "recommended_next_evidence", "scaffold"]
        selected = frame.set_index("canonical_id").loc[ids].reset_index()[columns]
        selected.insert(0, "selection_order", range(1, len(selected) + 1))
        selected["strategy"] = strategy
        panel = _read_csv(self.results / "phase15/acquisition_panel_v1.csv")
        if not panel.empty:
            extra = [c for c in ["canonical_id", "acquisition_class", "why_selected"] if c in panel]
            selected = selected.merge(panel[extra], on="canonical_id", how="left")
        selected["selection_reason"] = selected.get("why_selected", pd.Series(index=selected.index, dtype=object)).fillna(
            "selected by the frozen Phase 15 strategy ordering; this is not an activity probability")
        return selected

    def protocol_comparison(self) -> tuple[pd.DataFrame, dict]:
        frame = _read_csv(self.results / "phase14/glide_vina_protocol_disagreement.csv")
        metrics = _read_json(self.results / "phase14/glide_vina_protocol_metrics.json")
        return frame, metrics

    def jobs(self) -> pd.DataFrame:
        database = self.runtime / "workspace.sqlite3"
        if not database.exists():
            return pd.DataFrame()
        with sqlite3.connect(database) as connection:
            try:
                return pd.read_sql_query("SELECT * FROM calculation_job ORDER BY created_at DESC", connection)
            except Exception:
                return pd.DataFrame()

    def capabilities(self) -> pd.DataFrame:
        rows: list[dict] = []
        system = _read_json(self.results / "system_capabilities.json")
        payload = system.get("tools", system.get("capabilities", system)) if isinstance(system, dict) else {}
        if isinstance(payload, dict):
            for tool_id, value in payload.items():
                value = value if isinstance(value, dict) else {"status": value}
                rows.append({"tool_id": tool_id, "status": value.get("status", value.get("availability", UNKNOWN)),
                             "version": value.get("version", UNKNOWN), "reason": value.get("reason", value.get("blocking_reason", "")), "source": "system_capabilities"})
        phase17 = _read_json(self.results / "phase17/high_cost_backend_status.json").get("backends", {})
        for tool_id, value in phase17.items():
            rows.append({"tool_id": tool_id, "status": "available" if value.get("usable") else "unavailable",
                         "version": value.get("version", UNKNOWN), "reason": value.get("blocking_reason", ""), "source": "phase17_capability_gate"})
        phase17_1 = _read_json(self.results / "phase17_1/backend_certification.json")
        if phase17_1:
            rows.append({
                "tool_id": "open_mmgbsa_7p3w_v2",
                "status": phase17_1.get("status", "available"),
                "version": "OpenMM 8.6.0 + gmx_MMPBSA 1.6.5",
                "reason": "stage-gated WSL qualification/pilot backend",
                "source": "phase17_1_backend_certification",
            })
        phase16 = _read_json(self.results / "phase16/generator_backend_status.json")
        generator_values = phase16.get("backends", []) if isinstance(phase16, dict) else []
        if isinstance(generator_values, dict):
            generator_values = [{"generator_id": key, **(value if isinstance(value, dict) else {"status": value})} for key, value in generator_values.items()]
        for value in generator_values:
            if isinstance(value, dict):
                tool_id = value.get("generator_id", UNKNOWN)
                rows.append({"tool_id": f"generator:{tool_id}", "status": value.get("status", "available" if value.get("available") else "unavailable"),
                             "version": value.get("version", UNKNOWN), "reason": value.get("reason", ""), "source": "phase16_generator_gate"})
        return pd.DataFrame(rows).drop_duplicates(["tool_id", "source"]) if rows else pd.DataFrame(columns=["tool_id", "status", "version", "reason", "source"])

    def feedback_status(self) -> dict:
        try:
            return FeedbackStore(self.project).status()
        except Exception as error:
            return {"status": "unavailable", "reason": str(error), "training_performed": False}

    def git_state(self) -> dict:
        def run(*args: str) -> str:
            result = subprocess.run(["git", *args], cwd=self.project, capture_output=True, text=True, timeout=10)
            return result.stdout.strip() if result.returncode == 0 else UNKNOWN
        return {"commit": run("rev-parse", "--short", "HEAD"), "branch": run("branch", "--show-current"),
                "status": run("status", "--short"), "timestamp": datetime.now(timezone.utc).isoformat()}

    def timeline(self) -> pd.DataFrame:
        result = subprocess.run(["git", "log", "--date=short", "--pretty=format:%ad|%h|%s"], cwd=self.project,
                                capture_output=True, text=True, timeout=10)
        rows = []
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                parts = line.split("|", 2)
                if len(parts) == 3:
                    rows.append(dict(date=parts[0], commit=parts[1], change=parts[2]))
        return pd.DataFrame(rows)

    def dashboard_metrics(self) -> dict:
        historical = self.historical_candidates()
        generated = self.generated_candidates()
        generated_vina = _read_csv(self.results / "phase16/generated_vina_results.csv")
        jobs = self.jobs()
        status = jobs.get("status", pd.Series(dtype=str)).astype(str) if not jobs.empty else pd.Series(dtype=str)
        caps = self.capabilities()
        available = int(caps["status"].astype(str).str.lower().isin({"available", "usable"}).sum()) if not caps.empty else 0
        return {"historical_candidates": len(historical), "generated_candidates": len(generated),
                "internal_candidates": len(self.internal_candidates()), "historical_vina_evidence": int(historical["vina_affinity"].notna().sum()) if not historical.empty else 0,
                "generated_vina_evidence": len(generated_vina), "active_jobs": int(status.isin(["planned", "ready", "running", "awaiting_confirmation"]).sum()),
                "failed_jobs": int(status.eq("failed").sum()), "available_tools": available, "registered_tools": len(caps),
                "acquisition_panel": len(_read_csv(self.results / "phase15/acquisition_panel_v1.csv")),
                "generated_acquisition_panel": len(_read_csv(self.results / "phase16/generated_acquisition_panel_v1.csv"))}

    def generated_registry(self) -> pd.DataFrame:
        return self.generated_candidates()

    def phase_snapshot(self) -> dict:
        return {"metrics": self.dashboard_metrics(), "git": self.git_state(),
                "feedback": self.feedback_status(), "scientific_scope": "pre-experimental computational evidence integration and candidate prioritization"}
