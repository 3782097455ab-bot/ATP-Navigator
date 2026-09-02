"""Run the versioned IN-2 reconstructed open workflow smoke path."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "src"))

from library_generation.workflow import ReproducibleWorkflow


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=PROJECT)
    parser.add_argument("--config", default="configs/library_generation/in2_reconstructed_v1.json")
    parser.add_argument("--target", type=int, default=100)
    parser.add_argument("--run-id", default="in2_smoke_100_v1")
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    result = ReproducibleWorkflow(args.project_root, args.config).run_smoke(args.target, args.run_id, args.workers)
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
