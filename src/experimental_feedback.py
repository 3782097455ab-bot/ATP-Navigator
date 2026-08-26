"""Versioned experimental feedback with human review. Never trains or deploys.

Evidence goes raw -> validated/quarantined -> reviewed -> task-specific snapshot.
Scientific truth cannot be established by a CSV validator: review is an explicit
human attestation, and source bytes and their hashes are preserved for audit.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import math
import shutil
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

from rdkit import Chem
from rdkit.Chem.Scaffolds import MurckoScaffold

from workspace_io import file_hash, identifier, now, read_json, safe_id, within, write_json_new

FIELDS = [
    "record_id", "compound_id", "canonical_smiles", "organism", "strain", "target",
    "activity_type", "activity_value", "comparator", "unit", "assay_mode",
    "replicate_id", "assay_protocol_id", "experimental_date", "operator", "reference",
    "qc_status", "evidence_type", "evidence_file", "evidence_sha256", "dataset_role",
]
TASKS = {"MIC": "A_antibacterial", "ATP_IC50": "B_ATP_target",
         "MMGBSA": "C_computational_binding", "CC50": "D_cytotoxicity"}
GROUP_FIELDS = ["task", "organism", "strain", "target", "activity_type", "unit",
                "assay_mode", "assay_protocol_id"]
MISSING = {"", "unknown", "nan", "none", "pending"}


def write_csv_new(path: Path, rows: list[dict], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


class FeedbackStore:
    def __init__(self, project_root: str | Path, store_root: str | Path | None = None):
        self.project = Path(project_root).resolve()
        self.root = Path(store_root or self.project / "data/experimental/feedback_store").resolve()
        self.identities = {}
        registry = self.project / "data/model_v3/training_table.csv"
        if registry.exists():
            with registry.open(encoding="utf-8-sig", newline="") as stream:
                for row in csv.DictReader(stream):
                    mol = Chem.MolFromSmiles(row["canonical_smiles"])
                    self.identities[row["compound_id"]] = Chem.MolToSmiles(mol, isomericSmiles=True)

    def validate(self, input_path: str | Path) -> tuple[list[dict], dict]:
        payload = Path(input_path).read_bytes()
        reader = csv.DictReader(io.StringIO(payload.decode("utf-8-sig")))
        missing = sorted(set(FIELDS) - set(reader.fieldnames or []))
        if missing:
            raise ValueError(f"Feedback headers missing: {missing}")
        results = []
        for line, row in enumerate(reader, 2):
            row = {key: str(row.get(key) or "").strip() for key in FIELDS}
            issues = []
            pending = row["activity_value"].lower() in MISSING
            mol = Chem.MolFromSmiles(row["canonical_smiles"])
            if mol is None:
                issues.append("invalid_smiles")
            else:
                row["canonical_smiles"] = Chem.MolToSmiles(mol, isomericSmiles=True)
                row["scaffold"] = MurckoScaffold.MurckoScaffoldSmiles(mol=mol, includeChirality=True) or row["canonical_smiles"]
                if row["compound_id"] in self.identities and self.identities[row["compound_id"]] != row["canonical_smiles"]:
                    issues.append("registered_identity_mismatch")
            row["task"] = TASKS.get(row["activity_type"], "unknown")
            if not pending:
                for field in FIELDS:
                    if row[field].lower() in MISSING:
                        issues.append("missing_" + field)
                if row["activity_type"] not in TASKS:
                    issues.append("unsupported_endpoint")
                expected = "computational" if row["activity_type"] == "MMGBSA" else "experimental"
                if row["evidence_type"] != expected:
                    issues.append("evidence_type_endpoint_mismatch")
                units = {"kcal/mol"} if expected == "computational" else {"ng/mL", "ug/mL", "mg/mL", "nM", "uM", "mM"}
                if row["unit"] not in units:
                    issues.append("unsupported_unit_no_automatic_conversion")
                if row["activity_type"] == "ATP_IC50" and not any(term in row["target"].lower() for term in ("atp synthase", "atp合酶")):
                    issues.append("ATP_target_not_explicit")
                if row["comparator"] not in {"=", "<", "<=", ">", ">="}:
                    issues.append("invalid_comparator")
                if row["qc_status"] != "pass":
                    issues.append("assay_qc_not_pass")
                if row["dataset_role"] not in {"development", "holdout", "benchmark"}:
                    issues.append("invalid_dataset_role")
                try:
                    value = float(row["activity_value"])
                    if not math.isfinite(value) or (expected != "computational" and value <= 0):
                        raise ValueError()
                    row["numeric_value"] = value
                except ValueError:
                    issues.append("invalid_numeric_value")
                try:
                    measured = date.fromisoformat(row["experimental_date"])
                    if measured > date.today():
                        issues.append("future_measurement_date")
                except ValueError:
                    issues.append("invalid_measurement_date")
                try:
                    evidence = within(self.project, row["evidence_file"])
                    allowed = [self.project / "data/experimental/incoming", self.project / "data/external/incoming"]
                    if not any(evidence.is_relative_to(p.resolve()) for p in allowed):
                        raise ValueError("Evidence must be in an incoming directory")
                    if not evidence.is_file() or file_hash(evidence) != row["evidence_sha256"].lower():
                        issues.append("missing_or_mismatched_evidence_hash")
                except (ValueError, OSError):
                    issues.append("invalid_evidence_path")
            row.update(source_row=line, issues=issues,
                       status="pending" if pending and not issues else "quarantined" if issues else "valid_pending_review")
            results.append(row)
        # No ambiguous record identifiers or ID/structure mappings, even for new users.
        id_counts = Counter(row["record_id"] for row in results if row["record_id"])
        structures = defaultdict(set)
        for row in results:
            structures[row["compound_id"]].add(row["canonical_smiles"])
        for row in results:
            if id_counts[row["record_id"]] > 1:
                row["issues"].append("duplicate_record_id")
            if len(structures[row["compound_id"]]) > 1:
                row["issues"].append("batch_identity_conflict")
            if row["issues"]:
                row["status"] = "quarantined"
        counts = Counter(row["status"] for row in results)
        return results, {"rows": len(results), "counts": dict(counts),
                         "input_sha256": file_hash(Path(input_path)),
                         "scientific_authenticity": "requires_human_source_review",
                         "training_performed": False}

    def ingest(self, input_path: str | Path) -> dict:
        # Validate a bytes snapshot, not a mutable caller path.
        batch = identifier("feedback")
        dest = self.root / "imports" / batch
        dest.mkdir(parents=True, exist_ok=False)
        shutil.copyfile(input_path, dest / "raw.csv")
        rows, audit = self.validate(dest / "raw.csv")
        for row in rows:
            if row["status"] == "valid_pending_review":
                source = within(self.project, row["evidence_file"])
                evidence_dest = dest / "evidence" / row["evidence_sha256"].lower()
                evidence_dest.parent.mkdir(exist_ok=True)
                if not evidence_dest.exists():
                    shutil.copyfile(source, evidence_dest)
                if file_hash(evidence_dest) != row["evidence_sha256"].lower():
                    raise ValueError("Evidence changed during ingestion")
        write_json_new(dest / "validated.json", rows)
        audit.update(batch_id=batch, imported_at=now(), validated_sha256=file_hash(dest / "validated.json"))
        write_json_new(dest / "manifest.json", audit)
        return audit

    def review(self, batch_id: str, reviewer: str, accepted_record_ids: list[str]) -> dict:
        if not reviewer.strip() or reviewer.strip().lower() in MISSING:
            raise ValueError("Named human reviewer is required")
        dest = self.root / "imports" / safe_id(batch_id)
        manifest = read_json(dest / "manifest.json")
        if file_hash(dest / "validated.json") != manifest["validated_sha256"] or file_hash(dest / "raw.csv") != manifest["input_sha256"]:
            raise ValueError("Feedback import integrity check failed")
        rows = read_json(dest / "validated.json")
        valid = {r["record_id"] for r in rows if r["status"] == "valid_pending_review"}
        if not set(accepted_record_ids).issubset(valid):
            raise ValueError("Only valid records can be human-approved")
        review = {"batch_id": batch_id, "reviewer": reviewer.strip(), "reviewed_at": now(),
                  "accepted_record_ids": sorted(set(accepted_record_ids)),
                  "validated_sha256": manifest["validated_sha256"],
                  "attestation": "human_review_of_source_and_assay; not machine_verified_scientific_truth"}
        write_json_new(dest / "review.json", review)
        return review

    def snapshot(self) -> dict:
        collected, sources = [], []
        for path in sorted((self.root / "imports").glob("*/review.json")):
            review, audit = read_json(path), read_json(path.parent / "manifest.json")
            validated = path.parent / "validated.json"
            if file_hash(validated) != review["validated_sha256"] or file_hash(path.parent / "raw.csv") != audit["input_sha256"]:
                raise ValueError("Reviewed batch integrity mismatch")
            accepted = set(review["accepted_record_ids"])
            for row in read_json(validated):
                if row["record_id"] in accepted:
                    if row["status"] != "valid_pending_review":
                        raise ValueError("Invalid reviewed record")
                    if file_hash(path.parent / "evidence" / row["evidence_sha256"].lower()) != row["evidence_sha256"].lower():
                        raise ValueError("Archived evidence integrity mismatch")
                    collected.append({**row, "batch_id": review["batch_id"], "reviewer": review["reviewer"]})
            sources.append({"batch_id": review["batch_id"], "review_sha256": file_hash(path)})
        # Exact repeated imports don't increase n. Conflicting copies are quarantined.
        dedup = defaultdict(list)
        for row in collected:
            key = tuple(row.get(k, "") for k in ["record_id", "reference"])
            dedup[key].append(row)
        records, conflicts = [], []
        for group in dedup.values():
            signatures = {json.dumps({k: row.get(k) for k in FIELDS}, sort_keys=True) for row in group}
            if len(signatures) > 1:
                conflicts.extend(group)
            else:
                records.append(group[0])
        id_structures = defaultdict(set)
        for row in records:
            id_structures[row["compound_id"]].add(row["canonical_smiles"])
        bad_ids = {key for key, values in id_structures.items() if len(values) > 1}
        conflicts.extend(r for r in records if r["compound_id"] in bad_ids)
        records = [r for r in records if r["compound_id"] not in bad_ids]
        heldout = {r["canonical_smiles"] for r in records if r["dataset_role"] in {"holdout", "benchmark"}}
        for row in records:
            role_conflict = row["dataset_role"] == "development" and row["canonical_smiles"] in heldout
            row["training_eligible"] = bool(row["comparator"] == "=" and row["dataset_role"] == "development" and not role_conflict)
            row["eligibility_reason"] = "heldout_structure_overlap" if role_conflict else "censored_not_exact_label" if row["comparator"] != "=" else "evaluation_only" if row["dataset_role"] != "development" else "reviewed_exact_value"
            row["stratum"] = json.dumps([row[k] for k in GROUP_FIELDS], ensure_ascii=False)
        snapshot_id = identifier("snapshot")
        dest = self.root / "snapshots" / snapshot_id
        dest.mkdir(parents=True, exist_ok=False)
        columns = FIELDS + ["task", "scaffold", "numeric_value", "batch_id", "reviewer", "training_eligible", "eligibility_reason", "stratum"]
        write_csv_new(dest / "reviewed_records.csv", records, columns)
        write_json_new(dest / "conflicts.json", conflicts)
        for task in TASKS.values():
            write_csv_new(dest / (task + ".csv"), [r for r in records if r["task"] == task], columns)
        strata = defaultdict(list)
        for row in records:
            strata[row["stratum"]].append(row)
        task_summary = []
        for stratum, rows in sorted(strata.items()):
            training = [r for r in rows if r["training_eligible"]]
            task_summary.append({"stratum": stratum, "records": len(rows),
                                 "eligible_structures": len({r["canonical_smiles"] for r in training}),
                                 "eligible_scaffolds": len({r["scaffold"] for r in training}),
                                 "exact_evaluation_structures": len({r["canonical_smiles"] for r in rows if r["dataset_role"] != "development" and r["comparator"] == "="})})
        manifest = {"snapshot_id": snapshot_id, "created_at": now(), "records": len(records),
                    "status": "empty_waiting_for_reviewed_evidence" if not records else "reviewed_snapshot_ready_for_design_review",
                    "conflicting_records": len(conflicts), "sources": sources, "strata": task_summary,
                    "record_sha256": file_hash(dest / "reviewed_records.csv"),
                    "training_performed": False, "model_change": "none",
                    "promotion_allowed": False,
                    "next_gates": ["prospective_or_scaffold_holdout_design", "endpoint_specific_label_policy",
                                   "explicit_training_authorization", "compare_frozen_baseline", "human_release_review"],
                    "limitations": ["replicates are not independent compounds", "no cross-unit pooling",
                                    "no unreviewed labels", "no automatic replacement of historic models"]}
        write_json_new(dest / "iteration_manifest.json", manifest)
        return manifest

    def status(self) -> dict:
        imports = sorted((self.root / "imports").glob("*/manifest.json"))
        snapshots = sorted((self.root / "snapshots").glob("*/iteration_manifest.json"))
        return {"imports": len(imports), "reviewed_batches": len(list((self.root / "imports").glob("*/review.json"))),
                "snapshots": len(snapshots), "training_performed_by_feedback_store": False,
                "latest_snapshot": max((read_json(p) for p in snapshots), key=lambda x: x["created_at"], default=None)}

    def evidence_for(self, compound_id: str) -> list[dict]:
        latest = self.status()["latest_snapshot"]
        if not latest:
            return []
        path = self.root / "snapshots" / latest["snapshot_id"] / "reviewed_records.csv"
        if file_hash(path) != latest["record_sha256"]:
            raise ValueError("Feedback snapshot integrity failure")
        with path.open(encoding="utf-8", newline="") as stream:
            return [dict(row) for row in csv.DictReader(stream) if row["compound_id"] == compound_id]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["validate", "ingest", "review", "snapshot", "status"])
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--input", type=Path)
    parser.add_argument("--batch-id")
    parser.add_argument("--reviewer")
    parser.add_argument("--accept", nargs="*", default=[])
    args = parser.parse_args()
    store = FeedbackStore(args.project_root)
    if args.command in {"validate", "ingest"} and args.input is None:
        parser.error("--input is required")
    if args.command == "validate":
        result = store.validate(args.input)[1]
    elif args.command == "ingest":
        result = store.ingest(args.input)
    elif args.command == "review":
        if not args.batch_id or not args.reviewer:
            parser.error("--batch-id and --reviewer are required")
        result = store.review(args.batch_id, args.reviewer, args.accept)
    else:
        result = getattr(store, args.command)()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
