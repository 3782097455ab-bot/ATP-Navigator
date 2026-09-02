"""Versioned, metadata-rich exports from displayed real results."""
from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO

import pandas as pd

from .data_adapter import ProjectData


def enrich(frame: pd.DataFrame, kind: str, data: ProjectData) -> pd.DataFrame:
    result = frame.copy()
    git = data.git_state()
    metadata = {
        "_export_kind": kind,
        "_product": "研序智航",
        "_legacy_repository": "ATP-Navigator",
        "_exported_at_utc": datetime.now(timezone.utc).isoformat(),
        "_git_commit": git["commit"],
        "_model_scope": "frozen Model v0-v4-alpha; no training in Phase18A",
        "_protocol_scope": "read from registered versioned evidence",
    }
    for key, value in metadata.items():
        result[key] = value
    return result


def csv_bytes(frame: pd.DataFrame, kind: str, data: ProjectData) -> bytes:
    return enrich(frame, kind, data).to_csv(index=False).encode("utf-8-sig")


def markdown_bytes(title: str, frame: pd.DataFrame, kind: str, data: ProjectData, limit: int = 100) -> bytes:
    rich = enrich(frame, kind, data)
    text = f"# {title}\n\n由研序智航根据已登记、可追溯的项目资产生成。缺失证据不等于零。\n\n{rich.head(limit).to_markdown(index=False)}\n"
    return text.encode("utf-8")
