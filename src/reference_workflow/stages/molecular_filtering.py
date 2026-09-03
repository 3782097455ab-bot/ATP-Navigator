from __future__ import annotations

import json
import os
import shutil
import time
from collections import Counter
from pathlib import Path
from typing import Any

import pandas as pd
from rdkit import Chem, rdBase
from rdkit.Chem import Lipinski, rdMolDescriptors
from rdkit.Chem.Scaffolds import MurckoScaffold

from ..util import atomic_csv, atomic_json, sha256_file, stable_hash, utc_now


def _threshold(rule: dict[str, Any]) -> str:
    if rule["operator"] == "between":
        return f"[{rule['minimum']}, {rule['maximum']}]"
    if rule["operator"] in {"le", "eq"}:
        return str(rule["value"])
    return "empty"


def _passes(value: Any, rule: dict[str, Any]) -> bool:
    operator = rule["operator"]
    if operator == "empty":
        return pd.isna(value) or str(value).strip() == ""
    if operator == "eq":
        return str(value).strip().lower() == str(rule["value"]).strip().lower()
    numeric = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    if pd.isna(numeric):
        return False
    if operator == "le":
        return float(numeric) <= float(rule["value"])
    if operator == "between":
        return float(rule["minimum"]) <= float(numeric) <= float(rule["maximum"])
    raise ValueError(f"unsupported_filter_operator:{operator}")


