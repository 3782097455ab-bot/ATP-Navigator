"""Versioned external-data import pipeline for ATP-Navigator v2.0.

The pipeline validates provenance and evidence semantics before it computes
common molecular features. It never edits Dataset v0.2, existing models, or
baseline results. Imported evidence is stored in long form so experimental
activity, docking scores, and binding energies are not treated as one label.

Examples
--------
Validate the empty/template schema::

    python src/data_import_pipeline.py validate \
        --input data/External_Dataset_Format_v1.csv

Create a versioned import without training::

    python src/data_import_pipeline.py ingest --input external_records.csv

Create a versioned import and retrain compatible task baselines::

    python src/data_import_pipeline.py all --input external_records.csv
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
import shutil
import sys
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


FORMAT_VERSION = "External_Dataset_Format_v1"
PIPELINE_VERSION = "2.0.0"

CORE_COLUMNS = [
    "compound_id",
    "smiles",
    "target",
    "organism",
    "activity_type",
    "activity_value",
    "docking_score",
    "binding_energy",
    "source",
    "reference",
]

TEMPLATE_COLUMNS = [
    "compound_id",
    "smiles",
    "target",
    "target_name",
    "protein_id",
    "organism",
    "activity_type",
    "activity_relation",
    "activity_value",
    "activity_unit",
    "assay_type",
    "docking_score",
    "docking_protocol",
    "binding_energy",
    "binding_energy_type",
    "source",
    "source_record_id",
    "reference",
    "license",
    "retrieved_date",
]

ACTIVITY_TYPES = {"IC50", "MIC", "KI", "KD"}
ACTIVITY_RELATIONS = {"", "=", "<", ">", "<=", ">=", "~"}
MOLAR_FACTORS = {
    "M": 1.0,
    "MM": 1e-3,
    "UM": 1e-6,
    "ΜM": 1e-6,
    "NM": 1e-9,
    "PM": 1e-12,
}

DESCRIPTOR_COLUMNS = [
    "desc_mol_wt",
    "desc_logp",
    "desc_tpsa",
    "desc_hbd",
    "desc_hba",
    "desc_rotatable_bonds",
    "desc_aromatic_ring_count",
    "desc_fraction_csp3",
    "desc_heavy_atom_count",
    "desc_ring_count",
    "desc_formal_charge",
]
MORGAN_COLUMNS = [f"morgan1024_{index:04d}" for index in range(1024)]
COMMON_FEATURE_COLUMNS = MORGAN_COLUMNS + DESCRIPTOR_COLUMNS


@dataclass(frozen=True)
class ValidationIssue:
    severity: str
    code: str
    row: int | None
    field: str
    message: str


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def slug(value: str) -> str:
    output = re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")
    return output or "unknown"


def parse_number(value: str) -> float | None:
    text = value.strip()
    if not text:
        return None
    number = float(text)
    if not math.isfinite(number):
        raise ValueError("value must be finite")
    return number


def read_csv_records(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        headers = list(reader.fieldnames or [])
        rows: list[dict[str, str]] = []
        for raw in reader:
            row = {key: (value or "").strip() for key, value in raw.items() if key is not None}
            if any(row.values()):
                rows.append(row)
    return headers, rows


def validate_external_csv(path: Path) -> tuple[list[str], list[dict[str, str]], list[ValidationIssue]]:
    issues: list[ValidationIssue] = []
    if not path.exists():
        return [], [], [ValidationIssue("error", "file_missing", None, "", f"File not found: {path}")]
    if not path.is_file():
        return [], [], [ValidationIssue("error", "not_a_file", None, "", f"Not a file: {path}")]

    try:
        headers, rows = read_csv_records(path)
    except (OSError, UnicodeError, csv.Error) as exc:
        return [], [], [ValidationIssue("error", "csv_unreadable", None, "", str(exc))]

    if not headers:
        return headers, rows, [ValidationIssue("error", "missing_header", None, "", "CSV header is missing")]
    if len(headers) != len(set(headers)):
        issues.append(ValidationIssue("error", "duplicate_header", 1, "", "CSV has duplicate column names"))
    for column in CORE_COLUMNS:
        if column not in headers:
            issues.append(ValidationIssue("error", "missing_column", 1, column, "Required column is missing"))
    if any(issue.severity == "error" for issue in issues):
        return headers, rows, issues

    rdkit_chem = None
    if rows:
        try:
            from rdkit import Chem

            rdkit_chem = Chem
        except ImportError:
            issues.append(
                ValidationIssue(
                    "error",
                    "dependency_missing",
                    None,
                    "smiles",
                    "RDKit is required to validate non-empty external data",
                )
            )

    seen_source_records: set[tuple[str, str]] = set()
    compound_smiles: dict[str, str] = {}
    for index, row in enumerate(rows, start=2):
        def value(field: str) -> str:
            return row.get(field, "").strip()

        for field in ("smiles", "target", "organism", "source", "reference"):
            if not value(field):
                issues.append(ValidationIssue("error", "missing_value", index, field, "Required value is blank"))

        evidence_fields = ("activity_value", "docking_score", "binding_energy")
        if not any(value(field) for field in evidence_fields):
            issues.append(
                ValidationIssue(
                    "error",
                    "evidence_missing",
                    index,
                    "",
                    "At least one activity, docking, or binding-energy value is required",
                )
            )

        for field in evidence_fields:
            try:
                parse_number(value(field))
            except ValueError:
                issues.append(ValidationIssue("error", "invalid_number", index, field, "Expected a finite number"))

        activity_value = value("activity_value")
        activity_type = value("activity_type").upper()
        relation = value("activity_relation")
        if activity_value:
            if activity_type not in ACTIVITY_TYPES:
                issues.append(
                    ValidationIssue(
                        "error",
                        "activity_type_invalid",
                        index,
                        "activity_type",
                        "Use IC50, MIC, Ki, or Kd",
                    )
                )
            if "activity_unit" not in headers or not value("activity_unit"):
                issues.append(
                    ValidationIssue(
                        "error",
                        "activity_unit_missing",
                        index,
                        "activity_unit",
                        "An activity value requires its original unit",
                    )
                )
            if relation not in ACTIVITY_RELATIONS:
                issues.append(
                    ValidationIssue(
                        "error",
                        "activity_relation_invalid",
                        index,
                        "activity_relation",
                        "Use =, <, >, <=, >=, ~, or blank",
                    )
                )
        elif activity_type:
            issues.append(
                ValidationIssue(
                    "warning",
                    "activity_value_missing",
                    index,
                    "activity_value",
                    "activity_type is present but activity_value is blank",
                )
            )

        if value("docking_score") and not value("docking_protocol"):
            issues.append(
                ValidationIssue(
                    "warning",
                    "docking_protocol_missing",
                    index,
                    "docking_protocol",
                    "Score is retained, but cannot be compared across an unknown protocol",
                )
            )
        if value("binding_energy") and not value("binding_energy_type"):
            issues.append(
                ValidationIssue(
                    "warning",
                    "binding_energy_type_missing",
                    index,
                    "binding_energy_type",
                    "Specify MMGBSA, FEP, experimental dG, or another method",
                )
            )
        if not value("protein_id"):
            issues.append(
                ValidationIssue(
                    "warning",
                    "protein_id_missing",
                    index,
                    "protein_id",
                    "Target transfer is lower confidence without a Protein ID",
                )
            )
        if not value("license"):
            issues.append(
                ValidationIssue(
                    "warning",
                    "license_missing",
                    index,
                    "license",
                    "Reuse eligibility must be checked before redistribution",
                )
            )

        retrieved_date = value("retrieved_date")
        if retrieved_date:
            try:
                datetime.strptime(retrieved_date, "%Y-%m-%d")
            except ValueError:
                issues.append(
                    ValidationIssue(
                        "error",
                        "date_invalid",
                        index,
                        "retrieved_date",
                        "Use ISO date YYYY-MM-DD",
                    )
                )

        smiles = value("smiles")
        identity_smiles = smiles
        if rdkit_chem is not None and smiles:
            molecule = rdkit_chem.MolFromSmiles(smiles)
            if molecule is None:
                issues.append(
                    ValidationIssue("error", "smiles_invalid", index, "smiles", "RDKit could not parse SMILES")
                )
            else:
                identity_smiles = rdkit_chem.MolToSmiles(molecule, canonical=True, isomericSmiles=True)

        compound_id = value("compound_id")
        if compound_id:
            prior = compound_smiles.setdefault(compound_id, identity_smiles)
            if prior != identity_smiles:
                issues.append(
                    ValidationIssue(
                        "error",
                        "compound_id_conflict",
                        index,
                        "compound_id",
                        "The same compound_id is associated with different raw SMILES",
                    )
                )

        source_record_id = value("source_record_id")
        if source_record_id:
            key = (value("source"), source_record_id)
            if key in seen_source_records:
                issues.append(
                    ValidationIssue(
                        "warning",
                        "source_record_duplicate",
                        index,
                        "source_record_id",
                        "Duplicate source/source_record_id; exact duplicates are removed during import",
                    )
                )
            seen_source_records.add(key)

    if not rows:
        issues.append(
            ValidationIssue(
                "info",
                "empty_template",
                None,
                "",
                "Schema is valid and contains no data rows; no import or training will be performed",
            )
        )
    return headers, rows, issues


def validation_summary(headers: list[str], rows: list[dict[str, str]], issues: list[ValidationIssue]) -> dict[str, Any]:
    counts = {severity: sum(issue.severity == severity for issue in issues) for severity in ("error", "warning", "info")}
    return {
        "format_version": FORMAT_VERSION,
        "pipeline_version": PIPELINE_VERSION,
        "columns": len(headers),
        "records": len(rows),
        "status": "invalid" if counts["error"] else ("valid_empty_template" if not rows else "valid"),
        "issue_counts": counts,
        "issues": [asdict(issue) for issue in issues],
    }


def normalize_unit(unit: str) -> str:
    return unit.strip().replace("μ", "µ").upper()


def normalize_and_featurize(rows: list[dict[str, str]]) -> tuple[Any, Any]:
    try:
        import pandas as pd
        from rdkit import Chem
        from rdkit.Chem import Crippen, Descriptors, Lipinski, rdFingerprintGenerator, rdMolDescriptors
        from rdkit.Chem.Scaffolds import MurckoScaffold
    except ImportError as exc:
        raise RuntimeError("pandas and RDKit are required for ingest/all operations") from exc

    fingerprint_generator = rdFingerprintGenerator.GetMorganGenerator(
        radius=2,
        fpSize=1024,
        includeChirality=True,
    )
    normalized_rows: list[dict[str, Any]] = []
    feature_rows: dict[str, dict[str, Any]] = {}
    identity_map: dict[str, str] = {}

    for raw in rows:
        mol = Chem.MolFromSmiles(raw["smiles"])
        if mol is None:
            raise ValueError(f"Invalid SMILES passed validation: {raw['smiles']}")
        canonical_smiles = Chem.MolToSmiles(mol, canonical=True, isomericSmiles=True)
        inchi_key = Chem.MolToInchiKey(mol)
        compound_id = raw.get("compound_id", "").strip() or f"EXT-{inchi_key}"
        previous = identity_map.setdefault(compound_id, canonical_smiles)
        if previous != canonical_smiles:
            raise ValueError(f"compound_id {compound_id!r} maps to multiple canonical structures")

        normalized = {column: raw.get(column, "").strip() for column in TEMPLATE_COLUMNS}
        normalized.update(
            {
                "compound_id": compound_id,
                "canonical_smiles": canonical_smiles,
                "inchi_key": inchi_key,
                "activity_type": normalized["activity_type"].upper(),
                "activity_relation": normalized["activity_relation"] or "=",
                "activity_value_numeric": parse_number(normalized["activity_value"]),
                "docking_score_numeric": parse_number(normalized["docking_score"]),
                "binding_energy_numeric": parse_number(normalized["binding_energy"]),
            }
        )

        activity_molar = None
        p_activity = None
        activity_value = normalized["activity_value_numeric"]
        unit_key = normalize_unit(normalized["activity_unit"])
        factor = MOLAR_FACTORS.get(unit_key)
        if activity_value is not None and activity_value > 0 and factor is not None:
            activity_molar = activity_value * factor
            if normalized["activity_relation"] == "=":
                p_activity = -math.log10(activity_molar)
        normalized["activity_value_molar"] = activity_molar
        normalized["p_activity"] = p_activity

        evidence_kinds = []
        if activity_value is not None:
            evidence_kinds.append("experimental_activity")
        if normalized["docking_score_numeric"] is not None:
            evidence_kinds.append("computational_docking")
        if normalized["binding_energy_numeric"] is not None:
            evidence_kinds.append("computational_binding_energy")
        normalized["evidence_type"] = ";".join(evidence_kinds)
        record_material = json.dumps(normalized, ensure_ascii=False, sort_keys=True, default=str)
        normalized["record_uid"] = "EXTREC-" + hashlib.sha256(record_material.encode("utf-8")).hexdigest()[:16].upper()
        normalized_rows.append(normalized)

        if inchi_key not in feature_rows:
            scaffold_mol = MurckoScaffold.GetScaffoldForMol(mol)
            scaffold = Chem.MolToSmiles(scaffold_mol, canonical=True) if scaffold_mol.GetNumAtoms() else "ACYCLIC"
            fingerprint = fingerprint_generator.GetFingerprint(mol)
            bit_values = [int(character) for character in fingerprint.ToBitString()]
            features: dict[str, Any] = {
                "compound_id": compound_id,
                "canonical_smiles": canonical_smiles,
                "inchi_key": inchi_key,
                "scaffold": scaffold,
            }
            features.update(dict(zip(MORGAN_COLUMNS, bit_values, strict=True)))
            features.update(
                {
                    "desc_mol_wt": Descriptors.MolWt(mol),
                    "desc_logp": Crippen.MolLogP(mol),
                    "desc_tpsa": rdMolDescriptors.CalcTPSA(mol),
                    "desc_hbd": Lipinski.NumHDonors(mol),
                    "desc_hba": Lipinski.NumHAcceptors(mol),
                    "desc_rotatable_bonds": Lipinski.NumRotatableBonds(mol),
                    "desc_aromatic_ring_count": rdMolDescriptors.CalcNumAromaticRings(mol),
                    "desc_fraction_csp3": rdMolDescriptors.CalcFractionCSP3(mol),
                    "desc_heavy_atom_count": mol.GetNumHeavyAtoms(),
                    "desc_ring_count": rdMolDescriptors.CalcNumRings(mol),
                    "desc_formal_charge": Chem.GetFormalCharge(mol),
                }
            )
            feature_rows[inchi_key] = features

    normalized_frame = pd.DataFrame(normalized_rows).drop_duplicates(subset=["record_uid"], keep="first")
    feature_frame = pd.DataFrame(feature_rows.values())
    return normalized_frame, feature_frame


def build_learning_records(normalized: Any, features: Any) -> Any:
    import pandas as pd

    feature_lookup = features.set_index("inchi_key", drop=False)
    output: list[dict[str, Any]] = []
    for record in normalized.to_dict(orient="records"):
        common = feature_lookup.loc[record["inchi_key"]].to_dict()
        base = {
            **common,
            "compound_id": record["compound_id"],
            "source_dataset": "external_v1",
            "source_record_uid": record["record_uid"],
            "target": record["target"],
            "target_name": record["target_name"],
            "protein_id": record["protein_id"],
            "organism": record["organism"],
            "source": record["source"],
            "reference": record["reference"],
        }
        if record["activity_value_numeric"] is not None and not pd.isna(record["activity_value_numeric"]):
            if record["p_activity"] is not None and not pd.isna(record["p_activity"]):
                activity_type = slug(record["activity_type"])
                task = ":".join(
                    ["external", "pactivity", activity_type, slug(record["target"]), slug(record["organism"])]
                )
                output.append(
                    {
                        **base,
                        "evidence_type": "experimental_activity",
                        "label_family": f"p{record['activity_type']}",
                        "label_value": float(record["p_activity"]),
                        "label_direction": "higher_is_better",
                        "task_key": task,
                        "protocol": record["assay_type"],
                    }
                )
        if record["docking_score_numeric"] is not None and not pd.isna(record["docking_score_numeric"]):
            protocol = slug(record["docking_protocol"])
            output.append(
                {
                    **base,
                    "evidence_type": "computational_docking",
                    "label_family": "docking_score",
                    "label_value": float(record["docking_score_numeric"]),
                    "label_direction": "lower_is_better",
                    "task_key": f"external:docking:{protocol}:{slug(record['target'])}:{slug(record['organism'])}",
                    "protocol": record["docking_protocol"],
                }
            )
        if record["binding_energy_numeric"] is not None and not pd.isna(record["binding_energy_numeric"]):
            method = slug(record["binding_energy_type"])
            output.append(
                {
                    **base,
                    "evidence_type": "computational_binding_energy",
                    "label_family": record["binding_energy_type"] or "binding_energy_unknown_method",
                    "label_value": float(record["binding_energy_numeric"]),
                    "label_direction": "lower_is_better",
                    "task_key": f"external:binding_energy:{method}:{slug(record['target'])}:{slug(record['organism'])}",
                    "protocol": record["binding_energy_type"],
                }
            )
    columns = [
        "source_dataset",
        "source_record_uid",
        "compound_id",
        "canonical_smiles",
        "inchi_key",
        "scaffold",
        "target",
        "target_name",
        "protein_id",
        "organism",
        "evidence_type",
        "label_family",
        "label_value",
        "label_direction",
        "task_key",
        "protocol",
        "source",
        "reference",
        *COMMON_FEATURE_COLUMNS,
    ]
    return pd.DataFrame(output, columns=columns)


def build_merged_registry(project_root: Path, external_learning: Any) -> Any:
    import pandas as pd

    internal_path = project_root / "data" / "dataset_v0.2" / "samples.csv"
    internal = pd.read_csv(internal_path, low_memory=False)
    missing_features = [column for column in COMMON_FEATURE_COLUMNS if column not in internal.columns]
    if missing_features:
        raise ValueError(f"Dataset v0.2 is missing common features: {missing_features[:5]}")

    internal_registry = pd.DataFrame(
        {
            "source_dataset": "dataset_v0.2",
            "source_record_uid": internal["compound_id"].map(lambda value: f"INTERNAL-{value}"),
            "compound_id": internal["compound_id"],
            "canonical_smiles": internal["canonical_smiles"],
            "inchi_key": internal["inchi_key"],
            "scaffold": internal["scaffold"],
            "target": "F1F0-ATP synthase",
            "target_name": "F1F0-ATP synthase",
            "protein_id": "",
            "organism": "Acinetobacter baumannii",
            "evidence_type": "computational_binding_energy",
            "label_family": internal["label_type"],
            "label_value": internal["label_score"],
            "label_direction": "lower_is_better",
            "task_key": "internal:mmgbsa:vsw_static:ab_f1f0_atp_synthase",
            "protocol": internal["label_protocol"],
            "source": internal["label_source"],
            "reference": "ATP-Navigator internal VSW workflow",
        }
    )
    internal_registry = pd.concat(
        [internal_registry, internal[COMMON_FEATURE_COLUMNS].reset_index(drop=True)], axis=1
    )
    return pd.concat([internal_registry, external_learning], ignore_index=True, sort=False)


def write_import_bundle(
    project_root: Path,
    input_path: Path,
    import_id: str,
    normalized: Any,
    features: Any,
    learning: Any,
    merged: Any,
    validation: dict[str, Any],
) -> Path:
    import_root = project_root / "data" / "external" / "imports"
    import_root.mkdir(parents=True, exist_ok=True)
    final_dir = import_root / import_id
    if final_dir.exists():
        raise FileExistsError(f"Import already exists and was not overwritten: {final_dir}")

    temporary_dir = Path(tempfile.mkdtemp(prefix=f".{import_id}-", dir=import_root))
    try:
        normalized.to_csv(temporary_dir / "normalized_records.csv", index=False, encoding="utf-8-sig")
        features.to_csv(temporary_dir / "common_features.csv", index=False, encoding="utf-8-sig")
        learning.to_csv(temporary_dir / "external_learning_records.csv", index=False, encoding="utf-8-sig")
        merged.to_csv(temporary_dir / "merged_training_registry.csv", index=False, encoding="utf-8-sig")
        (temporary_dir / "validation.json").write_text(
            json.dumps(validation, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        manifest = {
            "pipeline_version": PIPELINE_VERSION,
            "format_version": FORMAT_VERSION,
            "import_id": import_id,
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "input_file": str(input_path.resolve()),
            "input_sha256": sha256_file(input_path),
            "external_source_rows": int(len(normalized)),
            "external_unique_structures": int(len(features)),
            "external_learning_rows": int(len(learning)),
            "merged_registry_rows": int(len(merged)),
            "immutable_inputs": ["data/dataset_v0.2/samples.csv"],
            "label_policy": "long_form_no_cross_task_label_mixing",
        }
        (temporary_dir / "import_manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        temporary_dir.rename(final_dir)
    except Exception:
        shutil.rmtree(temporary_dir, ignore_errors=True)
        raise
    return final_dir


def ndcg_at_k(y_true: Any, y_pred: Any, direction: str, k: int = 5) -> float:
    import numpy as np
    from sklearn.metrics import ndcg_score

    truth = np.asarray(y_true, dtype=float)
    prediction = np.asarray(y_pred, dtype=float)
    if direction == "lower_is_better":
        relevance = truth.max() - truth
        ranking_score = -prediction
    else:
        relevance = truth - truth.min()
        ranking_score = prediction
    return float(ndcg_score(relevance.reshape(1, -1), ranking_score.reshape(1, -1), k=min(k, len(truth))))


def run_versioned_retraining(
    project_root: Path,
    import_id: str,
    merged: Any,
    minimum_samples: int,
) -> dict[str, Any]:
    try:
        import joblib
        import numpy as np
        import pandas as pd
        from lightgbm import LGBMRegressor
        from sklearn.model_selection import GroupKFold, LeaveOneGroupOut
    except ImportError as exc:
        return {
            "status": "dependency_missing",
            "message": "Training skipped; install requirements.txt dependencies",
            "detail": str(exc),
            "tasks": [],
        }

    model_dir = project_root / "models" / "external_imports" / import_id
    result_dir = project_root / "results" / "external_imports" / import_id
    if model_dir.exists() or result_dir.exists():
        raise FileExistsError("Versioned model/result directory already exists; no output was overwritten")
    model_dir.mkdir(parents=True)
    result_dir.mkdir(parents=True)

    task_results: list[dict[str, Any]] = []
    predictions: list[Any] = []
    for task_key, task in merged.groupby("task_key", sort=True):
        task = task.dropna(subset=["label_value"]).copy()
        samples = len(task)
        unique_structures = task["inchi_key"].nunique()
        unique_scaffolds = task["scaffold"].nunique()
        status = "eligible"
        reason = ""
        if samples < minimum_samples:
            status, reason = "skipped", f"requires at least {minimum_samples} labeled rows"
        elif unique_structures != samples:
            status, reason = "skipped", "duplicate structures require assay-level aggregation policy"
        elif unique_scaffolds < 3:
            status, reason = "skipped", "requires at least 3 scaffold groups"

        result: dict[str, Any] = {
            "task_key": task_key,
            "samples": samples,
            "unique_structures": unique_structures,
            "unique_scaffolds": unique_scaffolds,
            "label_family": task["label_family"].iloc[0] if samples else "",
            "label_direction": task["label_direction"].iloc[0] if samples else "",
            "status": status,
            "reason": reason,
        }
        if status == "skipped":
            task_results.append(result)
            continue

        x = task[COMMON_FEATURE_COLUMNS].astype(float)
        y = task["label_value"].astype(float).to_numpy()
        groups = task["scaffold"].astype(str).to_numpy()
        splitter: Iterable[tuple[Any, Any]]
        if unique_scaffolds <= 12:
            splitter = LeaveOneGroupOut().split(x, y, groups)
            split_name = "leave_one_scaffold_group_out"
        else:
            splitter = GroupKFold(n_splits=5).split(x, y, groups)
            split_name = "group_kfold_5"

        oof = np.full(samples, np.nan, dtype=float)
        params = {
            "n_estimators": 160,
            "learning_rate": 0.03,
            "num_leaves": 7,
            "max_depth": 3,
            "min_child_samples": 2,
            "subsample": 0.9,
            "colsample_bytree": 0.8,
            "reg_lambda": 1.0,
            "random_state": 42,
            "verbosity": -1,
        }
        for train_index, test_index in splitter:
            model = LGBMRegressor(**params)
            model.fit(x.iloc[train_index], y[train_index])
            oof[test_index] = model.predict(x.iloc[test_index])
        if np.isnan(oof).any():
            raise RuntimeError(f"OOF prediction is incomplete for task {task_key}")

        full_model = LGBMRegressor(**params)
        full_model.fit(x, y)
        model_name = slug(task_key) + ".joblib"
        joblib.dump(
            {
                "model": full_model,
                "feature_columns": COMMON_FEATURE_COLUMNS,
                "task_key": task_key,
                "label_direction": task["label_direction"].iloc[0],
                "pipeline_version": PIPELINE_VERSION,
            },
            model_dir / model_name,
        )

        spearman = float(pd.Series(y).corr(pd.Series(oof), method="spearman"))
        rmse = float(np.sqrt(np.mean((y - oof) ** 2)))
        ndcg5 = ndcg_at_k(y, oof, task["label_direction"].iloc[0], k=5)
        result.update(
            {
                "status": "trained",
                "split": split_name,
                "spearman": spearman,
                "rmse": rmse,
                "ndcg_at_5": ndcg5,
                "model_file": str(model_dir / model_name),
            }
        )
        task_results.append(result)
        prediction = task[["source_dataset", "compound_id", "task_key", "label_value"]].copy()
        prediction["oof_prediction"] = oof
        predictions.append(prediction)

    pd.DataFrame(task_results).to_csv(result_dir / "task_metrics.csv", index=False, encoding="utf-8-sig")
    if predictions:
        pd.concat(predictions, ignore_index=True).to_csv(
            result_dir / "oof_predictions.csv", index=False, encoding="utf-8-sig"
        )

    external = merged.loc[merged["source_dataset"].eq("external_v1")]
    readiness = {
        "status": "completed",
        "training_policy": "independent_task_baselines_only",
        "external_prior_implemented": False,
        "external_prior_reason": "Requires a sufficiently large, independently validated compatible external task",
        "external_learning_rows": int(len(external)),
        "external_tasks": int(external["task_key"].nunique()),
        "trained_tasks": sum(result["status"] == "trained" for result in task_results),
        "tasks": task_results,
    }
    (result_dir / "training_manifest.json").write_text(
        json.dumps(readiness, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return readiness


def execute(args: argparse.Namespace) -> int:
    input_path = Path(args.input).resolve()
    project_root = Path(args.project_root).resolve()
    headers, rows, issues = validate_external_csv(input_path)
    summary = validation_summary(headers, rows, issues)
    summary["input"] = str(input_path)
    summary["input_sha256"] = sha256_file(input_path) if input_path.is_file() else None
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if summary["status"] == "invalid":
        return 2
    if args.command == "validate" or not rows:
        return 0

    normalized, features = normalize_and_featurize(rows)
    learning = build_learning_records(normalized, features)
    merged = build_merged_registry(project_root, learning)
    input_hash = summary["input_sha256"]
    import_id = args.import_id or f"extv1_{input_hash[:12]}"
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{2,80}", import_id):
        raise ValueError("import-id must be 3–81 safe filename characters")
    import_dir = write_import_bundle(
        project_root,
        input_path,
        import_id,
        normalized,
        features,
        learning,
        merged,
        summary,
    )
    output: dict[str, Any] = {"status": "imported", "import_id": import_id, "import_dir": str(import_dir)}
    if args.command == "all":
        output["training"] = run_versioned_retraining(
            project_root,
            import_id,
            merged,
            minimum_samples=args.minimum_train_samples,
        )
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate, version, featurize, merge, and retrain compatible ATP-Navigator external-data tasks."
    )
    parser.add_argument("command", choices=("validate", "ingest", "all"))
    parser.add_argument("--input", required=True, help="External Dataset Format v1 CSV")
    parser.add_argument(
        "--project-root",
        default=str(Path(__file__).resolve().parents[1]),
        help="ATP-Navigator project root",
    )
    parser.add_argument("--import-id", help="Optional immutable import version; default derives from input SHA-256")
    parser.add_argument(
        "--minimum-train-samples",
        type=int,
        default=12,
        help="Minimum labeled rows for an independent task baseline",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        return execute(args)
    except Exception as exc:  # fail closed with a concise CLI error
        print(json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False, indent=2), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
