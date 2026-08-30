"""Freeze the Competition Release Candidate without modifying frozen models."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


RC_VERSION = "ATP-Navigator-Competition-RC1"
DECISION_VERSION = "competition_rc_three_protocol_shadow_v1"


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def safe(value: Any) -> Any:
    if isinstance(value, dict): return {str(k): safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)): return [safe(v) for v in value]
    if hasattr(value, "item"): value = value.item()
    if isinstance(value, float) and not math.isfinite(value): return None
    if isinstance(value, Path): return str(value)
    return value


def atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False, dir=path.parent) as handle:
        json.dump(safe(payload), handle, ensure_ascii=False, indent=2, allow_nan=False)
        temporary = Path(handle.name)
    temporary.replace(path)


def atomic_csv(path: Path, frame: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8-sig", newline="", delete=False, dir=path.parent) as handle:
        frame.to_csv(handle, index=False)
        temporary = Path(handle.name)
    temporary.replace(path)


def git(project: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=project, capture_output=True, text=True, timeout=20)
    return result.stdout.strip() if result.returncode == 0 else "unknown"


def run(project: Path) -> dict[str, Any]:
    project = project.resolve()
    root = project / "results/release_candidate"
    decision_dir = root / "decision_runs"
    impact = pd.read_csv(project / "results/phase17_1/evidence_impact.csv")
    decision = impact.copy()
    decision["decision_version"] = DECISION_VERSION
    decision["decision_rank"] = pd.to_numeric(decision["post_mmgbsa_shadow_rank"], errors="coerce")
    decision["decision_score"] = 100.0 * pd.to_numeric(decision["post_mmgbsa_shadow_score"], errors="coerce")
    decision["decision_confidence"] = decision["three_protocol_complete"].map(
        {True: "three_protocol_computational", False: "two_protocol_computational"}
    ).fillna("two_protocol_computational")
    decision["experimental_ATP_inhibition"] = "unknown"
    decision["experimental_MIC"] = "unknown"
    decision["experimental_toxicity"] = "unknown"
    decision["official_model"] = "Model v3 (unchanged)"
    decision["run_role"] = "release_candidate_updated_evidence_shadow"
    columns = [
        "decision_version", "candidate_id", "decision_rank", "decision_score", "decision_confidence",
        "glide_score", "vina_score", "open_mmgbsa_deltaG", "protocol_count",
        "three_protocol_disagreement", "pre_mmgbsa_rank", "rank_change_after_mmgbsa",
        "evidence_completeness_gain", "selection_class", "scaffold", "protocol_id", "protocol_hash",
        "experimental_ATP_inhibition", "experimental_MIC", "experimental_toxicity", "official_model", "run_role",
    ]
    decision = decision[columns].sort_values(["decision_rank", "candidate_id"], na_position="last")
    atomic_csv(decision_dir / "competition_rc_decision_v1.csv", decision)

    top5_pre = set(impact.nsmallest(5, "pre_mmgbsa_rank")["candidate_id"])
    top5_post = set(impact.nsmallest(5, "post_mmgbsa_shadow_rank")["candidate_id"])
    decision_manifest = {
        "decision_version": DECISION_VERSION, "created_at": datetime.now(timezone.utc).isoformat(),
        "role": "updated-evidence shadow; frozen historical Decision is retained",
        "candidate_count": len(decision), "three_protocol_complete": int(decision["protocol_count"].eq(3).sum()),
        "two_protocol_complete": int(decision["protocol_count"].eq(2).sum()),
        "top5_overlap_pre_post": len(top5_pre & top5_post), "top5_overlap_fraction": len(top5_pre & top5_post) / 5,
        "median_absolute_rank_change": float(pd.to_numeric(decision["rank_change_after_mmgbsa"], errors="coerce").abs().median()),
        "largest_rank_change_candidate": str(impact.loc[pd.to_numeric(impact["rank_change_after_mmgbsa"], errors="coerce").abs().idxmax(), "candidate_id"]),
        "source": "results/phase17_1/evidence_impact.csv", "training_performed": False,
        "frozen_decision_overwritten": False,
    }
    atomic_json(decision_dir / "decision_run_manifest.json", decision_manifest)

    status_path = project / "data/external/integrated/benchmark_registry_status.json"
    status = json.loads(status_path.read_text(encoding="utf-8")) if status_path.exists() else {}
    status.update({
        "Part1 experimental benchmark records": "available_general_binding_only",
        "Part1 source": "BindingDB_BindingDB_Articles.tsv",
        "Part1 raw rows": 93712, "Part1 QC measurement rows": 96195,
        "Part1 direct ATP synthase rows": 0,
        "Part1 use boundary": "general binding external benchmark; not ATP-target training",
    })
    atomic_json(status_path, status)

    integration = json.loads((root / "member_data_integration/integration_summary.json").read_text(encoding="utf-8"))
    shadow = json.loads((root / "model_promotion/shadow_experiment_summary.json").read_text(encoding="utf-8"))
    phase17 = json.loads((project / "results/phase17_1/post_analysis.json").read_text(encoding="utf-8"))
    protected = json.loads((project / "results/phase14/model_hashes_after.json").read_text(encoding="utf-8"))
    current = {name: digest(project / name) for name in protected}
    if current != protected:
        raise RuntimeError("protected model hash mismatch")
    data_manifest = root / "member_data_integration/member_data_manifest.csv"
    new_model = project / "models/experiments/competition_rc_shadow_001/task_a_member2_context_shadow.joblib"
    release_manifest = {
        "release_version": RC_VERSION, "build_timestamp": datetime.now(timezone.utc).isoformat(),
        "source_code_commit": git(project, "rev-parse", "HEAD"), "branch": git(project, "branch", "--show-current"),
        "data_manifest": str(data_manifest.relative_to(project)).replace("\\", "/"),
        "data_manifest_sha256": digest(data_manifest),
        "official_model": "Model v3", "official_model_promoted": False,
        "shadow_model": "competition_rc_shadow_001", "shadow_model_sha256": digest(new_model),
        "evidence_registry_version": "Phase17.1 pilot30 / 60 registered evidence records",
        "decision_version": DECISION_VERSION,
        "protocol_versions": ["vina_7p3w_v1", "historical_glide", "open_mmgbsa_7p3w_v2"],
        "phase17_mmgbsa_candidates": 30, "phase17_evidence_records": 60,
        "three_protocol_exact_matched": phase17["three_protocol_matched_n"],
        "protected_model_hash_count": len(protected), "protected_model_hashes_unchanged": True,
        "scope": "pre-experimental computational evidence integration and candidate prioritization",
        "no_claims": ["biological activity", "experimental success probability", "clinical use", "biosafety assessment"],
    }
    atomic_json(root / "competition_rc_manifest.json", release_manifest)
    summary = {
        "release": release_manifest, "integration": integration, "shadow": shadow,
        "decision": decision_manifest, "phase17": {
            "mmgbsa_candidates": 30, "evidence_records": 60,
            "three_protocol_matched": phase17["three_protocol_matched_n"],
            "largest_disagreement": phase17["largest_protocol_disagreement"],
            "largest_rank_change": phase17["largest_shadow_rank_change"],
        },
    }
    atomic_json(root / "release_candidate_summary.json", summary)
    report = f"""# ATP-Navigator Competition Release Candidate

