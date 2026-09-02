"""Build or resume the reconstructed reproducible IN-2 derivative library."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "src"))

from library_generation import ReconstructedLibraryGenerator


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=PROJECT)
    parser.add_argument("--config", default="configs/library_generation/in2_reconstructed_v1.json")
    parser.add_argument("--target", type=int, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--stop-after-processed", type=int)
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    engine = ReconstructedLibraryGenerator(args.project_root, args.config)
    result = engine.generate(args.target, args.run_id, args.stop_after_processed)
    if args.verify and result.get("status") == "completed":
        result["verification"] = engine.verify_library(args.run_id)
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
