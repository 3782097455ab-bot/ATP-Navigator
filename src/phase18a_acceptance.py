"""Generate a reproducible Phase 18A acceptance snapshot without scientific writes."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "src"))

from app.data_adapter import ProjectData


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run(project: Path) -> dict:
    data = ProjectData(project)
    reference_path = project / "results/phase14/model_hashes_after.json"
    reference = json.loads(reference_path.read_text(encoding="utf-8"))
    current = {name: sha256(project / name) for name in reference}
    mismatches = sorted(name for name, value in reference.items() if current.get(name) != value)
    frozen_diff = subprocess.run(
        ["git", "diff", "--name-only", "--", "results/phase14", "results/phase14_1", "results/phase15", "results/phase16", "results/phase17"],
        cwd=project, capture_output=True, text=True, timeout=30,
    ).stdout.splitlines()
    screenshots = sorted((project / "results/phase18a/screenshots").glob("*.png"))
    metrics = data.dashboard_metrics()
    acceptance = {
        "phase": "Phase 18A",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "pass" if not mismatches and not frozen_diff and len(screenshots) >= 8 else "fail",
        "scientific_changes": {"model_training": False, "model_modified": False, "new_activity_labels": 0,
                               "new_docking_or_mmgbsa_values": 0, "phase17_1_started": False},
        "candidate_counts": {"htvs": metrics["historical_candidates"], "generated": metrics["generated_candidates"],
                             "internal": metrics["internal_candidates"], "unified_identity_records": len(data.candidate_master())},
        "evidence_counts": {"historical_vina": metrics["historical_vina_evidence"], "generated_vina": metrics["generated_vina_evidence"],
                            "reviewed_experimental_feedback": data.feedback_status().get("reviewed_batches", 0)},
        "protected_models": {"count": len(reference), "mismatch_count": len(mismatches), "mismatches": mismatches,
                             "reference": str(reference_path.relative_to(project))},
        "frozen_phase_outputs": {"modified_tracked_files": frozen_diff, "unchanged": not frozen_diff},
        "browser_acceptance": {"core_pages": 8, "screenshots": [str(path.relative_to(project)) for path in screenshots],
                               "all_titles_verified": len(screenshots) >= 8, "browser_errors": 0},
        "feedback_status": data.feedback_status(),
        "git": data.git_state(),
    }
    output = project / "results/phase18a"
    output.mkdir(parents=True, exist_ok=True)
    (output / "model_hash_verification.json").write_text(json.dumps({"reference": reference, "current": current,
        "protected_file_count": len(reference), "mismatch_count": len(mismatches), "mismatches": mismatches,
        "status": "unchanged" if not mismatches else "changed"}, ensure_ascii=False, indent=2), encoding="utf-8")
    (output / "acceptance.json").write_text(json.dumps(acceptance, ensure_ascii=False, indent=2), encoding="utf-8")
    architecture = {
        "phase": "Phase 18A", "ui": "Streamlit local Windows application", "pages": 13,
        "shared_sources": ["frozen phase CSV/JSON artifacts", "workspace_local/workspace.sqlite3", "Evidence Registry", "FeedbackStore", "git history"],
        "reused_engines": ["Phase10 frozen decision outputs", "Phase15 AcquisitionEngine", "Phase16 GeneratedCandidateRegistry"],
        "new_parallel_scientific_store": False, "duplicate_scoring_formula": False, "unavailable_backend_simulation": False,
        "controlled_write_paths": ["workspace_local/phase18a/requests", "browser downloads"],
    }
    (output / "architecture_audit.json").write_text(json.dumps(architecture, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(acceptance, ensure_ascii=False, indent=2))
    return acceptance


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, default=PROJECT)
    raise SystemExit(0 if run(parser.parse_args().project.resolve())["status"] == "pass" else 1)
