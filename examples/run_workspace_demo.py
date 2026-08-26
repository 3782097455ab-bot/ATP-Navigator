"""Exercise real conversation/tool flow on the 17 candidates; zero wet labels."""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from experimental_feedback import FIELDS, FeedbackStore, write_csv_new
from feedback_evaluator import evaluate
from research_workspace import ResearchWorkspace
from workspace_io import file_hash, now, write_json_new


def run(output: Path) -> dict:
    output.mkdir(parents=True, exist_ok=False)
    before = {str(p.relative_to(ROOT)): file_hash(p) for p in (ROOT / "models").rglob("*") if p.is_file()}
    workspace = ResearchWorkspace(ROOT)
    session = workspace.create_session(ROOT / "results/demo/demo_input.csv")
    transcript = []
    for message in ["状态", "按 atp_mechanism_focused 排序", "解释 Hit3", "比较模式", "查资料 abaucin"]:
        result = workspace.chat(session, message)
        transcript.append({"user": message, "assistant": result})
        if result.get("status") == "confirmation_required":
            # Script explicitly plays the human confirmation for this documented demo.
            command = "确认 " + result["proposal_id"]
            transcript.append({"user": command, "assistant": workspace.chat(session, command)})
    completed = next(turn["assistant"]["result"] for turn in transcript if turn["assistant"].get("status") == "completed")
    run_dir = Path(completed["output_dir"])
    for filename in ["final_navigation_report.csv", "candidate_explanation.md", "profile_comparison.csv", "workflow_validation.json"]:
        shutil.copyfile(run_dir / filename, output / filename)
    empty_store = FeedbackStore(ROOT, output / "empty_feedback_store")
    iteration = empty_store.snapshot()
    evaluation = evaluate(empty_store.root / "snapshots" / iteration["snapshot_id"], output / "final_navigation_report.csv", output / "empty_feedback_evaluation")
    write_json_new(output / "conversation.json", transcript)
    ranking = pd.read_csv(output / "final_navigation_report.csv")
    after = {str(p.relative_to(ROOT)): file_hash(p) for p in (ROOT / "models").rglob("*") if p.is_file()}
    summary = {"created_at": now(), "session_id": session, "candidates": len(ranking),
               "full_v3_predictions": int(ranking.model_used.eq("Model_v3_full_frozen").sum()),
               "ranked_candidates": int(ranking["rank"].notna().sum()),
               "conversation_tools_executed": ["status", "run_navigation", "explain_candidate", "compare_profiles", "find_knowledge"],
               "model_files_checked": len(before), "all_model_files_unchanged": before == after,
               "experimental_feedback_records": iteration["records"],
               "feedback_evaluation_status": evaluation["status"],
               "llm_api_used": False, "supervised_training": False,
               "limitation": "offline command workspace, not a free-form LLM chat; no prospective wet validation"}
    write_json_new(output / "demo_summary.json", summary)
    # Generate a blank template based on real identities, with no pseudo-results.
    template = ROOT / "data/templates/phase11_feedback_template.csv"
    if not template.exists():
        raw = pd.read_csv(ROOT / "data/model_v3/training_table.csv", usecols=["compound_id", "canonical_smiles"])
        rows = [{**{field: "" for field in FIELDS}, "compound_id": r["compound_id"],
                 "canonical_smiles": r["canonical_smiles"]} for r in raw.to_dict("records")]
        write_csv_new(template, rows, FIELDS)
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.output), ensure_ascii=False, indent=2))
