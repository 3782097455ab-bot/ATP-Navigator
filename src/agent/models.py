from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


READ_ONLY_INTENTS = {
    "candidate_query",
    "evidence_query",
    "provenance_query",
    "protocol_comparison",
    "decision_ranking",
    "job_status",
    "missing_evidence",
    "tool_capability",
    "parent_lineage",
}

CONFIRMATION_INTENTS = {
    "acquisition",
    "generation",
    "calculation_plan",
    "export_request",
}

SUPPORTED_INTENTS = READ_ONLY_INTENTS | CONFIRMATION_INTENTS


@dataclass(frozen=True)
class ParsedIntent:
    operation: str
    target: str = "ATP synthase"
    candidate_scope: list[str] = field(default_factory=list)
    constraints: dict[str, Any] = field(default_factory=dict)
    budget: int | None = None
    protocol: str | None = None
    expected_outputs: list[str] = field(default_factory=list)
    confidence: float = 1.0
    provider: str = "rule_based"
    original_text: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ExecutionPlan:
    plan_id: str
    session_id: str
    project_id: str
    action_id: str
    intent: dict[str, Any]
    what_will_happen: str
    candidate_count: int
    tool_backend: str
    protocol: str
    estimated_runtime: str
    estimated_resource_level: str
    evidence_generated: list[str]
    files_or_records_changed: list[str]
    scientific_caveats: list[str]
    status: str = "pending_confirmation"

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)