def run_filter(
    library_path: Path,
    output_dir: Path,
    filtering_config: dict[str, Any],
    library_hash: str,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    protocol_identity = {
        "protocol_id": filtering_config["protocol_id"],
        "historical_quickprop_equivalence": False,
        "rules_frozen_before_reference_runs": bool(filtering_config["rules_frozen_before_reference_runs"]),
        "rules": filtering_config["rules"],
        "rdkit_version": rdBase.rdkitVersion,
    }
    filter_protocol_hash = stable_hash(protocol_identity)
    protocol_payload = {**protocol_identity, "library_hash": library_hash}
    filter_hash = stable_hash(protocol_payload)
    manifest_path = output_dir / "filter_manifest.json"
    accepted_path = output_dir / "accepted_candidates.csv"
    results_path = output_dir / "filter_results.csv"
    rejections_path = output_dir / "filter_rejections.csv"
    if manifest_path.is_file() and accepted_path.is_file() and results_path.is_file() and rejections_path.is_file():
        existing = json.loads(manifest_path.read_text(encoding="utf-8"))
        if existing.get("filter_hash") != filter_hash or existing.get("library_hash") != library_hash:
            raise ValueError("immutable_filter_manifest_changed")
        portable_artifacts = {
            "accepted_candidates": {"path": "filtering/accepted_candidates.csv", "sha256": sha256_file(accepted_path)},
            "filter_results": {"path": "filtering/filter_results.csv", "sha256": sha256_file(results_path)},
            "filter_rejections": {"path": "filtering/filter_rejections.csv", "sha256": sha256_file(rejections_path)},
        }
        if existing.get("filter_protocol_hash") != filter_protocol_hash or existing.get("artifacts") != portable_artifacts:
            existing["filter_protocol_hash"] = filter_protocol_hash
            existing["artifacts"] = portable_artifacts
            atomic_json(manifest_path, existing)
        return {**existing, "cached": True}

    started = time.perf_counter()
    started_at = utc_now()
    chunks_dir = output_dir / "filter_chunks"
    chunks_dir.mkdir(parents=True, exist_ok=True)
    checkpoint_path = output_dir / "filter_checkpoint.json"
    checkpoint = {
        "filter_hash": filter_hash,
        "library_hash": library_hash,
        "next_chunk": 0,
        "input_count": 0,
        "accepted_count": 0,
        "rejected_count": 0,
        "warning_candidate_count": 0,
        "reason_counts": {},
        "status": "running",
    }
    if checkpoint_path.is_file():
        checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
        if checkpoint["filter_hash"] != filter_hash or checkpoint["library_hash"] != library_hash:
            raise ValueError("filter_checkpoint_input_mismatch")
        for durable_index in range(int(checkpoint["next_chunk"])):
            if not (chunks_dir / f"results_{durable_index:05d}.csv").is_file() or not (chunks_dir / f"accepted_{durable_index:05d}.csv").is_file():
                raise ValueError(f"filter_checkpoint_chunk_missing:{durable_index}")

    for chunk_index, library in enumerate(pd.read_csv(library_path, keep_default_na=False, chunksize=5000)):
        if chunk_index < int(checkpoint["next_chunk"]):
            continue
        result_rows: list[dict[str, Any]] = []
        rejection_rows: list[dict[str, Any]] = []
        for row in library.to_dict("records"):
            mol = Chem.MolFromSmiles(str(row.get("canonical_smiles", "")))
            computed = {
                "absolute_formal_charge": abs(Chem.GetFormalCharge(mol)) if mol is not None else None,
                "ring_count": Lipinski.RingCount(mol) if mol is not None else None,
                "fraction_csp3": rdMolDescriptors.CalcFractionCSP3(mol) if mol is not None else None,
                "scaffold": MurckoScaffold.MurckoScaffoldSmiles(mol=mol) if mol is not None else "",
            }
            evaluated = {**row, **computed}
            hard_failures: list[str] = []
            warnings: list[str] = []
            for rule in filtering_config["rules"]:
                value = evaluated.get(rule["field"])
                if _passes(value, rule):
                    continue
                record = {
                    "compound_id": row["compound_id"],
                    "stage": "open_physicochemical_structural_filtering",
                    "field": rule["field"],
                    "reason": rule["reason"],
                    "kind": rule["kind"],
                    "operator": rule["operator"],
                    "threshold": _threshold(rule),
                    "raw_value": value,
                    "rationale": rule["rationale"],
                    "filter_protocol_id": filtering_config["protocol_id"],
                    "filter_hash": filter_hash,
                }
                rejection_rows.append(record)
                (hard_failures if rule["kind"] == "hard" else warnings).append(rule["reason"])
            evaluated["filter_status"] = "rejected" if hard_failures else "accepted"
            evaluated["hard_failure_reasons"] = "|".join(hard_failures)
            evaluated["warning_reasons"] = "|".join(warnings)
            evaluated["filter_protocol_id"] = filtering_config["protocol_id"]
            evaluated["filter_hash"] = filter_hash
            result_rows.append(evaluated)
        results = pd.DataFrame(result_rows)
        accepted = results.loc[results["filter_status"].eq("accepted")].copy()
        rejections = pd.DataFrame(rejection_rows)
        atomic_csv(chunks_dir / f"results_{chunk_index:05d}.csv", results)
        atomic_csv(chunks_dir / f"accepted_{chunk_index:05d}.csv", accepted)
        if len(rejections):
            atomic_csv(chunks_dir / f"rejections_{chunk_index:05d}.csv", rejections)
        checkpoint["next_chunk"] = chunk_index + 1
        checkpoint["input_count"] += len(results)
        checkpoint["accepted_count"] += len(accepted)
        checkpoint["rejected_count"] += int(results["filter_status"].eq("rejected").sum())
        checkpoint["warning_candidate_count"] += int(results["warning_reasons"].ne("").sum())
        counter = Counter(checkpoint.get("reason_counts", {}))
        counter.update(f"{row['kind']}|{row['reason']}" for row in rejection_rows)
        checkpoint["reason_counts"] = dict(counter)
        checkpoint["updated_at"] = utc_now()
        atomic_json(checkpoint_path, checkpoint)

    def concatenate(pattern: str, destination: Path) -> None:
        temporary = destination.with_suffix(destination.suffix + ".tmp")
        with temporary.open("wb") as output:
            wrote_header = False
            for source in sorted(chunks_dir.glob(pattern)):
                with source.open("rb") as handle:
                    header = handle.readline()
                    if not wrote_header:
                        output.write(header)
                        wrote_header = True
                    shutil.copyfileobj(handle, output)
        os.replace(temporary, destination)

    concatenate("results_*.csv", results_path)
    concatenate("accepted_*.csv", accepted_path)
    concatenate("rejections_*.csv", rejections_path)
    reason_counts = [
        {"kind": key.split("|", 1)[0], "reason": key.split("|", 1)[1], "count": value}
        for key, value in sorted(checkpoint.get("reason_counts", {}).items())
    ]
    checkpoint["status"] = "completed"
    checkpoint["updated_at"] = utc_now()
    atomic_json(checkpoint_path, checkpoint)
    manifest = {
        **protocol_payload,
        "filter_hash": filter_hash,
        "filter_protocol_hash": filter_protocol_hash,
        "status": "completed",
        "cached": False,
        "started_at": started_at,
        "completed_at": utc_now(),
        "elapsed_seconds": time.perf_counter() - started,
        "input_count": int(checkpoint["input_count"]),
        "accepted_count": int(checkpoint["accepted_count"]),
        "rejected_count": int(checkpoint["rejected_count"]),
        "warning_candidate_count": int(checkpoint["warning_candidate_count"]),
        "reason_counts": reason_counts,
        "artifacts": {
            "accepted_candidates": {"path": "filtering/accepted_candidates.csv", "sha256": sha256_file(accepted_path)},
            "filter_results": {"path": "filtering/filter_results.csv", "sha256": sha256_file(results_path)},
            "filter_rejections": {"path": "filtering/filter_rejections.csv", "sha256": sha256_file(rejections_path)},
        },
        "scientific_scope": "open physicochemical and structural filtering; not historical QuickProp",
    }
    atomic_json(manifest_path, manifest)
    return manifest
