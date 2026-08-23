"""Feature construction for ATP-Navigator Phase 1 baselines.

The pipeline only consumes Dataset v0.1 tables. Missing cross-stage mappings are
kept as missing values; no compound identity is inferred from names or row order.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd
from rdkit import Chem, DataStructs
from rdkit.Chem import AllChem, Crippen, Descriptors, Lipinski, rdMolDescriptors


DESCRIPTOR_COLUMNS = [
    "desc_mol_wt",
    "desc_logp",
    "desc_tpsa",
    "desc_hbd",
    "desc_hba",
    "desc_rotatable_bonds",
    "desc_fraction_csp3",
    "desc_heavy_atom_count",
    "desc_ring_count",
    "desc_formal_charge",
]


@dataclass(frozen=True)
class FeatureConfig:
    radius: int = 2
    n_bits: int = 1024
    use_chirality: bool = True


class MoleculeFeaturePipeline:
    """Build Morgan, physicochemical and available evidence features."""

    def __init__(self, project_root: str | Path, config: FeatureConfig | None = None):
        self.project_root = Path(project_root).resolve()
        self.data_dir = self.project_root / "data"
        self.results_dir = self.project_root / "results"
        self.config = config or FeatureConfig()

    def load_tables(self) -> tuple[pd.DataFrame, pd.DataFrame]:
        molecules_path = self.data_dir / "molecules.csv"
        screening_path = self.data_dir / "screening_records.csv"
        molecules = pd.read_csv(molecules_path, dtype=str, keep_default_na=False)
        screening = pd.read_csv(screening_path, dtype={"canonical_id": str, "stage": str, "source_file": str})
        screening["canonical_id"] = screening["canonical_id"].fillna("")
        screening["score"] = pd.to_numeric(screening["score"], errors="coerce")

        required_molecule_fields = {
            "canonical_id",
            "historical_alias",
            "structure_file",
            "smiles",
            "source",
            "confidence",
        }
        required_screening_fields = {"canonical_id", "stage", "score", "source_file"}
        missing_molecule = required_molecule_fields.difference(molecules.columns)
        missing_screening = required_screening_fields.difference(screening.columns)
        if missing_molecule:
            raise ValueError(f"molecules.csv missing fields: {sorted(missing_molecule)}")
        if missing_screening:
            raise ValueError(f"screening_records.csv missing fields: {sorted(missing_screening)}")
        if molecules["canonical_id"].eq("").any():
            raise ValueError("molecules.csv contains blank canonical_id")
        if molecules["canonical_id"].duplicated().any():
            raise ValueError("molecules.csv contains duplicate canonical_id")
        return molecules, screening

    @staticmethod
    def _aggregate_stage_scores(screening: pd.DataFrame) -> pd.DataFrame:
        usable = screening.loc[screening["canonical_id"].ne("") & screening["score"].notna()].copy()
        if usable.empty:
            return pd.DataFrame(columns=["canonical_id"])

        # Lower values are preferred for HTVS/Docking/MMGBSA. Multiple HTVS poses
        # are reduced to the best pose; repeated aggregate evidence uses its mean.
        grouped_parts: list[pd.DataFrame] = []
        for stage, stage_rows in usable.groupby("stage", sort=True):
            reducer = "min" if stage in {"HTVS", "Docking"} else "mean"
            reduced = stage_rows.groupby("canonical_id", as_index=False)["score"].agg(reducer)
            reduced = reduced.rename(columns={"score": f"score_{stage}"})
            grouped_parts.append(reduced)

        merged = grouped_parts[0]
        for part in grouped_parts[1:]:
            merged = merged.merge(part, on="canonical_id", how="outer", validate="one_to_one")
        return merged

    def _smiles_features(self, smiles: str) -> dict[str, float | bool]:
        output: dict[str, float | bool] = {"smiles_valid": False}
        output.update({name: np.nan for name in DESCRIPTOR_COLUMNS})
        output.update({f"morgan_{index:04d}": np.nan for index in range(self.config.n_bits)})
        if not smiles:
            return output

        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return output

        output["smiles_valid"] = True
        output.update(
            {
                "desc_mol_wt": Descriptors.MolWt(mol),
                "desc_logp": Crippen.MolLogP(mol),
                "desc_tpsa": rdMolDescriptors.CalcTPSA(mol),
                "desc_hbd": Lipinski.NumHDonors(mol),
                "desc_hba": Lipinski.NumHAcceptors(mol),
                "desc_rotatable_bonds": Lipinski.NumRotatableBonds(mol),
                "desc_fraction_csp3": rdMolDescriptors.CalcFractionCSP3(mol),
                "desc_heavy_atom_count": Lipinski.HeavyAtomCount(mol),
                "desc_ring_count": Lipinski.RingCount(mol),
                "desc_formal_charge": Chem.GetFormalCharge(mol),
            }
        )
        fingerprint = AllChem.GetMorganGenerator(
            radius=self.config.radius,
            fpSize=self.config.n_bits,
            includeChirality=self.config.use_chirality,
        ).GetFingerprint(mol)
        array = np.zeros((self.config.n_bits,), dtype=np.int8)
        DataStructs.ConvertToNumpyArray(fingerprint, array)
        output.update({f"morgan_{index:04d}": int(value) for index, value in enumerate(array)})
        return output

    def build(self) -> tuple[pd.DataFrame, dict[str, object]]:
        molecules, screening = self.load_tables()
        stage_scores = self._aggregate_stage_scores(screening)

        smiles_features = pd.DataFrame(
            [self._smiles_features(smiles) for smiles in molecules["smiles"]],
            index=molecules.index,
        )
        feature_matrix = pd.concat([molecules.copy(), smiles_features], axis=1)
        feature_matrix = feature_matrix.merge(stage_scores, on="canonical_id", how="left", validate="one_to_one")

        quickprop_columns = [
            column
            for column in feature_matrix.columns
            if column.lower().startswith(("quickprop_", "qp_", "r_qp_", "i_qp_"))
        ]
        numeric_quickprop = []
        for column in quickprop_columns:
            converted = pd.to_numeric(feature_matrix[column], errors="coerce")
            if converted.notna().any():
                feature_matrix[column] = converted
                numeric_quickprop.append(column)

        evidence_columns = sorted(column for column in feature_matrix.columns if column.startswith("score_"))
        fingerprint_columns = [f"morgan_{index:04d}" for index in range(self.config.n_bits)]
        metadata = {
            "feature_config": asdict(self.config),
            "rows": int(len(feature_matrix)),
            "valid_smiles": int(feature_matrix["smiles_valid"].sum()),
            "invalid_or_missing_smiles": int((~feature_matrix["smiles_valid"]).sum()),
            "fingerprint_schema": {
                "prefix": "morgan_",
                "count": len(fingerprint_columns),
                "radius": self.config.radius,
                "use_chirality": self.config.use_chirality,
            },
            "descriptor_columns": DESCRIPTOR_COLUMNS,
            "evidence_columns": evidence_columns,
            "quickprop_columns": numeric_quickprop,
            "quickprop_available": bool(numeric_quickprop),
            "stage_coverage": {
                column.removeprefix("score_"): int(feature_matrix[column].notna().sum())
                for column in evidence_columns
            },
        }
        return feature_matrix, metadata

    @staticmethod
    def model_feature_columns(
        feature_matrix: pd.DataFrame,
        target_stage: str = "MMGBSA",
    ) -> list[str]:
        target_column = f"score_{target_stage}"
        descriptor_columns = [column for column in DESCRIPTOR_COLUMNS if column in feature_matrix.columns]
        fingerprint_columns = [column for column in feature_matrix.columns if column.startswith("morgan_")]
        evidence_columns = [
            column
            for column in feature_matrix.columns
            if column.startswith("score_") and column != target_column
        ]
        quickprop_columns = [
            column
            for column in feature_matrix.columns
            if column.lower().startswith(("quickprop_", "qp_", "r_qp_", "i_qp_"))
        ]
        return fingerprint_columns + descriptor_columns + sorted(evidence_columns) + sorted(quickprop_columns)

    @staticmethod
    def coverage_table(feature_matrix: pd.DataFrame, feature_columns: Iterable[str]) -> pd.DataFrame:
        rows = []
        total = len(feature_matrix)
        for column in feature_columns:
            count = int(pd.to_numeric(feature_matrix[column], errors="coerce").notna().sum())
            if column.startswith("morgan_"):
                group = "morgan"
            elif column.startswith("desc_"):
                group = "physicochemical"
            elif column.startswith("score_"):
                group = "screening_evidence"
            else:
                group = "quickprop"
            rows.append(
                {
                    "feature": column,
                    "feature_group": group,
                    "non_missing": count,
                    "coverage": count / total if total else 0.0,
                }
            )
        return pd.DataFrame(rows)

    def save(self, feature_matrix: pd.DataFrame, metadata: dict[str, object]) -> None:
        self.results_dir.mkdir(parents=True, exist_ok=True)
        feature_matrix.to_csv(self.results_dir / "feature_matrix.csv", index=False)
        columns = self.model_feature_columns(feature_matrix)
        self.coverage_table(feature_matrix, columns).to_csv(
            self.results_dir / "feature_coverage.csv", index=False
        )
        (self.results_dir / "feature_metadata.json").write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build ATP-Navigator molecular feature matrix")
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--radius", type=int, default=2)
    parser.add_argument("--n-bits", type=int, default=1024)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    pipeline = MoleculeFeaturePipeline(
        args.project_root,
        FeatureConfig(radius=args.radius, n_bits=args.n_bits),
    )
    matrix, metadata = pipeline.build()
    pipeline.save(matrix, metadata)
    print(json.dumps(metadata, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
