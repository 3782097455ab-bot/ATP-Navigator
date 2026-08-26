"""Audit the publisher's Abaucin workbook without training or re-labelling.

Read-only extraction of workbook values. Derived data are JSONL in a local,
ignored source store until redistribution rights and assay metadata are reviewed.
"""
from __future__ import annotations

import argparse
import csv
import json
import posixpath
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

import pandas as pd
from rdkit import Chem, DataStructs, rdBase
from rdkit.Chem import rdFingerprintGenerator
from rdkit.Chem.MolStandardize import rdMolStandardize

from workspace_io import file_hash, now, write_json_new

SOURCE_URL = "https://media.springernature.com/original/springer-static/esm/art%3A10.1038%2Fs41589-023-01349-8/MediaObjects/41589_2023_1349_MOESM3_ESM.xlsx"
REFERENCE = "https://doi.org/10.1038/s41589-023-01349-8"
SHEETS = ["SD1", "SD2.RDKit", "SD2.No RDKit", "SD3.Prioritized 240", "SD3.Lowest 240", "SD3.Highest 240"]


def read_source_sheet(path: Path, sheet: str) -> pd.DataFrame:
    """Read cached cell values only, never execute formulas or macros."""
    ns = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    rel_ns = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    with zipfile.ZipFile(path) as archive:
        shared = []
        if "xl/sharedStrings.xml" in archive.namelist():
            for item in ET.fromstring(archive.read("xl/sharedStrings.xml")).findall("m:si", ns):
                shared.append("".join(node.text or "" for node in item.findall(".//m:t", ns)))
        root = ET.fromstring(archive.read("xl/workbook.xml"))
        sheet_id = next(item.attrib["{" + rel_ns + "}id"] for item in root.findall("m:sheets/m:sheet", ns) if item.attrib["name"] == sheet)
        relations = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        target = next(item.attrib["Target"] for item in relations if item.attrib["Id"] == sheet_id)
        target = target.lstrip("/") if target.startswith("/") else posixpath.normpath("xl/" + target)
        rows = []
        for row in ET.fromstring(archive.read(target)).findall("m:sheetData/m:row", ns):
            cells = {}
            for cell in row.findall("m:c", ns):
                letters = "".join(c for c in cell.attrib["r"] if c.isalpha())
                index = 0
                for letter in letters:
                    index = index * 26 + ord(letter) - 64
                node = cell.find("m:v", ns)
                value = node.text if node is not None else None
                if cell.attrib.get("t") == "s" and value is not None:
                    value = shared[int(value)]
                elif cell.attrib.get("t") == "inlineStr":
                    value = "".join(t.text or "" for t in cell.findall(".//m:t", ns))
                elif value is not None and cell.attrib.get("t") not in {"str", "e"}:
                    value = float(value)
                cells[index - 1] = value
            rows.append(cells)
        headers = [rows[1].get(i) for i in range(max(rows[1]) + 1)]
        return pd.DataFrame([[row.get(i) for i in range(len(headers))] for row in rows[2:]], columns=headers)


def identities(smiles):
    mol = Chem.MolFromSmiles(str(smiles))
    if mol is None:
        return "", "", None
    canonical = Chem.MolToSmiles(mol, isomericSmiles=True)
    parent = rdMolStandardize.Uncharger().uncharge(rdMolStandardize.FragmentParent(mol))
    return canonical, Chem.MolToSmiles(parent, isomericSmiles=True), mol


