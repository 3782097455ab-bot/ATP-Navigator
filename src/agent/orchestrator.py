"""Natural language -> allowlisted action -> preview -> confirmation -> execution."""
from __future__ import annotations

import hashlib
import json
import uuid
from pathlib import Path
from typing import Any

from .actions import INTENT_TO_ACTION, ActionRegistry
from .collaboration import CollaborationStore
from .models import CONFIRMATION_INTENTS, ExecutionPlan, ParsedIntent
from .providers import IntentProvider, RuleBasedProvider


SCIENTIFIC_CAVEATS = [
    "Computational ranking and protocol agreement are not biological activity.",
    "Unknown experimental fields remain unknown and are never filled with invented values.",
    "The LLM, if configured, may parse intent or explain registered results but cannot create scientific numbers.",
]


class ConversationalOrchestrator:
    def __init__(self, project: str | Path, provider: IntentProvider | None = None,
                 collaboration: CollaborationStore | None = None):
        self.project = Path(project).resolve()
        self.store = collaboration or CollaborationStore(self.project)
        self.provider = provider or RuleBasedProvider()
        self.actions = ActionRegistry(self.project)

    def new_session(self, reviewer: str = "researcher", project_id: str = "atp_synthase") -> str:
        return self.store.create_session(project_id=project_id, reviewer=reviewer)

    def _arguments(self, intent: ParsedIntent, plan_id: str | None = None) -> dict[str, Any]:
        arguments = {
            "candidate_scope": list(intent.candidate_scope),
            **intent.constraints,
        }
        if intent.budget is not None:
            arguments["budget"] = int(intent.budget)
        if intent.protocol:
            arguments["protocol"] = intent.protocol
        if plan_id:
            arguments["plan_id"] = plan_id
        return arguments

    def _preview(self, session_id: str, intent: ParsedIntent) -> ExecutionPlan:
        session = self.store.session(session_id)
        plan_id = "plan_" + uuid.uuid4().hex[:18]
        action_id = INTENT_TO_ACTION[intent.operation]
        requested = int(intent.budget or intent.constraints.get("n", 0) or 0)
        candidate_count = min(len(intent.candidate_scope), requested) if intent.candidate_scope and requested else (len(intent.candidate_scope) or requested)
        backend = {
            "acquisition": "Phase15 ATP_Navigator_hybrid + shared Job Registry cache lookup",
            "generation": "versioned RDKit generation request (execution not implicit)",
            "calculation_plan": intent.protocol or "registered backend selected by protocol",
            "export_request": "audited local export service",
        }[intent.operation]
        runtime = {
            "acquisition": "seconds; selection only, no high-cost calculation",
            "generation": "seconds; request creation only",
            "calculation_plan": "unknown until capability/protocol gate; no task starts before confirmation",
            "export_request": "seconds",
        }[intent.operation]
        changes = {
            "acquisition": ["workspace_local/phase18b/plans/<plan_id>/acquisition_panel.csv", "CollaborationStore plan/events"],
            "generation": ["workspace_local/phase18b/requests/<plan_id>_generation.json", "CollaborationStore plan/events"],
            "calculation_plan": ["CollaborationStore plan/events; Job Registry only if an audited adapter is ready"],
            "export_request": ["workspace_local/phase18b/exports/<plan_id>.csv", "CollaborationStore plan/events"],
        }[intent.operation]
        evidence = [] if intent.operation != "calculation_plan" else [
            "only real tool evidence after a registered completed job; otherwise blocked"
        ]
        return ExecutionPlan(
            plan_id=plan_id,
            session_id=session_id,
            project_id=session["project_id"],
            action_id=action_id,
            intent=intent.as_dict(),
            what_will_happen={
                "acquisition": "Select and version candidates using the frozen acquisition strategy; link cached real jobs where available.",
                "generation": "Create a versioned molecule-generation request without executing or overwriting Phase16.",
                "calculation_plan": "Check exact candidate, protocol and backend readiness; use cached real results or return a blocked reason.",
                "export_request": "Export the selected registered candidate set with no scientific recomputation.",
            }[intent.operation],
            candidate_count=candidate_count,
            tool_backend=backend,
            protocol=intent.protocol or "not_applicable",
            estimated_runtime=runtime,
            estimated_resource_level="low" if intent.operation != "calculation_plan" else "capability-dependent",
            evidence_generated=evidence,
            files_or_records_changed=changes,
            scientific_caveats=SCIENTIFIC_CAVEATS,
        )

    def handle(self, session_id: str, message: str) -> dict[str, Any]:
        session = self.store.session(session_id)
        context = session["context"]
        self.store.event(session["project_id"], "user_message", {"text": message}, session_id=session_id)
        intent = self.provider.parse(message, context)
        if intent.operation not in INTENT_TO_ACTION:
            raise ValueError("Intent is not mapped to an allowlisted action")
        if intent.constraints.get("clarification_required"):
            result = {
                "status": "clarification_required",
                "answer": "请说明要查询的候选、证据、协议比较、预算、生成任务或导出内容。",
                "supported_intents": sorted(INTENT_TO_ACTION),
                "intent": intent.as_dict(),
            }
            self.store.event(session["project_id"], "assistant_result", result, session_id=session_id)
            return result
        self.store.update_context(
            session_id,
            last_intent=intent.as_dict(),
            current_budget=intent.budget,
        )
        if intent.operation in CONFIRMATION_INTENTS:
            plan = self._preview(session_id, intent)
            self.store.save_plan(plan.as_dict())
            return {
                "status": "confirmation_required",
                "answer": "计划已生成。确认前不会写入 Job Registry、启动工具或创建生成结果。",
                "plan": plan.as_dict(),
                "confirm_with": plan.plan_id,
                "intent": intent.as_dict(),
            }
        action_id = INTENT_TO_ACTION[intent.operation]
        result = self.actions.execute(action_id, self._arguments(intent))
        candidates = list(result.get("candidate_ids", []))
        self.store.update_context(
            session_id,
            selected_candidate_set=candidates,
            last_result_summary={"status": result.get("status"), "candidate_count": len(candidates), "action_id": action_id},
        )
        self.store.event(
            session["project_id"],
            "assistant_registry_answer",
            {"action_id": action_id, "status": result.get("status"), "candidate_ids": candidates},
            session_id=session_id,
        )
        return {**result, "intent": intent.as_dict(), "action_id": action_id}

    def confirm(self, session_id: str, plan_id: str) -> dict[str, Any]:
        plan = self.store.plan(plan_id)
        if plan["session_id"] != session_id:
            raise ValueError("Plan belongs to another research session")
        if plan["status"] != "pending_confirmation":
            return {"status": plan["status"], "result": plan["result"], "plan_id": plan_id}
        self.store.mark_plan(plan_id, "confirmed")
        intent = ParsedIntent(**plan["intent"])
        try:
            result = self.actions.execute(plan["action_id"], self._arguments(intent, plan_id=plan_id))
            terminal = "blocked" if result.get("status") == "blocked" else "completed"
        except Exception as error:
            result = {"status": "failed", "error": type(error).__name__, "reason": str(error)}
            terminal = "failed"
        self.store.mark_plan(plan_id, terminal, result)
        candidates = list(result.get("candidate_ids", []))
        self.store.update_context(
            session_id,
            selected_candidate_set=candidates,
            last_result_summary={"status": result.get("status"), "candidate_count": len(candidates), "plan_id": plan_id},
        )
        for candidate in candidates:
            self.store.event(
                plan["project_id"],
                "confirmed_action_result",
                {"plan_id": plan_id, "action_id": plan["action_id"], "status": result.get("status"), "job_ids": result.get("job_ids", [])},
                session_id=session_id,
                candidate_id=candidate,
            )
        return {
            **result,
            "plan_id": plan_id,
            "plan_status": terminal,
            "what_changed": result.get("artifact", "CollaborationStore plan/event records"),
            "new_evidence": result.get("evidence_generated", []),
            "ranking_impact": "not_recomputed" if plan["action_id"] != "ACTION_DECISION_RANKING" else "registry_backed",
            "uncertainty_impact": "not_claimed_without_new_registered_evidence",
            "next_recommended_action": "review the selected panel and registered provenance",
            "provenance": result.get("provenance", []),
        }

    def evidence_snapshot_hash(self, candidate_id: str) -> str:
        payload = {
            "candidate": self.actions.data.candidate_detail(candidate_id),
            "provenance": self.actions.data.provenance(candidate_id).to_dict("records"),
        }
        return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()

    def linked_jobs(self, session_id: str) -> list[dict[str, Any]]:
        """Refresh plan-linked jobs from the shared Job Registry on every UI render."""
        job_ids: list[str] = []
        for plan in self.store.plans(session_id):
            if not plan.get("result"):
                continue
            try:
                result = json.loads(plan["result"])
            except Exception:
                continue
            job_ids.extend(str(value) for value in result.get("job_ids", []))
        if not job_ids:
            return []
        jobs = self.actions.data.jobs()
        if jobs.empty:
            return []
        return jobs.loc[jobs["job_id"].astype(str).isin(set(job_ids))].to_dict("records")

    def presentation_script(self) -> list[str]:
        return [
            "找出Glide和Vina分歧最大的10个候选。",
            "如果MMGBSA只能再算5个，从这里帮我选一下。",
            "为什么推荐这里的第一个分子？",
        ]
