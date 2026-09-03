from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import pandas as pd

from ..util import atomic_csv, atomic_json, sha256_file


STAGE_LABELS = {
    "reference_inputs": "Target + IN-2",
    "library_generation": "Library Generation",
    "molecular_filtering": "Filtering",
    "docking": "Docking",
    "refinement": "Refinement",
    "mmgbsa": "Open MM/GBSA",
    "evidence_integration": "Evidence Integration",
    "decision": "AI / Decision",
    "candidate_panel": "Candidate Panel",
}


def _markdown_table(frame: pd.DataFrame) -> str:
    """Render a small table without adding the optional tabulate dependency."""
    columns = list(frame.columns)
    if not columns:
        return "No columns available."
    def clean(value: Any) -> str:
        return str(value).replace("|", "\\|").replace("\n", " ")
    lines = ["| " + " | ".join(columns) + " |", "|" + "|".join("---" for _ in columns) + "|"]
    lines.extend("| " + " | ".join(clean(value) for value in row) + " |" for row in frame.itertuples(index=False, name=None))
    return "\n".join(lines)


def write_funnel(run_dir: Path, stages: list[dict[str, Any]]) -> dict[str, Any]:
    rows = []
    for stage in stages:
        rows.append(
            {
                "stage": STAGE_LABELS.get(stage["stage_id"], stage["stage_id"]),
                "stage_id": stage["stage_id"],
                "input_count": stage.get("input_count"),
                "output_count": stage.get("output_count"),
                "failed_count": stage.get("failed_count", 0),
                "status": stage.get("status"),
                "protocol_id": stage.get("protocol_id"),
                "runtime_seconds": stage.get("runtime_seconds"),
            }
        )
    frame = pd.DataFrame(rows)
    csv_path = run_dir / "reports/screening_funnel.csv"
    json_path = run_dir / "reports/screening_funnel.json"
    png_path = run_dir / "reports/screening_funnel.png"
    atomic_csv(csv_path, frame)
    atomic_json(json_path, rows)
    plot = frame.dropna(subset=["output_count"]).copy()
    if len(plot):
        fig, ax = plt.subplots(figsize=(9, 4.8))
        values = pd.to_numeric(plot["output_count"], errors="coerce").fillna(0)
        ax.bar(range(len(plot)), values, color="#168b8c")
        ax.set_yscale("log" if values.max() > 1000 and values[values > 0].min() > 0 else "linear")
        ax.set_xticks(range(len(plot)), plot["stage"], rotation=30, ha="right")
        ax.set_ylabel("Candidates")
        ax.set_title("IN-2 / 7P3W screening funnel")
        for index, value in enumerate(values):
            ax.text(index, value, f"{int(value):,}", ha="center", va="bottom", fontsize=8)
        fig.tight_layout()
        fig.savefig(png_path, dpi=180)
        plt.close(fig)
    return {
        "csv": str(csv_path.relative_to(run_dir)).replace("\\", "/"),
        "json": str(json_path.relative_to(run_dir)).replace("\\", "/"),
        "png": str(png_path.relative_to(run_dir)).replace("\\", "/"),
    }


