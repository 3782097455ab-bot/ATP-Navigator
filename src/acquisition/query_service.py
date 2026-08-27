"""Deterministic answers backed only by Phase 15 acquisition artifacts."""
from __future__ import annotations

from pathlib import Path
import pandas as pd


def _load(project: Path) -> pd.DataFrame:
    return pd.read_csv(project / "results/phase15/acquisition_panel_v1.csv")


def answer(project: Path, question: str) -> dict:
    panel = _load(project)
    text = question.strip()
    if "只能再算20个" in text or ("20" in text and "算谁" in text):
        rows = panel.sort_values("hybrid_rank").head(20)
        return {"budget": 20, "strategy": "ATP_Navigator_hybrid",
                "candidates": rows[["canonical_id", "why_selected", "recommended_next_evidence"]].to_dict("records")}
    if "Vina和Glide意见冲突" in text or ("协议" in text and "选" in text):
        rows = panel.loc[panel["acquisition_class"].eq("extreme_disagreement")]
        return {"criterion": "protocol_disagreement",
                "candidates": rows[["canonical_id", "protocol_uncertainty", "why_selected"]].to_dict("records")}
    if "两个协议都很强" in text:
        rows = panel.loc[panel["acquisition_class"].eq("multi_protocol_strong")]
        return {"criterion": "multi_protocol_strong",
                "candidates": rows[["canonical_id", "vina_rank", "glide_rank", "why_selected"]].to_dict("records")}
    if "主要来自协议" in text:
        rows = panel.sort_values("protocol_uncertainty", ascending=False).head(20)
        return {"criterion": "protocol_uncertainty",
                "candidates": rows[["canonical_id", "protocol_uncertainty", "uncertainty_dominant_source"]].to_dict("records")}
    if "预算从60降到20" in text or ("60" in text and "20" in text and "删除" in text):
        keep = set(panel.sort_values("hybrid_rank").head(20)["canonical_id"])
        removed = panel.loc[~panel["canonical_id"].isin(keep)].sort_values("hybrid_rank")
        return {"kept": 20,
                "removed": removed[["canonical_id", "hybrid_rank", "acquisition_class", "why_selected"]].to_dict("records")}
    return {"status": "unsupported_question",
            "supported": ["MM/GBSA预算20", "协议冲突", "双协议强", "协议不确定性", "预算60降到20"]}
