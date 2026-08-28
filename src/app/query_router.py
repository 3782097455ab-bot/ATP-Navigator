"""Deterministic research dialogue over existing registries."""
from __future__ import annotations

import re

from .data_adapter import ProjectData


EXAMPLES = [
    "Hit13现在有哪些证据？",
    "如果MM/GBSA只能再算20个，算谁？",
    "哪些候选因为Vina和Glide冲突而被选择？",
    "项目现在最缺什么证据？",
    "哪些高成本工具现在不可用？",
]


class ResearchQueryRouter:
    def __init__(self, data: ProjectData):
        self.data = data

    def answer(self, question: str) -> dict:
        query = question.strip()
        lower = query.lower()
        if not query:
            return {"answer": "请输入一个研究问题。", "records": [], "provenance": [], "warning": ""}

        candidate_match = re.search(r"(hit\s*\d+|in-?2|HTVS[_-]?\w+)", query, re.I)
        if candidate_match and any(word in query for word in ["证据", "数据", "情况", "有哪些"]):
            token = candidate_match.group(1).replace(" ", "")
            master = self.data.candidate_master()
            mask = master["compound_id"].str.casefold().eq(token.casefold()) | master["display_name"].astype(str).str.casefold().eq(token.casefold())
            if not mask.any():
                return {"answer": f"未找到 {token} 的可追溯候选身份。不会按名称或排名猜测映射。", "records": [], "provenance": [], "warning": "身份未解决不等于无证据。"}
            cid = str(master.loc[mask, "compound_id"].iloc[0])
            matrix = self.data.evidence_matrix().loc[lambda x: x["compound_id"].eq(cid)]
            provenance = self.data.provenance(cid)
            return {"answer": f"{token} 对应已登记候选 {cid}。下表只陈述 Registry 中存在、缺失或未知的证据，不推断实验活性。",
                    "records": matrix.to_dict("records"), "provenance": provenance.head(30).to_dict("records"),
                    "warning": "计算排序不是ATP抑制、MIC或毒性的实验结论。"}

        if "mm/gbsa" in lower or "mmgbsa" in lower:
            budget_match = re.search(r"(\d+)\s*个", query)
            budget = min(max(int(budget_match.group(1)) if budget_match else 20, 1), 100)
            frame = self.data.acquisition_recommendations("ATP_Navigator_hybrid", budget)
            return {"answer": f"按冻结的 Phase 15 hybrid 策略，预算 {budget} 时优先获取这些候选的高成本证据。选择依据是协议分歧、证据缺口、结构覆盖和决策边界，不是生物活性概率。",
                    "records": frame.to_dict("records"), "provenance": [{"source": "results/phase15", "strategy": "ATP_Navigator_hybrid"}],
                    "warning": "Prime 当前许可证不可用；这里只给出可审计的获取顺序。"}

        if ("vina" in lower and "glide" in lower) or "协议" in query or "冲突" in query:
            frame, metrics = self.data.protocol_comparison()
            extreme = frame.sort_values("abs_rank_delta", ascending=False).head(20) if not frame.empty else frame
            return {"answer": "Glide 与 Vina 是不同计算协议；一致只表示计算结果稳定性，不等于活性。下面列出最大排名分歧。",
                    "records": extreme.to_dict("records"), "provenance": [metrics],
                    "warning": "协议共识不能替代实验验证。"}

        if "缺" in query or "missing" in lower:
            matrix = self.data.evidence_matrix()
            cols = [c for c in ["glide", "vina", "mmgbsa", "admet", "literature_prior", "experiment"] if c in matrix]
            summary = [{"evidence": col, **matrix[col].value_counts(dropna=False).to_dict()} for col in cols]
            return {"answer": "当前最主要的缺口是候选级高成本结合证据、独立ADMET证据和真实实验反馈；unknown 与 missing 均未按0填充。",
                    "records": summary, "provenance": [{"source": "unified evidence matrix"}], "warning": "这是数据完整性结论，不是生物安全或临床结论。"}

        if "工具" in query or "backend" in lower or "不可用" in query:
            caps = self.data.capabilities()
            unavailable = caps.loc[~caps["status"].astype(str).str.lower().isin(["available", "usable"])]
            return {"answer": "以下能力在当前 Windows 环境中不可用或不完整。系统不会为不可用后端生成模拟数值。",
                    "records": unavailable.to_dict("records"), "provenance": [{"source": "system/Phase17 capability audits"}], "warning": "Phase17.1 WSL 启用尚未执行。"}

        return {"answer": "当前对话层只回答候选证据、预算获取、协议分歧、证据缺口和工具能力问题。它不会自由生成科学数值。",
                "records": [], "provenance": [{"supported_examples": EXAMPLES}], "warning": "请从示例问题开始。"}
