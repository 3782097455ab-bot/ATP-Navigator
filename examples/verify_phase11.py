"""Write actual software validation results; never generate biological metrics."""
from __future__ import annotations

import io
import json
import sys
import unittest
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from workspace_io import file_hash, now, write_json_new


def main():
    destination = ROOT / "results/phase11_validation.json"
    if destination.exists():
        raise FileExistsError("Validation is already recorded; use a new versioned destination")
    before = {str(p.relative_to(ROOT)): file_hash(p) for p in (ROOT / "models").rglob("*") if p.is_file()}
    suite = unittest.defaultTestLoader.discover(str(ROOT / "tests"), pattern="test_phase1*.py")
    stream = io.StringIO()
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
    after = {str(p.relative_to(ROOT)): file_hash(p) for p in (ROOT / "models").rglob("*") if p.is_file()}
    old = pd.read_csv(ROOT / "results/demo/final_navigation_report.csv").set_index("compound_id")
    new = pd.read_csv(ROOT / "results/phase11_workspace_demo_v1_1/final_navigation_report.csv").set_index("compound_id")
    columns = ["model_score", "final_score", "rank"]
    difference = (old[columns].sort_index() - new[columns].sort_index()).abs().max().to_dict()
    payload = {"verified_at": now(), "tests_run": result.testsRun, "failures": len(result.failures),
               "errors": len(result.errors), "all_tests_passed": result.wasSuccessful(),
               "model_files_checked": len(before), "model_files_unchanged": before == after,
               "model_hashes": after, "phase10_vs_phase11_max_abs_differences": difference,
               "supervised_training": False, "experimental_validation": "not_performed",
               "llm_network_validation": "not_performed_no_key", "test_output": stream.getvalue()}
    write_json_new(destination, payload)
    print(json.dumps({k: v for k, v in payload.items() if k not in {"model_hashes", "test_output"}}, indent=2))
    return 0 if result.wasSuccessful() and before == after else 1


if __name__ == "__main__":
    raise SystemExit(main())
