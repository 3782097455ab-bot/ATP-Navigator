"""Standardize post-screening candidates for ATP-Navigator Phase 10.

This module performs structure processing and calls preserved models as tools.
It never trains a model and never imputes experimental ATP, MIC, or toxicity
results.  A new structure can receive a structure-only computational prior;
the full Model v3 tool is used only when every feature in its frozen contract is
available.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from rdkit import Chem, DataStructs, rdBase
from rdkit.Chem import rdFingerprintGenerator

from model_v3_pipeline import canonicalize, descriptor_row, direct_atp_reference_set


rdBase.DisableLog("rdApp.warning")

PROCESSOR_VERSION = "ATP-Navigator_Phase10_InputProcessor_v1.0"
UNKNOWN = "unknown"
JSON_FEATURE_COLUMNS = {
    "quickprop_features",
    "docking_features",
    "admet_features",
    "literature_features",
}
EXPERIMENT_STATUS_COLUMNS = [
    "experimental_ATP_inhibition",
    "experimental_MIC",
    "experimental_toxicity",
]
PRIOR_MODEL_MAP = {
    "prior_task_a_ab_mic_log10_ug_ml": "a_ab_mic_ugml.joblib",
    "prior_task_b_pa_atp_ic50_log10_ug_ml": "b_pa_atp_ic50_ugml_2024.joblib",
    "prior_task_b_mtb_atp_ic50_log10_nm": "b_mtb_atp_ic50_nm.joblib",
    "prior_task_b_ab_atp_ic50_log10_ng_ml": "b_ab_atp_ic50_ngml_2025.joblib",
}


def atomic_csv(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", newline="", delete=False, dir=path.parent, suffix=".tmp"
    ) as handle:
        temporary = Path(handle.name)
        frame.to_csv(handle, index=False)
    temporary.replace(path)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def json_object(value: Any, column: str, row_number: int) -> dict[str, Any]:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return {}
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "unknown"}:
        return {}
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Row {row_number}: {column} must be a JSON object") from exc
    if not isinstance(parsed, dict):
        raise ValueError(f"Row {row_number}: {column} must be a JSON object")
    return parsed


def generated_id(canonical_smiles: str) -> str:
    token = hashlib.sha256(canonical_smiles.encode("utf-8")).hexdigest()[:12].upper()
    return f"ATP-REQUEST-{token}"


class CandidateInputProcessor:
    """Create a traceable feature table from a standardized candidate CSV."""

    def __init__(self, project_root: str | Path) -> None:
        self.project_root = Path(project_root).resolve()
        self.generator = rdFingerprintGenerator.GetMorganGenerator(
            radius=2, fpSize=1024, includeChirality=True
        )
        self.model_dir = self.project_root / "models" / "model_v2"
        self.v2a_bundle = joblib.load(self.model_dir / "model_v2_a_structure_only.joblib")
        self.v3_bundle = joblib.load(self.project_root / "models" / "model_v3" / "model.joblib")
        self.prior_bundles = {
            output: joblib.load(self.model_dir / filename)
            for output, filename in PRIOR_MODEL_MAP.items()
        }
        dataset = pd.read_csv(
            self.project_root / "data" / "dataset_v1.0" / "ATP_Navigator_Dataset_v1.csv",
            dtype=str,
            keep_default_na=False,
        )
        self.references = direct_atp_reference_set(dataset)
        self.reference_fingerprints = []
        for smiles in self.references["canonical_smiles"]:
            _, _, molecule = canonicalize(smiles)
            self.reference_fingerprints.append(self.generator.GetFingerprint(molecule))
        self.known_scaffolds = set(self.references["scaffold"])
        self.model_hashes = {
            "model_v2a": sha256(self.model_dir / "model_v2_a_structure_only.joblib"),
            "model_v3": sha256(self.project_root / "models" / "model_v3" / "model.joblib"),
            **{
                output: sha256(self.model_dir / filename)
                for output, filename in PRIOR_MODEL_MAP.items()
            },
        }

    @staticmethod
    def _normalize_headers(frame: pd.DataFrame) -> pd.DataFrame:
        aliases = {
            "smiles": "SMILES",
            "canonical_smiles": "SMILES",
            "mmgbsa": "mmgbsa_score",
            "static_mmgbsa_score": "mmgbsa_score",
            "glide_docking_score": "docking_score",
        }
        rename: dict[str, str] = {}
        existing = set(frame.columns)
        for column in frame.columns:
            target = aliases.get(str(column).strip().lower())
            if target and target not in existing:
                rename[column] = target
        return frame.rename(columns=rename)

    @staticmethod
    def _predict(bundle: dict[str, Any], features: dict[str, Any]) -> float:
        columns = list(bundle["feature_columns"])
        matrix = pd.DataFrame([[features[column] for column in columns]], columns=columns)
        return float(bundle["model"].predict(matrix)[0])

    def _structure_features(self, molecule: Chem.Mol) -> dict[str, float]:
        fingerprint = self.generator.GetFingerprint(molecule)
        vector = np.zeros((1024,), dtype=np.int8)
        DataStructs.ConvertToNumpyArray(fingerprint, vector)
        output = {f"morgan1024_{index:04d}": float(value) for index, value in enumerate(vector)}
        output.update(descriptor_row(molecule))
        return output

    def _similarity_features(
        self, molecule: Chem.Mol, scaffold: str
    ) -> dict[str, Any]:
        fingerprint = self.generator.GetFingerprint(molecule)
        similarities = np.asarray(
            DataStructs.BulkTanimotoSimilarity(fingerprint, self.reference_fingerprints),
            dtype=float,
        )
        nearest_index = int(np.argmax(similarities))
        nearest = self.references.iloc[nearest_index]
        return {
            "similarity_to_known_inhibitor": float(similarities[nearest_index]),
            "scaffold_seen_in_known_inhibitors": float(scaffold in self.known_scaffolds),
            "nearest_known_inhibitor_id": nearest["reference_compound_id"],
            "nearest_reference_source": nearest["data_source"],
            "reference_set_size": int(len(self.references)),
            "similarity_evidence_semantics": (
                "external direct ATP-assay structural reference; similarity is not activity"
            ),
        }

    @staticmethod
    def _numeric_feature_dict(values: dict[str, Any]) -> dict[str, float]:
        output: dict[str, float] = {}
        for key, value in values.items():
            numeric = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
            if pd.notna(numeric):
                output[str(key)] = float(numeric)
        return output

    def process(self, input_path: str | Path, output_path: str | Path) -> pd.DataFrame:
        input_path = Path(input_path).resolve()
        output_path = Path(output_path).resolve()
        raw = self._normalize_headers(pd.read_csv(input_path, dtype=str, keep_default_na=False))
        required = {"compound_id", "SMILES", "docking_score", "mmgbsa_score"}
        missing_headers = required.difference(raw.columns)
        if missing_headers:
            raise ValueError(f"Candidate input missing required headers: {sorted(missing_headers)}")
        if raw.empty:
            raise ValueError("Candidate input is empty")

        rows: list[dict[str, Any]] = []
        seen_ids: set[str] = set()
        seen_structures: dict[str, str] = {}
        for zero_index, record in raw.iterrows():
            row_number = zero_index + 2
            supplied_id = str(record.get("compound_id", "")).strip()
            supplied_smiles = str(record.get("SMILES", "")).strip()
            output: dict[str, Any] = {
                "source_row": row_number,
                "input_compound_id": supplied_id,
                "historical_alias": str(record.get("historical_alias", "")).strip(),
                "input_smiles": supplied_smiles,
                "docking_score": pd.to_numeric(record.get("docking_score"), errors="coerce"),
                "mmgbsa_score": pd.to_numeric(record.get("mmgbsa_score"), errors="coerce"),
                "source": str(record.get("source", "user_candidate_input")).strip()
                or "user_candidate_input",
            }
            for status in EXPERIMENT_STATUS_COLUMNS:
                explicit = str(record.get(status, "")).strip()
                output[status] = explicit if explicit else UNKNOWN

            molecule = Chem.MolFromSmiles(supplied_smiles) if supplied_smiles else None
            if molecule is None:
                output.update(
                    {
                        "compound_id": supplied_id or f"INVALID-ROW-{row_number}",
                        "canonical_smiles": "",
                        "scaffold": "",
                        "structure_status": "invalid_smiles",
                        "duplicate_structure_of": "",
                        "model_score": np.nan,
                        "model_used": "none",
                        "model_v3_status": "unavailable_invalid_structure",
                        "missing_computational_fields": json.dumps(
                            ["valid_SMILES"], ensure_ascii=False
                        ),
                        "input_processor_version": PROCESSOR_VERSION,
                    }
                )
                rows.append(output)
                continue

            canonical, scaffold, molecule = canonicalize(supplied_smiles)
            compound_id = supplied_id or generated_id(canonical)
            if compound_id in seen_ids:
                raise ValueError(f"Duplicate compound_id in input: {compound_id}")
            seen_ids.add(compound_id)
            duplicate_of = seen_structures.get(canonical, "")
            seen_structures.setdefault(canonical, compound_id)
            structure = self._structure_features(molecule)
            similarity = self._similarity_features(molecule, scaffold)
            feature_values: dict[str, Any] = {**structure, **similarity}

            for column in JSON_FEATURE_COLUMNS:
                parsed = json_object(record.get(column, ""), column, row_number)
                feature_values.update(self._numeric_feature_dict(parsed))
            # Wide optional fields are accepted for machine-generated pipelines.
            for column, value in record.items():
                if column in required | JSON_FEATURE_COLUMNS | set(EXPERIMENT_STATUS_COLUMNS):
                    continue
                numeric = pd.to_numeric(value, errors="coerce")
                if pd.notna(numeric):
                    feature_values[str(column)] = float(numeric)

            feature_values["glide_docking_score"] = output["docking_score"]
            for name, bundle in self.prior_bundles.items():
                feature_values[name] = self._predict(bundle, feature_values)

            v2_score = self._predict(self.v2a_bundle, feature_values)
            v3_columns = list(self.v3_bundle["feature_columns"])
            missing_v3 = [
                column
                for column in v3_columns
                if column not in feature_values or pd.isna(feature_values[column])
            ]
            if missing_v3:
                model_score = v2_score
                model_used = "Model_v2-A_structure_only_fallback"
                model_v3_status = "not_run_missing_frozen_features"
            else:
                model_score = self._predict(self.v3_bundle, feature_values)
                model_used = "Model_v3_full_frozen"
                model_v3_status = "available"

            missing_computational = []
            if pd.isna(output["docking_score"]):
                missing_computational.append("docking_score")
            if pd.isna(output["mmgbsa_score"]):
                missing_computational.append("mmgbsa_score")
            if "admet_endpoint_sum" not in feature_values:
                missing_computational.append("admet_features")
            quickprop_expected = [
                column for column in v3_columns if column.startswith("quickprop_")
            ]
            if any(column not in feature_values for column in quickprop_expected):
                missing_computational.append("complete_quickprop_features")

            output.update(
                {
                    "compound_id": compound_id,
                    "canonical_smiles": canonical,
                    "scaffold": scaffold,
                    "structure_status": "valid",
                    "duplicate_structure_of": duplicate_of,
                    "model_score": model_score,
                    "model_used": model_used,
                    "model_score_semantics": (
                        "prediction_of_static_MMGBSA_computational_ranking; not activity"
                    ),
                    "model_v3_status": model_v3_status,
                    "model_v3_missing_feature_count": len(missing_v3),
                    "model_v3_missing_features": json.dumps(missing_v3, ensure_ascii=False),
                    "missing_computational_fields": json.dumps(
                        missing_computational, ensure_ascii=False
                    ),
                    "input_processor_version": PROCESSOR_VERSION,
                    **feature_values,
                }
            )
            rows.append(output)

        processed = pd.DataFrame(rows)
        ordered = [
            "compound_id",
            "historical_alias",
            "input_compound_id",
            "canonical_smiles",
            "scaffold",
            "structure_status",
            "duplicate_structure_of",
            "docking_score",
            "mmgbsa_score",
            "model_score",
            "model_used",
            "model_v3_status",
            "missing_computational_fields",
            *EXPERIMENT_STATUS_COLUMNS,
        ]
        processed = processed[[*ordered, *[c for c in processed.columns if c not in ordered]]]
        atomic_csv(processed, output_path)
        return processed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument(
        "--output", type=Path, default=Path("results/processed_candidate_table.csv")
    )
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    processor = CandidateInputProcessor(args.project_root)
    frame = processor.process(args.input, args.output)
    print(
        json.dumps(
            {
                "processor_version": PROCESSOR_VERSION,
                "candidate_count": len(frame),
                "valid_structures": int(frame["structure_status"].eq("valid").sum()),
                "full_model_v3_available": int(frame["model_v3_status"].eq("available").sum()),
                "experimental_values_imputed": 0,
                "output": str(args.output),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
