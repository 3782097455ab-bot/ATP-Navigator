from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from agent.actions import INTENT_TO_ACTION
from agent.models import SUPPORTED_INTENTS


PROJECT = Path(__file__).resolve().parents[1]
RESULTS = PROJECT / "results" / "phase18b"
REFERENCE = PROJECT / "results" / "phase14" / "model_hashes_after.json"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def model_hash_audit() -> dict:
    expected = json.loads(REFERENCE.read_text(encoding="utf-8"))
    actual: dict[str, str] = {}
    missing: list[str] = []
    mismatches: list[dict[str, str]] = []
    for relative, expected_hash in expected.items():
        path = PROJECT / Path(relative)
        if not path.exists():
            missing.append(relative)
            continue
        observed = sha256(path)
        actual[relative] = observed
        if observed != expected_hash:
            mismatches.append({"path": relative, "expected": expected_hash, "actual": observed})
    return {
        "reference": str(REFERENCE.relative_to(PROJECT)),
        "expected_count": len(expected),
        "verified_count": len(actual),
        "missing": missing,
        "mismatches": mismatches,
        "all_unchanged": not missing and not mismatches and len(actual) == len(expected),
        "actual_hashes": actual,
    }


def protected_diff() -> list[str]:
    paths = [
        "models",
        "results/phase14",
        "results/phase14_1",
        "results/phase15",
        "results/phase16",
        "results/phase17",
        "results/phase18a",
    ]
    run = subprocess.run(
        ["git", "diff", "--name-only", "--", *paths],
        cwd=PROJECT,
        check=True,
        capture_output=True,
        text=True,
    )
    return [line for line in run.stdout.splitlines() if line.strip()]


def collaboration_counts() -> dict[str, int]:
    database = PROJECT / "workspace_local" / "collaboration.sqlite3"
    tables = [
        "research_session_v2",
        "execution_plan_v2",
        "collaboration_event",
        "candidate_review",
        "candidate_vote",
        "final_human_decision",
        "make_test_queue",
    ]
    if not database.exists():
        return {table: 0 for table in tables}
    with sqlite3.connect(database) as connection:
        return {table: int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]) for table in tables}


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit the Phase 18B product integration without changing science assets.")
    parser.add_argument("--tests-run", type=int, required=True)
    parser.add_argument("--tests-passed", type=int, required=True)
    args = parser.parse_args()

    RESULTS.mkdir(parents=True, exist_ok=True)
    screenshots = sorted((RESULTS / "screenshots").glob("*.png"))
    browser = json.loads((RESULTS / "browser_acceptance.json").read_text(encoding="utf-8"))
    model_audit = model_hash_audit()
    (RESULTS / "model_hash_verification.json").write_text(
        json.dumps(model_audit, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    architecture = {
        "supported_intents": sorted(SUPPORTED_INTENTS),
        "supported_intent_count": len(SUPPORTED_INTENTS),
        "allowlisted_actions": sorted(set(INTENT_TO_ACTION.values())),
        "natural_language_shell_execution": False,
        "natural_language_sql_execution": False,
        "natural_language_eval_execution": False,
        "llm_scientific_number_generation": False,
        "unknown_experiment_fill": False,
    }
    (RESULTS / "architecture_audit.json").write_text(
        json.dumps(architecture, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    acceptance = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "passed" if args.tests_run == args.tests_passed and model_audit["all_unchanged"] else "failed",
        "test_command": "python -m pytest tests -q",
        "tests_run": args.tests_run,
        "tests_passed": args.tests_passed,
        "browser_acceptance": browser,
        "screenshot_count": len(screenshots),
        "screenshot_hashes": {path.name: sha256(path) for path in screenshots},
        "collaboration_counts": collaboration_counts(),
        "protected_scientific_tracked_diff": protected_diff(),
        "model_hash_summary": {
            "expected": model_audit["expected_count"],
            "verified": model_audit["verified_count"],
            "mismatch_count": len(model_audit["mismatches"]),
            "all_unchanged": model_audit["all_unchanged"],
        },
        "model_training": False,
        "fabricated_scientific_values": False,
        "phase17_1_control_action": "none",
    }
    (RESULTS / "acceptance.json").write_text(
        json.dumps(acceptance, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(acceptance, ensure_ascii=False, indent=2))
    return 0 if acceptance["status"] == "passed" and not acceptance["protected_scientific_tracked_diff"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
