"""Audit member-contributed datasets without changing their source workbooks.

The outputs are integration registries, not training labels.  Chemical identity is
derived only when RDKit can parse the submitted structure; raw fields are retained
verbatim for provenance and later human review.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

import pandas as pd
from rdkit import Chem


MEMBER2 = "Member2_GN_antibacterial_week1.xlsx"
MEMBER3 = "Member3_Part2_AI_Benchmark_26_audited.xlsx"
EXTERNAL_V2 = "data/dataset_v2.0/ATP_Navigator_external_dataset_v1.csv"


def _text(value: object) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _structure(smiles: object) -> tuple[str, str, str]:
    raw = _text(smiles)
    if not raw:
        return "", "", "missing"
    mol = Chem.MolFromSmiles(raw)
    if mol is None:
        return "", "", "invalid"
    return Chem.MolToSmiles(mol, canonical=True, isomericSmiles=True), Chem.MolToInchiKey(mol), "valid"


def _activity(value: object) -> tuple[str, str, float | None]:
    raw = _text(value)
    match = re.match(r"^\s*(<=|>=|<|>|=|~)?\s*([-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)\s*$", raw)
    if not match:
        return raw, "", None
    return raw, match.group(1) or "=", float(match.group(2))


def _unit(value: object) -> str:
    raw = _text(value).replace("μ", "u").replace("µ", "u")
    compact = raw.replace(" ", "")
    if compact.lower() in {"ug/ml", "mcg/ml"}:
        return "ug/mL"
    if compact.lower() == "mg/ml":
        return "mg/mL"
    # Some submitted cells contain replacement characters before g/mL.  The
    # normalized field records the intended MIC convention while raw_unit is kept.
    if compact.lower().endswith("g/ml") and compact.lower() not in {"g/ml", "mg/ml"}:
        return "ug/mL"
    return raw


def _organism(value: object) -> tuple[str, str]:
    raw = _text(value)
    genera = "Acinetobacter|Escherichia|Pseudomonas|Klebsiella|Enterobacter|Citrobacter|Salmonella|Serratia|Burkholderia|Stenotrophomonas"
    match = re.search(rf"\b(({genera})\s+[a-z][a-z.-]+)\b", raw)
    if not match:
        return "unknown", raw or "unknown"
    species = match.group(1)
    context = (raw[: match.start()] + raw[match.end() :]).strip(" ,-;") or "unspecified"
    return species, context


def _norm(value: object) -> str:
    return re.sub(r"\s+", " ", _text(value)).casefold()


def _assay_key(row: pd.Series, include_reference: bool = False) -> str:
    components = [
        _text(row.get("inchikey")),
        _norm(row.get("raw_organism", row.get("organism"))),
        _norm(row.get("endpoint", row.get("activity_type"))),
        _text(row.get("operator", "=")),
        _text(row.get("activity_value_numeric", row.get("activity_value"))),
        _norm(row.get("normalized_unit", row.get("unit"))),
    ]
    if include_reference:
        components.append(_norm(row.get("raw_reference", row.get("reference"))))
    return "|".join(components)


def audit_member2(project: Path) -> tuple[pd.DataFrame, dict]:
    source = project / "data/external/curated" / MEMBER2
    sheets = pd.read_excel(source, sheet_name=None, dtype=object)
    raw = next(iter(sheets.values())).copy()
    raw.columns = [str(column).strip() for column in raw.columns]
    expected = {"compound_id", "compound_name", "SMILES", "organism", "activity_type", "activity_value", "unit", "reference", "source_level"}
    missing = sorted(expected - set(raw.columns))
    if missing:
        raise ValueError(f"Member2 workbook is missing required columns: {missing}")

    rows: list[dict] = []
    for source_row, record in raw.reset_index(drop=True).iterrows():
        canonical, inchikey, parse_status = _structure(record["SMILES"])
        raw_value, operator, numeric = _activity(record["activity_value"])
        species, context = _organism(record["organism"])
        rows.append(
            {
                "source_row": int(source_row) + 2,
                "raw_compound_id": _text(record["compound_id"]),
                "raw_compound_name": _text(record["compound_name"]),
                "raw_smiles": _text(record["SMILES"]),
                "raw_organism": _text(record["organism"]),
                "raw_activity_type": _text(record["activity_type"]),
                "raw_activity_value": raw_value,
                "raw_unit": _text(record["unit"]),
                "raw_reference": _text(record["reference"]),
                "raw_source_level": _text(record["source_level"]),
                "canonical_smiles": canonical,
                "inchikey": inchikey,
                "rdkit_parse_status": parse_status,
                "species": species,
                "strain_resistance_context": context,
                "endpoint": _text(record["activity_type"]).upper(),
                "operator": operator,
                "activity_value_numeric": numeric,
                "normalized_unit": _unit(record["unit"]),
                "chembl_document": _text(record["reference"]) if _text(record["reference"]).upper().startswith("CHEMBL") else "",
                "provenance": f"data/external/curated/{MEMBER2}#row={int(source_row) + 2}",
                "source_file_sha256": _sha256(source),
                "training_status": "pending_endpoint_and_provenance_review",
            }
        )
    frame = pd.DataFrame(rows)
    frame["strict_assay_key"] = frame.apply(lambda row: _assay_key(row, include_reference=True), axis=1)
    frame["semantic_assay_key"] = frame.apply(_assay_key, axis=1)
    frame["exact_assay_duplicate"] = frame.duplicated("strict_assay_key", keep=False)
    frame["duplicate_group_size"] = frame.groupby("strict_assay_key")["strict_assay_key"].transform("size")

    external = pd.read_csv(project / EXTERNAL_V2, low_memory=False, dtype=object)
    ext_rows: list[dict] = []
    for _, record in external.iterrows():
        canonical, inchikey, status = _structure(record.get("canonical_smiles", ""))
        raw_value, operator, numeric = _activity(record.get("activity_value", ""))
        ext_rows.append(
            {
                "canonical_smiles": canonical,
                "inchikey": inchikey,
                "rdkit_parse_status": status,
                "organism": _text(record.get("organism", "")),
                "activity_type": _text(record.get("activity_type", "")),
                "operator": operator,
                "activity_value_numeric": numeric,
                "unit": _unit(record.get("unit", "")),
                "reference": _text(record.get("reference", "")),
            }
        )
    ext = pd.DataFrame(ext_rows)
    ext_valid = ext.loc[ext["rdkit_parse_status"].eq("valid")].copy()
    ext_valid["strict_assay_key"] = ext_valid.apply(lambda row: _assay_key(row, include_reference=True), axis=1)
    ext_valid["semantic_assay_key"] = ext_valid.apply(_assay_key, axis=1)
    ext_inchikey = set(ext_valid["inchikey"])
    ext_smiles = set(ext_valid["canonical_smiles"])
    ext_context = set(ext_valid["organism"].map(_norm))
    ext_strict = set(ext_valid["strict_assay_key"])
    ext_semantic = set(ext_valid["semantic_assay_key"])

    frame["inchikey_overlap_external_v2"] = frame["inchikey"].isin(ext_inchikey) & frame["inchikey"].ne("")
    frame["exact_structure_overlap_external_v2"] = frame["canonical_smiles"].isin(ext_smiles) & frame["canonical_smiles"].ne("")
    frame["strict_assay_overlap_external_v2"] = frame["strict_assay_key"].isin(ext_strict)
    frame["semantic_assay_overlap_external_v2"] = frame["semantic_assay_key"].isin(ext_semantic)
    frame["organism_context_overlap_external_v2"] = frame["raw_organism"].map(_norm).isin(ext_context)
    frame["integration_status"] = "candidate_increment"
    frame.loc[frame["rdkit_parse_status"].ne("valid"), "integration_status"] = "invalid_structure_quarantine"
    frame.loc[frame["strict_assay_overlap_external_v2"], "integration_status"] = "exact_assay_already_present"
    frame.loc[frame["exact_assay_duplicate"], "integration_status"] = "member_source_duplicate"

    valid = frame["rdkit_parse_status"].eq("valid")
    first_per_structure = frame.loc[valid].drop_duplicates("inchikey")
    new_structures = first_per_structure.loc[~first_per_structure["inchikey_overlap_external_v2"]]
    new_contexts = sorted(set(frame.loc[~frame["organism_context_overlap_external_v2"], "raw_organism"]) - {""})
    summary = {
        "source_file": f"data/external/curated/{MEMBER2}",
        "source_sha256": _sha256(source),
        "raw_rows": int(len(frame)),
        "valid_structures_rows": int(valid.sum()),
        "invalid_or_missing_structure_rows": int((~valid).sum()),
        "unique_structures": int(frame.loc[valid, "inchikey"].nunique()),
        "member_exact_duplicate_rows": int(frame["exact_assay_duplicate"].sum()),
        "member_exact_duplicate_groups": int(frame.loc[frame["exact_assay_duplicate"], "strict_assay_key"].nunique()),
        "structure_overlap_external_v2_unique": int(first_per_structure["inchikey_overlap_external_v2"].sum()),
        "truly_new_structures": int(len(new_structures)),
        "strict_assay_overlap_external_v2_rows": int(frame["strict_assay_overlap_external_v2"].sum()),
        "semantic_assay_overlap_external_v2_rows": int(frame["semantic_assay_overlap_external_v2"].sum()),
        "new_assay_records_strict": int((~frame["strict_assay_overlap_external_v2"] & ~frame["exact_assay_duplicate"]).sum()),
        "unique_species": int(frame["species"].nunique()),
        "new_species_or_strain_contexts": int(len(new_contexts)),
        "new_context_values": new_contexts,
        "training_performed": False,
        "source_structures_modified": False,
    }
    return frame, summary


def register_member3(project: Path) -> tuple[pd.DataFrame, dict]:
    source = project / "data/external/curated" / MEMBER3
    sheets = pd.read_excel(source, sheet_name=None, dtype=object)
    raw = sheets.get("AI_Benchmark", next(iter(sheets.values()))).copy()
    raw.columns = [str(column).strip() for column in raw.columns]
    rename = {
        "Dataset": "dataset",
        "Task": "task",
        "Data size": "size",
        "Input": "input",
        "Output": "output",
        "Split": "split",
        "Evaluation metric": "metric",
        "Source": "source",
        "Reference": "reference",
        "Relevance to ATP-Navigator": "relevance",
        "Official source URL": "official_source_url",
        "Verification status": "verification",
    }
    registry = raw.rename(columns=rename)
    keep = ["dataset", "task", "size", "input", "output", "split", "metric", "source", "reference", "relevance", "official_source_url", "verification"]
    registry = registry[[column for column in keep if column in registry]].copy()
    for column in keep:
        if column not in registry:
            registry[column] = ""
    registry = registry[keep].fillna("").astype(str)
    registry.insert(0, "benchmark_id", [f"BENCH-{index:03d}" for index in range(1, len(registry) + 1)])
    registry["registry_type"] = "benchmark_metadata_catalog"
    registry["training_allowed"] = False
    registry["execution_status"] = "not_run"
    registry["source_file"] = f"data/external/curated/{MEMBER3}"
    registry["source_sheet"] = "AI_Benchmark"
    registry["source_file_sha256"] = _sha256(source)
    summary = {
        "source_file": f"data/external/curated/{MEMBER3}",
        "source_sha256": _sha256(source),
        "benchmark_registry_count": int(len(registry)),
        "registry_type": "benchmark_metadata_catalog",
        "benchmarks_executed": 0,
        "training_records_added": 0,
        "part1_experimental_benchmark_records": "available_general_binding_only",
    }
    return registry, summary


def run(project: Path) -> dict:
    project = project.resolve()
    data_dir = project / "data/external/integrated"
    result_dir = project / "results/data_integration"
    data_dir.mkdir(parents=True, exist_ok=True)
    result_dir.mkdir(parents=True, exist_ok=True)

    member2, member2_summary = audit_member2(project)
    member3, member3_summary = register_member3(project)
    member2.to_csv(data_dir / "member2_gn_mic_audit.csv", index=False, encoding="utf-8")
    member2.loc[
        member2["rdkit_parse_status"].eq("valid")
        & ~member2["strict_assay_overlap_external_v2"]
        & ~member2["exact_assay_duplicate"]
    ].to_csv(data_dir / "member2_gn_mic_increment.csv", index=False, encoding="utf-8")
    member3.to_csv(data_dir / "benchmark_registry_v1.csv", index=False, encoding="utf-8")
    status = {"Part1 experimental benchmark records": "pending", "Part2 metadata catalog": "available", **member3_summary}
    (data_dir / "benchmark_registry_status.json").write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
    summary = {"member2": member2_summary, "member3": member3_summary}
    (result_dir / "member_data_integration_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", type=Path, default=Path(__file__).resolve().parents[2])
    args = parser.parse_args()
    print(json.dumps(run(args.project), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
