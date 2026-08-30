"""Intent-provider abstraction; providers never execute scientific actions."""
from __future__ import annotations

import json
import os
import re
import urllib.request
from abc import ABC, abstractmethod
from typing import Any

from .models import ParsedIntent, SUPPORTED_INTENTS


def _top_k(text: str, default: int = 10) -> int:
    patterns = [r"(?:top|前|挑|选|算|扩|生成)\s*(\d+)", r"(\d+)\s*个"]
    for pattern in patterns:
        match = re.search(pattern, text, re.I)
        if match:
            return min(max(int(match.group(1)), 1), 500)
    return default


def _candidate_tokens(text: str) -> list[str]:
    values = re.findall(r"(?:ATP-(?:HTVS|GEN|REF)-[A-Z0-9-]+|Hit\s*\d+|IN-?2)", text, re.I)
    return list(dict.fromkeys(value.replace(" ", "") for value in values))


class IntentProvider(ABC):
    @abstractmethod
    def parse(self, text: str, context: dict[str, Any]) -> ParsedIntent:
        raise NotImplementedError


class RuleBasedProvider(IntentProvider):
    """Deterministic Chinese/English router with explicit supported actions."""

    def parse(self, text: str, context: dict[str, Any]) -> ParsedIntent:
        raw = text.strip()
        lower = raw.lower()
        candidates = _candidate_tokens(raw)
        if any(token in raw for token in ["这里", "这些", "这一批", "from here", "these"]):
            candidates = candidates or list(context.get("selected_candidate_set", []))
        budget = _top_k(raw, default=10)
        constraints: dict[str, Any] = {}
        protocol = None

        if any(word in lower for word in ["job status", "任务状态", "进度", "running", "checkpoint"]):
            operation = "job_status"
        elif any(word in lower for word in ["tool", "backend", "工具", "后端", "许可证", "capability"]):
            operation = "tool_capability"
        elif any(word in lower for word in ["provenance", "来源", "追溯", "hash"]):
            operation = "provenance_query"
        elif any(word in lower for word in ["parent", "lineage", "母体", "谱系", "r group"]):
            operation = "parent_lineage"
        elif any(word in lower for word in ["缺什么", "缺失", "missing evidence", "证据缺口"]):
            operation = "missing_evidence"
        elif any(word in lower for word in ["加入mmgbsa后", "mmgbsa后判断变化", "evidence impact"]):
            operation = "protocol_comparison"
            constraints.update(top_k=budget, analysis_view="evidence_impact")
        elif any(word in lower for word in ["三个协议最一致", "三协议最一致", "three protocol consensus"]):
            operation = "protocol_comparison"
            constraints.update(top_k=budget, analysis_view="consensus")
        elif any(word in lower for word in ["仍然证据冲突", "三个协议分歧", "三协议分歧", "three protocol disagreement"]):
            operation = "protocol_comparison"
            constraints.update(top_k=budget, analysis_view="disagreement")
        elif ("glide" in lower and "vina" in lower) or any(word in lower for word in ["协议比较", "协议分歧", "protocol disagreement"]):
            operation = "protocol_comparison"
            constraints.update(top_k=budget, analysis_view="glide_vina_full_library")
        elif any(word in lower for word in ["为什么推荐", "决策排名", "decision rank", "综合排名", "ai排名"]):
            operation = "decision_ranking"
            constraints["top_k"] = budget
        elif any(word in lower for word in ["生成", "扩展", "扩", "generate", "expand", "r-group"]):
            operation = "generation"
            constraints.update(n=budget, preserve_scaffold=any(word in raw for word in ["保留核心", "保留骨架", "核心骨架"]))
            candidates = candidates or list(context.get("selected_candidate_set", []))
        elif any(word in lower for word in ["mmgbsa", "mm/gbsa", "进一步计算", "高成本计算", "acquisition", "预算"]):
            operation = "acquisition" if any(word in lower for word in ["挑", "选", "算谁", "预算", "acquisition"]) else "calculation_plan"
            constraints.update(evidence_type="MMGBSA", strategy="ATP_Navigator_hybrid")
            protocol = "open_mmgbsa_7p3w_v2"
        elif any(word in lower for word in ["导出", "export", "下载"]):
            operation = "export_request"
            constraints["format"] = "csv"
        elif candidates and any(word in lower for word in ["证据", "evidence", "数据"]):
            operation = "evidence_query"
        elif candidates:
            operation = "candidate_query"
        else:
            operation = "candidate_query"
            constraints["clarification_required"] = True

        expected = {
            "protocol_comparison": ["ranked protocol-disagreement table", "provenance"],
            "acquisition": ["candidate acquisition panel", "selection reasons", "job links"],
            "generation": ["versioned generation request"],
            "calculation_plan": ["versioned calculation plan", "blocked/ready status"],
            "export_request": ["audited CSV export"],
        }.get(operation, ["registry-backed answer"])
        return ParsedIntent(
            operation=operation,
            candidate_scope=candidates,
            constraints=constraints,
            budget=budget if operation in {"acquisition", "calculation_plan"} else None,
            protocol=protocol,
            expected_outputs=expected,
            confidence=0.55 if constraints.get("clarification_required") else 1.0,
            original_text=raw,
        )


class OpenAIProvider(IntentProvider):
    """Optional intent-only provider. Scientific actions remain allowlisted."""

    def __init__(self, model: str = "gpt-5.4-mini"):
        self.api_key = os.environ.get("OPENAI_API_KEY", "")
        if not self.api_key:
            raise RuntimeError("OPENAI_API_KEY is not configured")
        self.model = model

    def parse(self, text: str, context: dict[str, Any]) -> ParsedIntent:
        schema = {
            "operation": sorted(SUPPORTED_INTENTS),
            "candidate_scope": "array of exact IDs/aliases",
            "budget": "integer or null",
            "protocol": "string or null",
            "constraints": "object",
        }
        prompt = (
            "Extract one ATP-Navigator intent. Never calculate a scientific value or emit code. "
            f"Allowed schema: {json.dumps(schema)}. Context: {json.dumps(context, ensure_ascii=False)}. "
            f"Request: {text}"
        )
        body = json.dumps(
            {"model": self.model, "input": prompt, "text": {"format": {"type": "json_object"}}}
        ).encode()
        request = urllib.request.Request(
            "https://api.openai.com/v1/responses",
            data=body,
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=45) as response:
            payload = json.loads(response.read())
        parsed = json.loads(payload["output"][0]["content"][0]["text"])
        if parsed.get("operation") not in SUPPORTED_INTENTS:
            raise ValueError("LLM returned a non-allowlisted operation")
        return ParsedIntent(
            operation=parsed["operation"],
            candidate_scope=list(parsed.get("candidate_scope") or []),
            constraints=dict(parsed.get("constraints") or {}),
            budget=parsed.get("budget"),
            protocol=parsed.get("protocol"),
            expected_outputs=["registry-backed answer"],
            confidence=0.8,
            provider="openai_intent_only",
            original_text=text,
        )
