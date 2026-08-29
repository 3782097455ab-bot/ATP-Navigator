"""Allowlisted Phase 18B actions. No action accepts shell, SQL or Python code."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Callable

import pandas as pd

from app.data_adapter import ProjectData
from workspace.state import State, encode, file_hash, now

from .structure_viewer import PoseRegistry


ACTION_QUERY_CANDIDATE = "ACTION_QUERY_CANDIDATE"
ACTION_QUERY_EVIDENCE = "ACTION_QUERY_EVIDENCE"
ACTION_QUERY_PROVENANCE = "ACTION_QUERY_PROVENANCE"
ACTION_COMPARE_PROTOCOL = "ACTION_COMPARE_PROTOCOL"
ACTION_DECISION_RANKING = "ACTION_DECISION_RANKING"
ACTION_RUN_ACQUISITION = "ACTION_RUN_ACQUISITION"
ACTION_CREATE_GENERATION_REQUEST = "ACTION_CREATE_GENERATION_REQUEST"
ACTION_CREATE_CALCULATION_PLAN = "ACTION_CREATE_CALCULATION_PLAN"
ACTION_JOB_STATUS = "ACTION_JOB_STATUS"
ACTION_MISSING_EVIDENCE = "ACTION_MISSING_EVIDENCE"
ACTION_TOOL_CAPABILITY = "ACTION_TOOL_CAPABILITY"
ACTION_PARENT_LINEAGE = "ACTION_PARENT_LINEAGE"
ACTION_EXPORT_PANEL = "ACTION_EXPORT_PANEL"


INTENT_TO_ACTION = {
    "candidate_query": ACTION_QUERY_CANDIDATE,
    "evidence_query": ACTION_QUERY_EVIDENCE,
    "provenance_query": ACTION_QUERY_PROVENANCE,
    "protocol_comparison": ACTION_COMPARE_PROTOCOL,
    "decision_ranking": ACTION_DECISION_RANKING,
    "acquisition": ACTION_RUN_ACQUISITION,
    "generation": ACTION_CREATE_GENERATION_REQUEST,
    "calculation_plan": ACTION_CREATE_CALCULATION_PLAN,
    "job_status": ACTION_JOB_STATUS,
    "missing_evidence": ACTION_MISSING_EVIDENCE,
    "tool_capability": ACTION_TOOL_CAPABILITY,
    "parent_lineage": ACTION_PARENT_LINEAGE,
    "export_request": ACTION_EXPORT_PANEL,
}


def _safe_candidate_ids(values: list[str]) -> list[str]:
    result = []
    for value in values:
        value = str(value).strip()
        if not value or len(value) > 120 or not all(char.isalnum() or char in "_-" for char in value):
            raise ValueError("Candidate identifiers must be exact IDs or aliases")
        result.append(value)
    return list(dict.fromkeys(result))


class ActionRegistry:
    """Maps audited action IDs to internal functions only."""

    def __init__(self, project: str | Path):
        self.project = Path(project).resolve()
        self.data = ProjectData(self.project)
        self.pose = PoseRegistry(self.project)
        self.actions: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
            ACTION_QUERY_CANDIDATE: self.query_candidate,
            ACTION_QUERY_EVIDENCE: self.query_evidence,
            ACTION_QUERY_PROVENANCE: self.query_provenance,
            ACTION_COMPARE_PROTOCOL: self.compare_protocol,
            ACTION_DECISION_RANKING: self.decision_ranking,
            ACTION_RUN_ACQUISITION: self.run_acquisition,
            ACTION_CREATE_GENERATION_REQUEST: self.generation_request,
            ACTION_CREATE_CALCULATION_PLAN: self.calculation_plan,
            ACTION_JOB_STATUS: self.job_status,
            ACTION_MISSING_EVIDENCE: self.missing_evidence,
            ACTION_TOOL_CAPABILITY: self.tool_capability,
            ACTION_PARENT_LINEAGE: self.parent_lineage,
            ACTION_EXPORT_PANEL: self.export_panel,
        }

    @property
    def allowlist(self) -> tuple[str, ...]:
        return tuple(sorted(self.actions))

    def execute(self, action_id: str, arguments: dict[str, Any]) -> dict[str, Any]:
        action = self.actions.get(action_id)
        if not action:
            raise ValueError("Action is not allowlisted")
        forbidden = {"shell", "bash", "powershell", "sql", "eval", "python_code", "command"}
        if forbidden & set(arguments):
            raise ValueError("Executable text is forbidden")
        return action(dict(arguments))

    def _resolve(self, values: list[str]) -> list[str]:
        master = self.data.candidate_master()
        resolved = []
        for token in _safe_candidate_ids(values):
            match = master.loc[
                master["compound_id"].astype(str).str.casefold().eq(token.casefold())
                | master["display_name"].astype(str).str.casefold().eq(token.casefold())
            ]
            if len(match) == 1:
                resolved.append(str(match.iloc[0]["compound_id"]))
        return list(dict.fromkeys(resolved))

    def _product_job(self, plan_id: str, tool_id: str, protocol_id: str, protocol: dict[str, Any],
                     input_path: Path, output_path: Path | None, status: str = "completed",
                     reason: str = "", candidate_id: str = "__panel__") -> str:
        """Register a real internal-engine/request action without registering scientific evidence."""
        state = State(self.project)
        project_id = state.project_id("atp_synthase")
        state.freeze_protocol({"protocol_id": protocol_id, **protocol})
        batch = state.batch(project_id, {"phase": "18B", "plan_id": plan_id, "tool_id": tool_id})
        source = state.artifact(input_path)
        job_id = state.job(
            batch,
            project_id,
            candidate_id,
            tool_id,
            protocol_id,
            [source],
            {"action": tool_id, "phase18b_plan_id": plan_id, "scientific_values_generated": False},
        )
        artifacts = [state.artifact(output_path)] if output_path and output_path.is_file() else []
        with state.connect() as db:
            db.execute(
                """UPDATE calculation_job SET status=?,started_at=?,completed_at=?,return_code=?,
                   output_artifacts=?,reason=?,attempt=1 WHERE job_id=?""",
                (status, now(), now(), 0 if status == "completed" else None, encode(artifacts), reason, job_id),
            )
        return job_id

    def query_candidate(self, args: dict[str, Any]) -> dict[str, Any]:
        candidates = self._resolve(args.get("candidate_scope", []))
        frame = self.data.candidate_master()
        if candidates:
            frame = frame.loc[frame["compound_id"].isin(candidates)]
        else:
            frame = frame.sort_values(["global_rank", "compound_id"], na_position="last").head(int(args.get("top_k", 10)))
        records = frame.to_dict("records")
        return {
            "status": "available" if records else "empty",
            "answer": "候选信息来自统一候选资产层；身份不按名称或历史排名猜测。",
            "records": records,
            "candidate_ids": [row["compound_id"] for row in records],
            "provenance": [{"source": "ProjectData.candidate_master"}],
        }

    def query_evidence(self, args: dict[str, Any]) -> dict[str, Any]:
        candidates = self._resolve(args.get("candidate_scope", []))
        matrix = self.data.evidence_matrix()
        if candidates:
            matrix = matrix.loc[matrix["compound_id"].isin(candidates)]
        records = matrix.head(100).to_dict("records")
        provenance = []
        for candidate in candidates[:20]:
            provenance.extend(self.data.provenance(candidate).head(20).to_dict("records"))
        return {
            "status": "available" if records else "empty",
            "answer": "available、missing、unknown 与 not_applicable 保持分开；缺失值不填0。",
            "records": records,
            "candidate_ids": candidates,
            "provenance": provenance,
        }

    def query_provenance(self, args: dict[str, Any]) -> dict[str, Any]:
        candidates = self._resolve(args.get("candidate_scope", []))
        records = []
        for candidate in candidates:
            records.extend(self.data.provenance(candidate).to_dict("records"))
        return {
            "status": "available" if records else "empty",
            "answer": "仅显示已登记来源、协议、job与artifact hash。",
            "records": records,
            "candidate_ids": candidates,
            "provenance": records,
        }

    def compare_protocol(self, args: dict[str, Any]) -> dict[str, Any]:
        frame, metrics = self.data.protocol_comparison()
        top_k = min(max(int(args.get("top_k", 10)), 1), 100)
        selected = frame.sort_values("abs_rank_delta", ascending=False).head(top_k) if not frame.empty else frame
        return {
            "status": "available" if not selected.empty else "empty",
            "answer": f"以下为 Glide/Vina 排名分歧最大的 {len(selected)} 个候选。协议分歧不是生物活性结论。",
            "records": selected.to_dict("records"),
            "candidate_ids": selected.get("canonical_id", pd.Series(dtype=str)).astype(str).tolist(),
            "provenance": [metrics, {"source": "results/phase14/glide_vina_protocol_disagreement.csv"}],
        }

    def decision_ranking(self, args: dict[str, Any]) -> dict[str, Any]:
        profile = str(args.get("profile", "balanced"))
        top_k = min(max(int(args.get("top_k", 10)), 1), 100)
        frame = self.data.decision_ranking(profile)
        candidates = self._resolve(args.get("candidate_scope", []))
        if candidates:
            frame = frame.loc[frame["compound_id"].astype(str).isin(candidates)]
        frame = frame.head(top_k)
        return {
            "status": "available" if not frame.empty else "empty",
            "answer": f"读取冻结 Decision Engine 的 {profile} 排名；没有重新训练或改写评分。",
            "records": frame.to_dict("records"),
            "candidate_ids": frame.get("compound_id", pd.Series(dtype=str)).astype(str).tolist(),
            "provenance": [{"source": "results/phase10_workflow/profile_comparison.csv", "profile": profile}],
        }

    def run_acquisition(self, args: dict[str, Any]) -> dict[str, Any]:
        budget = min(max(int(args.get("budget", 20)), 1), 100)
        selected_scope = self._resolve(args.get("candidate_scope", []))
        # When a previous conversational turn has established a candidate scope,
        # rank that whole scope before applying the new budget.  Asking for five
        # candidates "from here" must not mean filtering a pre-truncated global
        # top-five list, which could silently discard the selected context.
        source_budget = 100 if selected_scope else budget
        frame = self.data.acquisition_recommendations(
            str(args.get("strategy", "ATP_Navigator_hybrid")), source_budget
        )
        if selected_scope:
            scoped = frame.loc[frame["canonical_id"].isin(selected_scope)]
            frame = scoped.head(budget)
        plan_id = str(args["plan_id"])
        output = self.project / "workspace_local/phase18b/plans" / plan_id
        output.mkdir(parents=True, exist_ok=False)
        path = output / "acquisition_panel.csv"
        frame.to_csv(path, index=False, encoding="utf-8-sig")
        candidates = frame["canonical_id"].astype(str).tolist()
        cached_jobs: list[dict[str, Any]] = []
        database = self.project / "workspace_local/workspace.sqlite3"
        with sqlite3.connect(database) as db:
            db.row_factory = sqlite3.Row
            for candidate in candidates:
                row = db.execute(
                    """SELECT job_id,status,protocol_id,completed_at FROM calculation_job
                       WHERE candidate_id=? AND tool_id='open_mmgbsa'
                       ORDER BY completed_at DESC LIMIT 1""",
                    (candidate,),
                ).fetchone()
                if row:
                    cached_jobs.append(dict(row))
        action_job = self._product_job(
            plan_id,
            "acquisition_engine",
            "phase18b_acquisition_v1",
            {
                "source_policy": "configs/acquisition_phase15.json",
                "strategy": "ATP_Navigator_hybrid",
                "output_semantics": "evidence acquisition priority; not activity",
                "training": False,
            },
            self.project / "results/phase15/acquisition_panel_v1.csv",
            path,
        )
        return {
            "status": "completed",
            "answer": f"已按冻结 hybrid 获取策略形成 {len(frame)} 个候选的版本化面板。",
            "records": frame.to_dict("records"),
            "candidate_ids": candidates,
            "job_ids": [action_job, *[row["job_id"] for row in cached_jobs]],
            "cached_real_jobs": cached_jobs,
            "artifact": str(path),
            "artifact_hash": file_hash(path),
            "evidence_generated": [],
            "warning": "获取分数不是活性概率；本动作没有启动新的高成本计算。",
        }

    def generation_request(self, args: dict[str, Any]) -> dict[str, Any]:
        candidates = self._resolve(args.get("candidate_scope", []))
        if not candidates:
            return {"status": "blocked", "reason": "exact_seed_candidate_required", "required_dependency": "select a registered seed"}
        plan_id = str(args["plan_id"])
        output = self.project / "workspace_local/phase18b/requests"
        output.mkdir(parents=True, exist_ok=True)
        path = output / f"{plan_id}_generation.json"
        payload = {
            "request_id": plan_id,
            "seed_candidates": candidates,
            "requested_count": min(max(int(args.get("n", 30)), 1), 500),
            "preserve_scaffold": bool(args.get("preserve_scaffold", False)),
            "backend": "rdkit_rgroup_enumeration",
            "status": "versioned_request_created_not_executed",
            "scientific_values_generated": False,
            "training": False,
        }
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        action_job = self._product_job(
            plan_id,
            "generation_request",
            "phase18b_generation_request_v1",
            {"backend": "rdkit_rgroup_enumeration", "execution": "request_only", "training": False},
            self.project / "results/phase16/generated_candidate_registry.csv",
            path,
            candidate_id=candidates[0],
        )
        return {"status": "completed", "answer": "已创建可追溯生成请求；没有覆盖或执行冻结 Phase16。", "records": [payload], "candidate_ids": candidates, "job_ids": [action_job], "artifact": str(path), "artifact_hash": file_hash(path)}

    def calculation_plan(self, args: dict[str, Any]) -> dict[str, Any]:
        candidates = self._resolve(args.get("candidate_scope", []))
        protocol = str(args.get("protocol") or "open_mmgbsa_7p3w_v2")
        database = self.project / "workspace_local/workspace.sqlite3"
        cached = []
        with sqlite3.connect(database) as db:
            db.row_factory = sqlite3.Row
            for candidate in candidates:
                row = db.execute(
                    "SELECT job_id,status,protocol_id,completed_at FROM calculation_job WHERE candidate_id=? AND protocol_id=? ORDER BY completed_at DESC LIMIT 1",
                    (candidate, protocol),
                ).fetchone()
                if row:
                    cached.append(dict(row))
        if candidates and len(cached) == len(candidates) and all(row["status"] == "completed" for row in cached):
            return {"status": "completed_cached", "answer": "所选候选已有同协议真实注册结果；复用缓存，不重复计算。", "candidate_ids": candidates, "job_ids": [row["job_id"] for row in cached], "cached_real_jobs": cached, "evidence_generated": []}
        checkpoint = self.project / "workspace_local/phase17_1/checkpoint.json"
        active = {}
        if checkpoint.is_file():
            active = json.loads(checkpoint.read_text(encoding="utf-8"))
        plan_id = str(args["plan_id"])
        blocked_job = self._product_job(
            plan_id,
            "open_mmgbsa",
            "phase18b_calculation_request_v1",
            {
                "requested_scientific_protocol": protocol,
                "execution": "capability_and_active-batch_gate_only",
                "scientific_values_generated": False,
            },
            self.project / "results/phase17_1/open_mmgbsa_7p3w_v2.json",
            None,
            status="blocked",
            reason="active_gated_high_cost_batch" if active.get("status") == "running" else "general_open_mmgbsa_execution_adapter_not_released",
            candidate_id=candidates[0] if candidates else "__phase18b_request__",
        )
        return {
            "status": "blocked",
            "reason": "active_gated_high_cost_batch" if active.get("status") == "running" else "general_open_mmgbsa_execution_adapter_not_released",
            "required_dependency": "complete the active frozen batch and explicitly approve a versioned candidate/protocol execution adapter",
            "candidate_ids": candidates,
            "job_ids": [blocked_job, *[row["job_id"] for row in cached]],
            "scientific_values_generated": False,
        }

    def job_status(self, args: dict[str, Any]) -> dict[str, Any]:
        jobs = self.data.jobs()
        if jobs.empty:
            return {"status": "empty", "answer": "没有登记任务。", "records": [], "candidate_ids": []}
        active = jobs.loc[jobs["status"].astype(str).isin(["planned", "ready", "running", "blocked", "failed"])]
        return {"status": "available", "answer": "任务状态来自共享 Calculation Job Registry。", "records": active.head(100).to_dict("records"), "candidate_ids": active["candidate_id"].dropna().astype(str).tolist(), "provenance": [{"source": "workspace.sqlite3/calculation_job"}]}

    def missing_evidence(self, args: dict[str, Any]) -> dict[str, Any]:
        matrix = self.data.evidence_matrix()
        candidates = self._resolve(args.get("candidate_scope", []))
        if candidates:
            matrix = matrix.loc[matrix["compound_id"].isin(candidates)]
        evidence = [column for column in ["glide", "vina", "mmgbsa", "admet", "literature_prior", "experiment"] if column in matrix]
        records = [{"evidence_type": column, **matrix[column].value_counts().to_dict()} for column in evidence]
        return {"status": "available", "answer": "证据缺口来自统一矩阵；这是 provenance/data completeness QC，不是生物安全或临床结论。", "records": records, "candidate_ids": candidates, "provenance": [{"source": "ProjectData.evidence_matrix"}]}

    def tool_capability(self, args: dict[str, Any]) -> dict[str, Any]:
        frame = self.data.capabilities()
        manifest = self.project / "results/phase17_1/backend_certification.json"
        extra = []
        if manifest.is_file():
            payload = json.loads(manifest.read_text(encoding="utf-8"))
            extra.append({"tool_id": "open_mmgbsa_7p3w_v2", "status": payload.get("status", "certified"), "version": "OpenMM 8.6.0 + gmx_MMPBSA 1.6.5", "reason": "qualification/pilot remains stage-gated", "source": "phase17_1 certification"})
        records = [*frame.to_dict("records"), *extra]
        return {"status": "available", "answer": "能力状态来自实际探测；不可用后端不会生成模拟结果。", "records": records, "candidate_ids": [], "provenance": [{"source": "capability manifests"}]}

    def parent_lineage(self, args: dict[str, Any]) -> dict[str, Any]:
        candidates = self._resolve(args.get("candidate_scope", []))
        frame = self.data.generated_registry()
        if candidates:
            frame = frame.loc[frame["compound_id"].isin(candidates) | frame.get("parent_id", pd.Series(index=frame.index)).isin(candidates)]
        records = frame.head(100).to_dict("records")
        return {"status": "available" if records else "empty", "answer": "谱系来自 Phase16 GeneratedCandidateRegistry。", "records": records, "candidate_ids": frame.get("compound_id", pd.Series(dtype=str)).astype(str).tolist(), "provenance": [{"source": "results/phase16/generated_candidate_registry.csv"}]}

    def export_panel(self, args: dict[str, Any]) -> dict[str, Any]:
        candidates = self._resolve(args.get("candidate_scope", []))
        frame = self.data.candidate_master()
        if candidates:
            frame = frame.loc[frame["compound_id"].isin(candidates)]
        plan_id = str(args["plan_id"])
        output = self.project / "workspace_local/phase18b/exports"
        output.mkdir(parents=True, exist_ok=True)
        path = output / f"{plan_id}.csv"
        frame.to_csv(path, index=False, encoding="utf-8-sig")
        action_job = self._product_job(
            plan_id,
            "export_service",
            "phase18b_export_v1",
            {"format": "csv", "source": "registered candidate master", "scientific_values_generated": False},
            self.project / "results/phase14/full_library_vina_ranking.csv",
            path,
        )
        return {"status": "completed", "answer": f"已导出 {len(frame)} 条候选记录。", "records": frame.head(100).to_dict("records"), "candidate_ids": frame["compound_id"].astype(str).tolist(), "job_ids": [action_job], "artifact": str(path), "artifact_hash": file_hash(path)}