def generate_reports(run_dir: Path, manifest: dict[str, Any]) -> list[str]:
    reports = run_dir / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    stages = manifest["stages"]
    stage_table = "\n".join(
        f"| {STAGE_LABELS.get(row['stage_id'], row['stage_id'])} | {row.get('status')} | {row.get('input_count')} | {row.get('output_count')} | {row.get('protocol_id')} | {row.get('runtime_seconds')} |"
        for row in stages
    )
    common_table = "| Stage | Status | Input | Output | Protocol | Runtime (s) |\n|---|---:|---:|---:|---|---:|\n" + stage_table
    panel_path = run_dir / "decision/candidate_panel.csv"
    panel_table = "No candidate passed the declared evidence gate in this run."
    missing_summary = "No evidence-gated candidate panel was produced."
    if panel_path.is_file():
        panel = pd.read_csv(panel_path, keep_default_na=False)
        if len(panel):
            view_columns = [
                "priority_rank", "candidate_id", "vina_affinity", "open_mmgbsa_deltaG",
                "open_mmgbsa_sd", "evidence_completeness", "evidence_missing", "final_score",
            ]
            panel_table = _markdown_table(panel[[column for column in view_columns if column in panel]].head(10))
            missing = panel.get("evidence_missing", pd.Series(dtype=str)).replace("", "none_reported").value_counts()
            missing_summary = "; ".join(f"{name}: {count}" for name, count in missing.items()) or "none_reported"
    files: dict[str, str] = {
        "End_to_End_Workflow_Report.md": f"""# IN-2 / 7P3W End-to-End Workflow Report

Target + IN-2 → reconstructed reproducible derivative library → open physicochemical/structural filtering → AutoDock Vina → evidence acquisition → Open MM/GBSA → Evidence Registry → computational pre-experimental candidate panel.

{common_table}

This run does not claim that the reconstructed library equals the historical 2024 Auto_Enum library. Vina is not Glide; Open MM/GBSA is not Prime MM/GBSA.
""",
        "Reproducibility_Report.md": f"""# Reproducibility Report

- Workflow version: `{manifest['workflow_version']}`
- Git commit: `{manifest['git_commit']}`
- Config hash: `{manifest['config_hash']}`
- Library hash: `{manifest.get('library_hash')}`
- Target PDB hash: `{manifest['reference_inputs']['target_hash']}`
- Vina receptor hash: `{manifest['reference_inputs']['vina_receptor_hash']}`
- IN-2 canonical structure hash: `{manifest['reference_inputs']['reference_ligand_hash']}`
- Random seeds: `{json.dumps(manifest['random_seeds'], ensure_ascii=False)}`
- Cache-aware: yes; completed candidates are hash-validated and skipped.
- Resume-aware: yes; library chunks, per-candidate docking results, per-candidate Open MM/GBSA checkpoints and stage state are retained.
""",
        "Screening_Funnel_Report.md": f"""# Screening Funnel Report

{common_table}

All hard-filter exclusions are retained in `filtering/filter_rejections.csv` with field, threshold, raw value, rationale and filter hash. No structure is silently removed.
""",
        "Protocol_and_Tool_Report.md": """# Protocol and Tool Report

## Historical evidence route

The project PPT describes QuickProp, Glide HTVS/SP/XP, Prime MM/GBSA and Deep-PK. These records remain historical evidence and are not claimed as reconstructed executions.

## Reconstructed open route

- RDKit open physicochemical/structural filtering (`open_physchem_structural_filter_v1`); not QuickProp.
- AutoDock Vina (`vina_7p3w_v1`); not Glide HTVS/SP/XP.
- Acquisition selection (`acquisition_refinement_v1`); no fabricated second docking protocol.
- OpenMM + gmx_MMPBSA (`open_mmgbsa_7p3w_v2`); not Prime MM/GBSA and not experimental affinity.

`open_mmgbsa_7p3w_v2` uses the audited 7P3W e/g receptor scope, explicit TIP3P solvent, Amber ff14SB/GAFF 2.11, AM1-BCC charges and restrained short sampling. The membrane is omitted because no validated lipid coordinates are available; results are comparative screening-level evidence, not membrane-mechanism validation.
""",
        "Candidate_Prioritization_Report.md": f"""# Candidate Prioritization Report

- Decision scope: computational pre-experimental prioritization.
- Evidence-gated panel size: `{manifest.get('candidate_panel_count', 0)}`.
- Model training in this run: `false`.
- Model v3 modification: `false`.

The Level A output ranks the value of acquiring additional evidence and is not a biological hit ranking. Level B includes only candidates with the declared Vina + Open MM/GBSA evidence gate.

## Evidence-gated computational panel

{panel_table}
""",
        "Missing_Evidence_and_Next_Experiment_Report.md": f"""# Missing Evidence and Next Experiment Report

Current computational panel size: `{manifest.get('candidate_panel_count', 0)}`.

Panel missing-evidence summary: {missing_summary}

ADMET evidence for newly reconstructed structures remains `unknown` unless an actual registered result exists. ATP synthase inhibition, MIC and cytotoxicity are not inferred from docking/MMGBSA. Recommended validation order is biochemical ATP synthase inhibition, followed by MIC and cytotoxicity as separate endpoints.

When critical evidence is absent, the workflow returns `unknown`, `insufficient evidence`, or `additional evidence required` rather than an invented value.
""",
    }
    paths = []
    for name, text in files.items():
        path = reports / name
        path.write_text(text, encoding="utf-8")
        paths.append(str(path.relative_to(run_dir)).replace("\\", "/"))
    return paths
