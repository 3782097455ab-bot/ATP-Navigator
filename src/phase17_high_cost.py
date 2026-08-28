from __future__ import annotations

import argparse
import json
from pathlib import Path

from high_cost.engine import Phase17Engine


def main() -> None:
    parser = argparse.ArgumentParser(description="Phase 17 gated high-cost evidence acquisition")
    parser.add_argument("--project", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    print(json.dumps(Phase17Engine(args.project).run(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