## Release boundary

ATP-Navigator remains an AI-assisted candidate-priority decision system positioned after virtual screening and before experimental selection. It integrates registered computational evidence; it does not claim biological activity or experimental success probability.

## Member data

- Member 1: {integration['member1']['raw_rows']} literature rows, {integration['member1']['unique_valid_structures']} unique valid structures, 0 exact training-eligible ATP-synthase records.
- Member 2: {integration['member2']['raw_rows']} MIC rows, {integration['member2']['unique_structures']} unique structures, all {integration['member2']['structure_overlap_external_v2_unique']} structures already overlap External Dataset v2; the new value is strain/resistance assay context.
- Member 3 Part 1: {integration['member3_part1']['raw_rows']} BindingDB rows / {integration['member3_part1']['qc_measurement_rows']} endpoint measurements; 0 direct ATP-synthase records in this supplied file.
- Member 3 Part 2: {integration['member3_part2']['benchmark_registry_count']} benchmark catalog entries; catalog only, not executed results.

## Shadow promotion gate

- Task-A baseline RMSE: {shadow['task_a']['metrics'][0]['rmse']:.4f}; member-context shadow RMSE: {shadow['task_a']['metrics'][1]['rmse']:.4f}.
- Task-A baseline Spearman: {shadow['task_a']['metrics'][0]['spearman']:.4f}; shadow Spearman: {shadow['task_a']['metrics'][1]['spearman']:.4f}.
- Bootstrap 95% interval for RMSE(new-old): {shadow['task_a']['bootstrap_rmse_delta_95_interval']}.
- Promotion gate: **not passed**. Model v3 remains the official candidate ranker. The MIC shadow is a different task and did not improve its own fixed scaffold benchmark.

## Phase17.1 evidence integration

- 30 candidates have real Open MM/GBSA results; 60 evidence records are registered.
- 24 candidates have exact three-protocol comparisons.
- The Release Candidate Decision Run is a new shadow evidence run and does not overwrite historical Decision outputs.
- Top-5 pre/post overlap: {decision_manifest['top5_overlap_pre_post']}/5; median absolute rank change: {decision_manifest['median_absolute_rank_change']:.1f}.
- Largest change: {decision_manifest['largest_rank_change_candidate']}.

## Frozen assets

- Official supervised model: Model v3.
- Protected model hashes: {len(protected)}/{len(protected)} unchanged.
- Release manifest: `results/release_candidate/competition_rc_manifest.json`.
"""
    (project / "docs/Competition_Release_Candidate_Report.md").write_text(report, encoding="utf-8")
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    print(json.dumps(run(args.project), ensure_ascii=False, indent=2))
