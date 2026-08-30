"""Fast, non-simulating checks before the Phase 17.1 background worker."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from src.phase17_1.engine import Engine, atomic_json, sha256
from src.phase17_1.worker import reconstruct_pose


def run(project: Path) -> dict:
    engine = Engine(project.resolve())
    receptor = Path(engine.protocol["receptor"]["prepared_runtime_path"])
    if not receptor.is_file():
        raise FileNotFoundError("prepared_runtime_receptor_missing")
    if sha256(receptor) != engine.protocol["receptor"]["prepared_sha256"]:
        raise ValueError("prepared_runtime_receptor_hash_changed")
    records = []
    for row in engine.plan.iloc[:8].to_dict("records"):
        _, identity = reconstruct_pose(Path(row["resolved_pose_path"]), row["canonical_smiles"])
        records.append(
            {
                "candidate_id": row["candidate_id"],
                "pose_sha256": identity["pose_sha256"],
                "expected_inchikey": identity["expected_inchikey"],
                "observed_inchikey": identity["observed_inchikey"],
                "exact_structure_match": identity["exact_structure_match"],
            }
        )
    output = {
        "status": "pass" if len(records) == 8 and all(r["exact_structure_match"] for r in records) else "failed",
        "checked_candidates": len(records),
        "receptor_sha256": sha256(receptor),
        "protocol_hash": engine.protocol["protocol_hash"],
        "records": records,
        "simulation_performed": False,
        "numerical_evidence_generated": False,
    }
    atomic_json(project / "results/phase17_1/qualification_preflight.json", output)
    return output


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", type=Path, default=Path.cwd())
    args = parser.parse_args()
    result = run(args.project)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["status"] == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
