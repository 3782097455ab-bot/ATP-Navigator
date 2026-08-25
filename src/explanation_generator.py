"""Generate evidence-grounded candidate explanations for Phase 10."""

from __future__ import annotations

import math
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd


REPORT_VERSION = "ATP-Navigator_Phase10_Explanation_v1.0"


def atomic_text(text: str, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", delete=False, dir=path.parent, suffix=".tmp"
    ) as handle:
        temporary = Path(handle.name)
        handle.write(text)
    temporary.replace(path)


def fmt(value: object, digits: int = 2) -> str:
    numeric = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    return "unknown" if pd.isna(numeric) else f"{float(numeric):.{digits}f}"


def recommendation(row: pd.Series, candidate_count: int) -> str:
    rank = pd.to_numeric(row.get("rank"), errors="coerce")
    if pd.isna(rank):
        return "Insufficient computational evidence; do not prioritize automatically"
    high_cutoff = max(3, int(math.ceil(candidate_count * 0.2)))
    comparison_cutoff = max(high_cutoff + 1, int(math.ceil(candidate_count * 0.6)))
    if rank <= high_cutoff:
        return "High priority for experimental evaluation (computational decision only)"
    if rank <= comparison_cutoff:
        return "Intermediate priority or diversity/uncertainty comparison candidate"
    return "Lower current priority; retain as a comparator, not a presumed inactive"


def reason_lines(row: pd.Series) -> list[str]:
    components = {
        "Binding evidence": row.get("binding_score"),
        "ATP-related computational evidence": row.get("ATP_score"),
        "Antibacterial external-model prior": row.get("antibacterial_score"),
        "Drug-likeness and predicted ADMET evidence": row.get("drug_score"),
    }
    valid = [
        (name, float(value))
        for name, value in components.items()
        if pd.notna(pd.to_numeric(value, errors="coerce"))
    ]
    valid.sort(key=lambda item: item[1], reverse=True)
    lines = [f"{name}: batch-relative component score {value:.2f}." for name, value in valid[:3]]
    if not lines:
        lines.append("Required computational decision components are incomplete.")
    model = row.get("model_used", "unknown")
    lines.append(
        f"Model tool: {model}; its score predicts the preserved static-MM/GBSA computational task, not biological activity."
    )
    return lines


def limitation_lines(row: pd.Series) -> list[str]:
    lines = [
        f"Experimental ATP inhibition: {row.get('experimental_ATP_inhibition', 'unknown')}",
        f"MIC: {row.get('experimental_MIC', 'unknown')}",
        f"Experimental toxicity: {row.get('experimental_toxicity', 'unknown')}",
        "External ATP and antibacterial priors are cross-domain model outputs, not measurements on this candidate.",
        "Final and component scores are relative to the submitted candidate batch and are not success probabilities.",
    ]
    missing = str(row.get("missing_computational_fields", "[]"))
    if missing not in {"[]", "", "nan"}:
        lines.append(f"Missing computational fields recorded by the processor: {missing}")
    if str(row.get("duplicate_structure_of", "")).strip() not in {"", "nan"}:
        lines.append(
            f"Canonical structure duplicates {row['duplicate_structure_of']} and is excluded from independent ranking."
        )
    return lines


def generate_report(
    ranking: pd.DataFrame,
    profile: str,
    output_path: str | Path,
    source_name: str,
) -> str:
    output_path = Path(output_path)
    lines = [
        "# ATP-Navigator Candidate Recommendation Report",
        "",
        f"版本：{REPORT_VERSION}",
        "",
        f"研究模式：`{profile}`",
        "",
        f"输入来源：`{source_name}`",
        "",
        "> 本报告用于决定下一批实验资源的优先顺序。它不证明候选具有ATP抑制或抗菌活性。",
        "",
        "## Ranking overview",
        "",
        "| Rank | Candidate | Model tool | Final score | Mean robust rank | P(Top 3) | Risk | Recommendation |",
        "|---:|---|---|---:|---:|---:|---|---|",
    ]
    sorted_frame = ranking.sort_values(["rank", "compound_id"], na_position="last")
    for row in sorted_frame.to_dict(orient="records"):
        series = pd.Series(row)
        rank = "unknown" if pd.isna(row.get("rank")) else str(int(row["rank"]))
        lines.append(
            f"| {rank} | {row['compound_id']} | {row.get('model_used', 'unknown')} | "
            f"{fmt(row.get('final_score'))} | {fmt(row.get('mean_rank'))} | "
            f"{fmt(row.get('p_top3'), 3)} | {row.get('risk', 'unknown')} | "
            f"{recommendation(series, len(ranking))} |"
        )

    lines.extend(["", "## Candidate-level explanations", ""])
    for row in sorted_frame.to_dict(orient="records"):
        series = pd.Series(row)
        rank = "unknown" if pd.isna(row.get("rank")) else str(int(row["rank"]))
        lines.extend(
            [
                f"### {row['compound_id']}",
                "",
                f"- Rank: {rank}",
                f"- Recommendation: {recommendation(series, len(ranking))}",
                f"- Final score: {fmt(row.get('final_score'))}",
                f"- Decision confidence: {row.get('decision_confidence', 'unknown')}",
                f"- Predicted risk band: {row.get('risk', 'unknown')}",
                "",
                "Reasons:",
                "",
            ]
        )
        for index, reason in enumerate(reason_lines(series), start=1):
            lines.append(f"{index}. {reason}")
        lines.extend(["", "Limitations:", ""])
        for limitation in limitation_lines(series):
            lines.append(f"- {limitation}")
        lines.append("")

    lines.extend(
        [
            "## Interpretation boundary",
            "",
            "- `P(Top 3)` is the frequency of entering the top three under the declared weight distribution, not biological activity probability.",
            "- `risk` summarizes predicted ADMET endpoints and descriptor rules; it is not experimental safety.",
            "- A lower-priority molecule is retained as a comparator and is not labeled inactive.",
            "- Experimental results remain `unknown` until a traceable assay result is imported.",
            "",
        ]
    )
    text = "\n".join(lines)
    atomic_text(text, output_path)
    return text
