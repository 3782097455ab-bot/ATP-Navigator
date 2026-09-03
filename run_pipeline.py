from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT / "src"))

from reference_workflow.pipeline import ReferencePipeline


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the versioned IN-2 / 7P3W reference workflow")
    parser.add_argument("--config", default="configs/in2_7p3w_reference.yaml")
    parser.add_argument("--mode", choices=["smoke", "development", "full"], default=None)
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--retry-failed", action="store_true", help="Retry only terminal technical failures without changing scientific protocols.")
    parser.add_argument(
        "--stop-after",
        choices=["reference_inputs", "library_generation", "molecular_filtering", "docking", "refinement", "mmgbsa"],
        default=None,
        help="Stop safely at a stage boundary; rerun the same command without this flag to resume from caches/checkpoints.",
    )
    args = parser.parse_args()
    project = PROJECT
    result = ReferencePipeline(project, args.config).run(args.mode, args.run_id, args.stop_after, args.retry_failed)
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