def audit(workbook: Path, project: Path, output: Path) -> dict:
    rdBase.DisableLog("rdApp.warning")
    rdBase.DisableLog("rdApp.error")
    if output.exists():
        raise FileExistsError("Choose a new output directory; audit outputs are immutable")
    output.mkdir(parents=True)
    workbook_hash = file_hash(workbook)
    existing_exact, existing_parent = set(), set()
    registered = []
    for relative in ["data/dataset_v1.0/ATP_Navigator_Dataset_v1.csv", "data/dataset_v2.0/ATP_Navigator_external_dataset_v1.csv"]:
        path = project / relative
        table = pd.read_csv(path, dtype=str, keep_default_na=False)
        candidates = [c for c in ["canonical_smiles", "smiles", "SMILES"] if c in table]
        if not candidates:
            raise ValueError("No structure column in " + relative)
        for smiles in table[candidates[0]].unique():
            exact, parent, _ = identities(smiles)
            if exact:
                existing_exact.add(exact)
                existing_parent.add(parent)
        registered.append({"path": relative, "sha256": file_hash(path)})
    records, summaries, measured_mols = [], [], {}
    for sheet in SHEETS:
        frame = read_source_sheet(workbook, sheet)
        frame = frame.loc[frame["SMILES"].notna()].reset_index(drop=True)
        kind = "author_model_prediction" if sheet.startswith("SD2") else "external_experimental_growth"
        counts = {"sheet": sheet, "rows": len(frame), "evidence_kind": kind,
                  "valid_structures": 0, "overlap_existing_exact_rows": 0, "overlap_existing_parent_rows": 0}
        for index, row in frame.iterrows():
            canonical, parent, mol = identities(row["SMILES"])
            counts["valid_structures"] += int(bool(canonical))
            counts["overlap_existing_exact_rows"] += int(bool(canonical) and canonical in existing_exact)
            counts["overlap_existing_parent_rows"] += int(bool(parent) and parent in existing_parent)
            value_column = "Mean" if sheet == "SD1" else "Mean_Growth"
            raw_value = row.get(value_column)
            observed = float(raw_value) if kind != "author_model_prediction" and pd.notna(raw_value) else None
            record = {"source_record_id": f"ABAU2023:{sheet}:{index+3}", "source_sheet": sheet,
                      "source_row": index+3, "source_name": str(row.get("Name", row.get("Sample", ""))),
                      "raw_smiles": str(row["SMILES"]), "canonical_smiles": canonical,
                      "parent_smiles_for_overlap_only": parent, "evidence_kind": kind,
                      "organism": "Acinetobacter baumannii", "target": "whole_cell_growth_not_ATP_specific",
                      "activity_type": "relative_growth" if observed is not None else "unknown",
                      "observed_value": observed, "observed_value_source_column": value_column if observed is not None else None,
                      "author_prediction": float(row["Activity"]) if "Activity" in row and pd.notna(row["Activity"]) else None,
                      "overlap_existing_exact": bool(canonical) and canonical in existing_exact,
                      "overlap_existing_parent": bool(parent) and parent in existing_parent,
                      "training_eligible": False, "assay_condition_status": "requires_full_method_review",
                      "license_status": "redistribution_not_confirmed_local_only", "reference": REFERENCE,
                      "source_url": SOURCE_URL, "source_sha256": workbook_hash}
            records.append(record)
            if canonical and observed is not None:
                measured_mols[canonical] = mol
        summaries.append(counts)
    with (output / "external_evidence.jsonl").open("x", encoding="utf-8") as stream:
        for record in records:
            stream.write(json.dumps(record, ensure_ascii=False, allow_nan=False) + "\n")
    generator = rdFingerprintGenerator.GetMorganGenerator(radius=2, fpSize=1024, includeChirality=True)
    references = list(measured_mols)
    fps = [generator.GetFingerprint(measured_mols[x]) for x in references]
    internal = pd.read_csv(project / "data/model_v3/training_table.csv", usecols=["compound_id", "canonical_smiles"])
    similarities = []
    for row in internal.to_dict("records"):
        _, _, mol = identities(row["canonical_smiles"])
        values = DataStructs.BulkTanimotoSimilarity(generator.GetFingerprint(mol), fps)
        index = max(range(len(values)), key=values.__getitem__)
        similarities.append({"compound_id": row["compound_id"], "max_morgan_similarity": values[index],
                             "nearest_external_smiles": references[index], "semantics": "structural_similarity_not_activity"})
    write_json_new(output / "internal_chemical_space.json", similarities)
    manifest = {"source_url": SOURCE_URL, "reference": REFERENCE, "downloaded_file_sha256": workbook_hash,
                "audited_at": now(), "sheets": summaries, "total_extracted_rows": len(records),
                "unique_measured_structures": len(measured_mols),
                "measured_structures_absent_from_existing_exact": len(set(measured_mols) - existing_exact),
                "existing_datasets": registered, "training_performed": False, "new_internal_experiments": 0,
                "rights_status": "local_only_pending_redistribution_review",
                "limitations": ["not_MIC_not_ATP_IC50", "SD2_predictions_never_experimental_labels",
                                "assay_conditions_pending_full_method_review", "exact_overlap_not_complete_scaffold_leakage_audit"],
                "internal_similarity_min": min(x["max_morgan_similarity"] for x in similarities),
                "internal_similarity_max": max(x["max_morgan_similarity"] for x in similarities)}
    write_json_new(output / "source_audit.json", manifest)
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    print(json.dumps(audit(args.input, args.project_root, args.output), ensure_ascii=False, indent=2))
