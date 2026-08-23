"""ATP-Navigator Phase 2 feature engineering (Dataset v0.2, additive).

This module leaves the Phase 1 feature pipeline and its outputs untouched. It
constructs explicit feature blocks for ranking computational MM/GBSA labels;
it does not train a model or claim biological-activity prediction.
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
from rdkit.Chem import Crippen, Descriptors, Lipinski, rdFingerprintGenerator, rdMolDescriptors


DESCRIPTOR_COLUMNS_V2 = [
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

DOCKING_COLUMNS = [
    "glide_docking_score",
    "glide_gscore",
    "glide_emodel",
    "glide_energy",
    "glide_evdw",
    "glide_ecoul",
    "glide_einternal",
    "glide_eff_state_penalty",
    "glide_ligand_efficiency",
    "glide_ligand_efficiency_sa",
    "glide_ligand_efficiency_ln",
    "dock_pose_count",
    "dock_score_median",
    "dock_score_std",
    "dock_score_top2_gap",
]


@dataclass(frozen=True)
class FeatureConfigV2:
    radius: int = 2
    n_bits: int = 2048
    use_chirality: bool = True
    version: str = "0.2"


class EnhancedFeaturePipeline:
    """Build explicit molecular, docking/QuickProp and ADMET feature blocks."""

    def __init__(self, project_root: str | Path, config: FeatureConfigV2 | None = None):
        self.project_root = Path(project_root).resolve()
        self.data_dir = self.project_root / "data"
        self.results_dir = self.project_root / "results"
        self.config = config or FeatureConfigV2()

    @staticmethod
    def _read_csv(path: Path, required: set[str]) -> pd.DataFrame:
        if not path.exists():
            raise FileNotFoundError(f"Required Phase 2 asset is missing: {path}")
        table = pd.read_csv(path, dtype=str, keep_default_na=False)
        missing = required.difference(table.columns)
        if missing:
            raise ValueError(f"{path.name} missing fields: {sorted(missing)}")
        return table

    def load_tables(self) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        molecules = self._read_csv(
            self.data_dir / "molecules.csv",
            {"canonical_id", "historical_alias", "structure_file", "smiles", "source", "confidence"},
        )
        screening = self._read_csv(
            self.data_dir / "screening_records.csv",
            {"canonical_id", "stage", "score", "source_file"},
        )
        docking = self._read_csv(
            self.data_dir / "docking_features_v0_2.csv",
            {"canonical_id", "compound_code", "glide_docking_score", "source_file"},
        )
        admet = self._read_csv(
            self.data_dir / "admet_features_v0_2.csv",
            {"canonical_id", "smiles", "admet_endpoint_sum", "source_file"},
        )
        mapping = self._read_csv(
            self.data_dir / "compound_mapping_v1.csv",
            {"canonical_id", "original_name", "source", "confidence"},
        )
        if molecules["canonical_id"].eq("").any() or molecules["canonical_id"].duplicated().any():
            raise ValueError("molecules.csv must contain unique, non-blank canonical_id values")
        categorical = {"canonical_id", "stage", "source_file", "compound_code", "title", "variant", "smiles"}
        for frame in (screening, docking, admet):
            for column in frame.columns:
                if column in categorical:
                    continue
                frame[column] = pd.to_numeric(frame[column], errors="coerce")
        screening["score"] = pd.to_numeric(screening["score"], errors="coerce")
        docking["glide_docking_score"] = pd.to_numeric(docking["glide_docking_score"], errors="coerce")

        # Apply only confirmed, explicit legacy-HTVS-ID bridges. Reassignment
        # keeps each source pose once; provenance remains in the mapping table.
        verified_bridges = mapping.loc[
            mapping["confidence"].eq("confirmed")
            & mapping["original_name"].str.startswith("ATP-HTVS-")
            & mapping["canonical_id"].str.startswith("ATP-SMI-"),
            ["original_name", "canonical_id"],
        ]
        if verified_bridges["original_name"].duplicated().any():
            raise ValueError("compound_mapping_v1.csv has conflicting confirmed HTVS bridges")
        bridge_map = dict(verified_bridges.itertuples(index=False, name=None))
        docking["canonical_id"] = docking["canonical_id"].map(lambda value: bridge_map.get(value, value))
        return molecules, screening, docking, admet

    @staticmethod
    def _aggregate_stage_scores(screening: pd.DataFrame) -> pd.DataFrame:
        usable = screening.loc[screening["canonical_id"].ne("") & screening["score"].notna()].copy()
        if usable.empty:
            return pd.DataFrame(columns=["canonical_id"])
        parts: list[pd.DataFrame] = []
        for stage, rows in usable.groupby("stage", sort=True):
            reducer = "min" if stage in {"HTVS", "Docking"} else "mean"
            part = rows.groupby("canonical_id", as_index=False)["score"].agg(reducer)
            parts.append(part.rename(columns={"score": f"score_{stage}"}))
        output = parts[0]
        for part in parts[1:]:
            output = output.merge(part, on="canonical_id", how="outer", validate="one_to_one")
        return output

    @staticmethod
    def _aggregate_best_docking(docking: pd.DataFrame) -> pd.DataFrame:
        usable = docking.loc[docking["canonical_id"].ne("") & docking["glide_docking_score"].notna()].copy()
        if usable.empty:
            return pd.DataFrame(columns=["canonical_id"])
        score_summary = usable.groupby("canonical_id")["glide_docking_score"].agg(
            dock_pose_count="count",
            dock_score_median="median",
            dock_score_std="std",
        ).reset_index()
        sorted_scores = usable.sort_values(["canonical_id", "glide_docking_score"])
        top_two = sorted_scores.groupby("canonical_id")["glide_docking_score"].apply(
            lambda values: float(values.iloc[1] - values.iloc[0]) if len(values) > 1 else np.nan
        ).rename("dock_score_top2_gap").reset_index()
        score_summary = score_summary.merge(top_two, on="canonical_id", how="left", validate="one_to_one")
        best_indices = usable.groupby("canonical_id")["glide_docking_score"].idxmin()
        best = usable.loc[best_indices].copy()
        numeric_features = [
            column
            for column in best.columns
            if column in DOCKING_COLUMNS or column.startswith("quickprop_")
        ]
        for column in numeric_features:
            best[column] = pd.to_numeric(best[column], errors="coerce")
        keep = ["canonical_id", *numeric_features]
        return (
            best[keep]
            .merge(score_summary, on="canonical_id", how="left", validate="one_to_one")
            .sort_values("canonical_id")
            .reset_index(drop=True)
        )

    def _smiles_features(self, smiles: str) -> tuple[dict[str, float | bool], dict[str, float]]:
        prefix = f"morgan{self.config.n_bits}_"
        output: dict[str, float | bool] = {"smiles_valid": False}
        output.update({name: np.nan for name in DESCRIPTOR_COLUMNS_V2})
        output.update({f"{prefix}{index:04d}": np.nan for index in range(self.config.n_bits)})
        diagnostic = {"on_bits": np.nan, "density": np.nan, "distinct_features": np.nan, "collision_rate": np.nan}
        if not smiles:
            return output, diagnostic
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return output, diagnostic

        output["smiles_valid"] = True
        output.update(
            {
                "desc_mol_wt": Descriptors.MolWt(mol),
                "desc_logp": Crippen.MolLogP(mol),
                "desc_tpsa": rdMolDescriptors.CalcTPSA(mol),
                "desc_hbd": Lipinski.NumHDonors(mol),
                "desc_hba": Lipinski.NumHAcceptors(mol),
                "desc_rotatable_bonds": Lipinski.NumRotatableBonds(mol),
                "desc_aromatic_ring_count": rdMolDescriptors.CalcNumAromaticRings(mol),
                "desc_fraction_csp3": rdMolDescriptors.CalcFractionCSP3(mol),
                "desc_heavy_atom_count": Lipinski.HeavyAtomCount(mol),
                "desc_ring_count": Lipinski.RingCount(mol),
                "desc_formal_charge": Chem.GetFormalCharge(mol),
            }
        )
        generator = rdFingerprintGenerator.GetMorganGenerator(
            radius=self.config.radius,
            fpSize=self.config.n_bits,
            includeChirality=self.config.use_chirality,
        )
        fingerprint = generator.GetFingerprint(mol)
        array = np.zeros((self.config.n_bits,), dtype=np.int8)
        DataStructs.ConvertToNumpyArray(fingerprint, array)
        output.update({f"{prefix}{index:04d}": int(value) for index, value in enumerate(array)})

        sparse = generator.GetSparseCountFingerprint(mol)
        distinct = len(sparse.GetNonzeroElements())
        on_bits = int(fingerprint.GetNumOnBits())
        diagnostic = {
            "on_bits": on_bits,
            "density": on_bits / self.config.n_bits,
            "distinct_features": distinct,
            "collision_rate": max(distinct - on_bits, 0) / distinct if distinct else 0.0,
        }
        return output, diagnostic

    def build(self) -> tuple[pd.DataFrame, dict[str, object]]:
        molecules, screening, docking, admet = self.load_tables()
        stage_scores = self._aggregate_stage_scores(screening)
        best_docking = self._aggregate_best_docking(docking)

        feature_rows = []
        diagnostics = []
        for canonical_id, smiles in molecules[["canonical_id", "smiles"]].itertuples(index=False):
            features, diagnostic = self._smiles_features(smiles)
            feature_rows.append(features)
            diagnostics.append({"canonical_id": canonical_id, **diagnostic})
        matrix = pd.concat([molecules.copy(), pd.DataFrame(feature_rows, index=molecules.index)], axis=1)
        matrix = matrix.merge(stage_scores, on="canonical_id", how="left", validate="one_to_one")
        matrix = matrix.merge(best_docking, on="canonical_id", how="left", validate="one_to_one")

        admet_features = admet.drop(columns=["smiles", "source_file"], errors="ignore").copy()
        if admet_features["canonical_id"].duplicated().any():
            raise ValueError("admet_features_v0_2.csv contains duplicate canonical_id")
        for column in admet_features.columns:
            if column != "canonical_id":
                admet_features[column] = pd.to_numeric(admet_features[column], errors="coerce")
        matrix = matrix.merge(admet_features, on="canonical_id", how="left", validate="one_to_one")

        diagnostics_frame = pd.DataFrame(diagnostics)
        valid_diagnostics = diagnostics_frame.dropna(subset=["on_bits"])
        fingerprint_columns = self.feature_sets(matrix)["morgan"]
        docking_columns = self.feature_sets(matrix)["docking"]
        quickprop_columns = self.feature_sets(matrix)["quickprop"]
        admet_columns = self.feature_sets(matrix)["admet"]
        metadata = {
            "feature_config": asdict(self.config),
            "purpose": "computational candidate-ranking feature construction; not biological-activity prediction",
            "rows": int(len(matrix)),
            "valid_smiles": int(matrix["smiles_valid"].sum()),
            "invalid_or_missing_smiles": int((~matrix["smiles_valid"]).sum()),
            "descriptor_columns": DESCRIPTOR_COLUMNS_V2,
            "fingerprint_columns": len(fingerprint_columns),
            "docking_columns": docking_columns,
            "quickprop_columns": quickprop_columns,
            "admet_columns": admet_columns,
            "coverage": {
                "docking_compounds": int(matrix.get("glide_docking_score", pd.Series(dtype=float)).notna().sum()),
                "admet_compounds": int(matrix.get("admet_endpoint_sum", pd.Series(dtype=float)).notna().sum()),
                "mmgbsa_labeled_smiles": int((matrix["smiles_valid"] & matrix.get("score_MMGBSA", pd.Series(index=matrix.index, dtype=float)).notna()).sum()),
                "mmgbsa_labeled_smiles_with_docking": int((
                    matrix["smiles_valid"]
                    & matrix.get("score_MMGBSA", pd.Series(index=matrix.index, dtype=float)).notna()
                    & matrix.get("glide_docking_score", pd.Series(index=matrix.index, dtype=float)).notna()
                ).sum()),
            },
            "fingerprint_diagnostics": {
                "molecules": int(len(valid_diagnostics)),
                "mean_on_bits": float(valid_diagnostics["on_bits"].mean()) if len(valid_diagnostics) else None,
                "mean_density": float(valid_diagnostics["density"].mean()) if len(valid_diagnostics) else None,
                "mean_distinct_features": float(valid_diagnostics["distinct_features"].mean()) if len(valid_diagnostics) else None,
                "mean_folding_collision_rate": float(valid_diagnostics["collision_rate"].mean()) if len(valid_diagnostics) else None,
            },
            "feature_sets": self.feature_sets(matrix),
        }
        return matrix, metadata

    @staticmethod
    def feature_sets(matrix: pd.DataFrame) -> dict[str, list[str]]:
        """Return explicit, pre-registered feature blocks; target columns are excluded."""
        return {
            "morgan": sorted(column for column in matrix.columns if column.startswith(("morgan1024_", "morgan2048_"))),
            "descriptors": [column for column in DESCRIPTOR_COLUMNS_V2 if column in matrix.columns],
            "docking": [column for column in DOCKING_COLUMNS if column in matrix.columns],
            "quickprop": sorted(column for column in matrix.columns if column.startswith("quickprop_")),
            "admet": sorted(column for column in matrix.columns if column.startswith("admet_")),
        }

    @staticmethod
    def coverage_table(matrix: pd.DataFrame, groups: dict[str, Iterable[str]]) -> pd.DataFrame:
        rows = []
        total = len(matrix)
        for group, columns in groups.items():
            for column in columns:
                count = int(pd.to_numeric(matrix[column], errors="coerce").notna().sum())
                rows.append(
                    {
                        "feature": column,
                        "feature_group": group,
                        "non_missing": count,
                        "coverage": count / total if total else 0.0,
                    }
                )
        return pd.DataFrame(rows)

    def save(self, matrix: pd.DataFrame, metadata: dict[str, object]) -> None:
        self.results_dir.mkdir(parents=True, exist_ok=True)
        bits = self.config.n_bits
        matrix.to_csv(self.results_dir / f"feature_matrix_v2_morgan{bits}.csv", index=False)
        self.coverage_table(matrix, self.feature_sets(matrix)).to_csv(
            self.results_dir / f"feature_coverage_v2_morgan{bits}.csv", index=False
        )
        (self.results_dir / f"feature_metadata_v2_morgan{bits}.json").write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build additive ATP-Navigator Phase 2 feature matrices")
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--radius", type=int, default=2)
    parser.add_argument("--n-bits", choices=["1024", "2048", "both"], default="both")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    bit_sizes = [1024, 2048] if args.n_bits == "both" else [int(args.n_bits)]
    comparison = []
    for bits in bit_sizes:
        pipeline = EnhancedFeaturePipeline(
            args.project_root,
            FeatureConfigV2(radius=args.radius, n_bits=bits),
        )
        matrix, metadata = pipeline.build()
        pipeline.save(matrix, metadata)
        comparison.append({"n_bits": bits, **metadata["fingerprint_diagnostics"]})
        print(json.dumps({
            "feature_config": metadata["feature_config"],
            "rows": metadata["rows"],
            "valid_smiles": metadata["valid_smiles"],
            "coverage": metadata["coverage"],
            "fingerprint_diagnostics": metadata["fingerprint_diagnostics"],
        }, ensure_ascii=False, indent=2))
    if len(comparison) > 1:
        output = Path(args.project_root).resolve() / "results" / "morgan_1024_vs_2048.json"
        output.write_text(json.dumps(comparison, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
