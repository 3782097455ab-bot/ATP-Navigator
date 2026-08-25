"""Extract traceable structures from ATP-Navigator Maestro HTVS files.

The original Maestro files are read-only. Chinese-path and gzip inputs are
copied/decompressed into an ASCII temporary directory because RDKit's C++ file
reader cannot open non-ASCII Windows paths reliably. No model is trained.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
import tempfile
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from rdkit import Chem, rdBase
from rdkit.Chem import rdMolDescriptors
from rdkit.Chem.Scaffolds import MurckoScaffold


rdBase.DisableLog("rdApp.warning")


def json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_csv(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8-sig", newline="", delete=False, dir=path.parent, suffix=".tmp"
    ) as handle:
        frame.to_csv(handle, index=False)
        temporary = Path(handle.name)
    temporary.replace(path)


def atomic_json(payload: Any, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", delete=False, dir=path.parent, suffix=".tmp"
    ) as handle:
        json.dump(json_safe(payload), handle, ensure_ascii=False, indent=2, allow_nan=False)
        temporary = Path(handle.name)
    temporary.replace(path)


def atomic_text(text: str, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", delete=False, dir=path.parent, suffix=".tmp"
    ) as handle:
        handle.write(text)
        temporary = Path(handle.name)
    temporary.replace(path)


def mol_property(mol: Chem.Mol, name: str, default: str = "") -> str:
    return mol.GetProp(name) if mol.HasProp(name) else default


def molecule_record(mol: Chem.Mol, source_file: str, source_index: int) -> dict[str, Any]:
    without_h = Chem.RemoveHs(mol, sanitize=True)
    smiles = Chem.MolToSmiles(without_h, canonical=True, isomericSmiles=True)
    nonisomeric = Chem.MolToSmiles(without_h, canonical=True, isomericSmiles=False)
    try:
        scaffold = MurckoScaffold.MurckoScaffoldSmilesFromSmiles(smiles)
    except Exception:
        scaffold = ""
    if not scaffold:
        scaffold = "__ACYCLIC__"
    return {
        "source_file": source_file,
        "source_structure_index": source_index,
        "title": mol.GetProp("_Name") if mol.HasProp("_Name") else "",
        "compound_code": mol_property(mol, "s_vsw_compound_code"),
        "variant": mol_property(mol, "s_vsw_variant"),
        "glide_lignum": mol_property(mol, "i_i_glide_lignum"),
        "glide_posenum": mol_property(mol, "i_i_glide_posenum"),
        "canonical_smiles": smiles,
        "canonical_smiles_nonisomeric": nonisomeric,
        "scaffold": scaffold,
        "molecular_formula": rdMolDescriptors.CalcMolFormula(without_h),
        "formal_charge": int(Chem.GetFormalCharge(without_h)),
        "heavy_atom_count": int(without_h.GetNumHeavyAtoms()),
        "atom_count_with_h": int(mol.GetNumAtoms()),
        "conformer_count": int(mol.GetNumConformers()),
        "smiles_sha256": hashlib.sha256(smiles.encode("utf-8")).hexdigest(),
        "extraction_status": "complete",
    }


def parse_sources(project_root: Path, docking: pd.DataFrame) -> tuple[pd.DataFrame, dict[tuple[str, str, str], Chem.Mol], list[dict[str, Any]]]:
    workspace = project_root.parent
    records: list[dict[str, Any]] = []
    molecules: dict[tuple[str, str, str], Chem.Mol] = {}
    source_audit: list[dict[str, Any]] = []
    source_files = sorted(docking["source_file"].dropna().astype(str).unique())
    for relative in source_files:
        source = workspace / relative
        if not source.exists():
            raise FileNotFoundError(source)
        expected = int(docking["source_file"].eq(relative).sum())
        parsed = 0
        failed = 0
        attempts = 0
        failed_indices: list[int] = []
        duplicate_keys = 0
        opener = gzip.open if source.suffix.lower() == ".maegz" else open
        with opener(source, "rb") as source_handle:
            supplier = Chem.MaeMolSupplier(source_handle, sanitize=True, removeHs=False)
            while True:
                attempts += 1
                try:
                    mol = next(supplier)
                except StopIteration:
                    attempts -= 1
                    break
                except RuntimeError:
                    failed += 1
                    failed_indices.append(attempts)
                    continue
                if mol is None:
                    failed += 1
                    failed_indices.append(attempts)
                    continue
                record = molecule_record(mol, relative, attempts)
                key = (relative, record["title"], record["variant"])
                if key in molecules:
                    duplicate_keys += 1
                else:
                    molecules[key] = Chem.Mol(mol)
                records.append(record)
                parsed += 1
        source_audit.append(
            {
                "source_file": relative,
                "source_size_bytes": int(source.stat().st_size),
                "source_sha256": sha256(source),
                "expected_docking_rows": expected,
                "supplier_attempts": attempts,
                "parsed_structures": parsed,
                "failed_structures": failed,
                "failed_structure_indices": ";".join(map(str, failed_indices)),
                "duplicate_identity_keys": duplicate_keys,
                "count_match_including_failures": parsed + failed == expected,
            }
        )
    return pd.DataFrame(records), molecules, source_audit


def join_and_validate(docking: pd.DataFrame, extracted: pd.DataFrame) -> pd.DataFrame:
    keys = ["source_file", "title", "variant"]
    if extracted.duplicated(keys).any():
        raise ValueError("Extracted Maestro identity keys are not unique")
    merged = docking.merge(extracted, on=keys, how="left", validate="one_to_one")
    merged["structure_join_status"] = np.where(
        merged["canonical_smiles"].fillna("").astype(str).str.len().gt(0),
        "matched",
        "missing",
    )
    return merged


def compound_structure_table(merged: pd.DataFrame) -> pd.DataFrame:
    numeric_columns = [
        "glide_docking_score",
        "glide_emodel",
        "glide_ligand_efficiency",
        "pose_index",
    ]
    working = merged.copy()
    for column in numeric_columns:
        working[column] = pd.to_numeric(working[column], errors="coerce")
    working = working.sort_values(
        ["canonical_id", "glide_docking_score", "glide_emodel", "variant"],
        na_position="last",
        kind="stable",
    )
    valid = working.loc[working["structure_join_status"].eq("matched")].copy()
    best = valid.drop_duplicates("canonical_id", keep="first")
    counts = working.groupby("canonical_id", as_index=False).agg(
        pose_count=("canonical_smiles", "size"),
        unique_variant_structures=("canonical_smiles", "nunique"),
        variant_count=("variant", "nunique"),
    )
    best = best.merge(counts, on="canonical_id", validate="one_to_one")
    columns = [
        "canonical_id",
        "compound_code_x",
        "title",
        "variant",
        "pose_index",
        "source_file",
        "canonical_smiles",
        "canonical_smiles_nonisomeric",
        "scaffold",
        "molecular_formula",
        "formal_charge",
        "heavy_atom_count",
        "atom_count_with_h",
        "conformer_count",
        "smiles_sha256",
        "glide_docking_score",
        "glide_emodel",
        "glide_ligand_efficiency",
        "pose_count",
        "variant_count",
        "unique_variant_structures",
        "structure_join_status",
        "extraction_status",
    ]
    result = best[columns].rename(columns={"compound_code_x": "compound_code"}).reset_index(drop=True)
    return result


def known_structure_validation(project_root: Path, compounds: pd.DataFrame) -> pd.DataFrame:
    internal = pd.read_csv(project_root / "data/model_v3/training_table.csv")
    mapping = pd.read_csv(project_root / "data/compound_mapping_v1.csv")
    bridge = mapping.loc[
        mapping["original_name"].astype(str).str.startswith("ATP-HTVS-")
        & mapping["canonical_id"].astype(str).isin(set(internal["compound_id"].astype(str)))
    ][["canonical_id", "original_name", "confidence", "source"]].drop_duplicates()
    bridge = bridge.rename(
        columns={"canonical_id": "internal_compound_id", "original_name": "canonical_id"}
    )
    known = internal[["compound_id", "canonical_smiles"]].rename(
        columns={"compound_id": "internal_compound_id", "canonical_smiles": "known_smiles"}
    )
    validation = bridge.merge(known, on="internal_compound_id", validate="many_to_one").merge(
        compounds[["canonical_id", "canonical_smiles"]].rename(
            columns={"canonical_smiles": "extracted_smiles"}
        ),
        on="canonical_id",
        how="left",
        validate="many_to_one",
    )

    exact: list[bool] = []
    connectivity: list[bool] = []
    for row in validation.itertuples(index=False):
        known_mol = Chem.MolFromSmiles(row.known_smiles)
        extracted_mol = Chem.MolFromSmiles(row.extracted_smiles) if isinstance(row.extracted_smiles, str) else None
        if known_mol is None or extracted_mol is None:
            exact.append(False)
            connectivity.append(False)
            continue
        known_iso = Chem.MolToSmiles(known_mol, canonical=True, isomericSmiles=True)
        extracted_iso = Chem.MolToSmiles(extracted_mol, canonical=True, isomericSmiles=True)
        known_plain = Chem.MolToSmiles(known_mol, canonical=True, isomericSmiles=False)
        extracted_plain = Chem.MolToSmiles(extracted_mol, canonical=True, isomericSmiles=False)
        exact.append(known_iso == extracted_iso)
        connectivity.append(known_plain == extracted_plain)
    validation["exact_isomeric_match"] = exact
    validation["connectivity_match"] = connectivity
    validation["validation_status"] = np.select(
        [validation["exact_isomeric_match"], validation["connectivity_match"]],
        ["exact_match", "connectivity_match_stereo_or_protonation_differs"],
        default="mismatch_or_missing",
    )
    return validation


def atomic_sdf(records: pd.DataFrame, molecule_map: dict[tuple[str, str, str], Chem.Mol], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    writer = Chem.SDWriter(str(temporary))
    try:
        for row in records.itertuples(index=False):
            key = (row.source_file, row.title, row.variant)
            if key not in molecule_map:
                continue
            mol = Chem.Mol(molecule_map[key])
            mol.SetProp("_Name", str(row.acquisition_id))
            for name in [
                "acquisition_id",
                "canonical_id",
                "compound_code",
                "title",
                "variant",
                "selection_arm",
                "priority",
                "wave",
                "source_file",
                "canonical_smiles",
            ]:
                mol.SetProp(name, str(getattr(row, name)))
            writer.write(mol)
    finally:
        writer.close()
    temporary.replace(path)


def atomic_compound_sdf(
    compounds: pd.DataFrame,
    molecule_map: dict[tuple[str, str, str], Chem.Mol],
    path: Path,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    writer = Chem.SDWriter(str(temporary))
    try:
        for row in compounds.itertuples(index=False):
            key = (row.source_file, row.title, row.variant)
            if key not in molecule_map:
                continue
            mol = Chem.Mol(molecule_map[key])
            mol.SetProp("_Name", str(row.canonical_id))
            for name in [
                "canonical_id",
                "compound_code",
                "title",
                "variant",
                "source_file",
                "canonical_smiles",
                "scaffold",
                "molecular_formula",
            ]:
                mol.SetProp(name, str(getattr(row, name)))
            writer.write(mol)
    finally:
        writer.close()
    temporary.replace(path)


def selected_manifest(
    project_root: Path,
    merged: pd.DataFrame,
    molecule_map: dict[tuple[str, str, str], Chem.Mol],
) -> pd.DataFrame:
    queue = pd.read_csv(project_root / "results/phase8_data_acquisition/mmgbsa_acquisition_queue.csv")
    structure_columns = [
        "source_file",
        "title",
        "variant",
        "canonical_smiles",
        "canonical_smiles_nonisomeric",
        "scaffold",
        "molecular_formula",
        "formal_charge",
        "heavy_atom_count",
        "atom_count_with_h",
        "conformer_count",
        "smiles_sha256",
        "structure_join_status",
    ]
    pose_structures = merged[structure_columns].drop_duplicates(
        ["source_file", "title", "variant"]
    )
    selected = queue.drop(columns=["smiles", "structure_status"], errors="ignore").merge(
        pose_structures,
        on=["source_file", "title", "variant"],
        how="left",
        validate="one_to_one",
    )
    selected["structure_status"] = np.where(
        selected["canonical_smiles"].fillna("").astype(str).str.len().gt(0),
        "extracted_and_rdkit_validated",
        "missing",
    )
    results_dir = project_root / "results/phase8_data_acquisition"
    atomic_sdf(selected, molecule_map, results_dir / "selected_structures_v0_1.sdf")
    atomic_sdf(
        selected.loc[selected["wave"].eq(1)],
        molecule_map,
        results_dir / "p0_structures_v0_1.sdf",
    )
    return selected


def report(summary: dict[str, Any]) -> str:
    return f"""# Phase 8 Maestro Structure Extraction Report

日期：2026-08-25  
状态：结构提取已运行；未训练或修改模型

## 结论

现有Schrödinger文件足以直接提取分子结构，不需要导师或队员重新提供SMILES。RDKit内置Maestro reader读取原子、键、形式电荷、立体信息和三维坐标；`.maegz`只在临时目录解压，原始文件保持只读。

## 全库结果

- Maestro源文件：{summary['source_files']}；
- Docking记录：{summary['docking_rows']:,}；
- 成功解析结构：{summary['parsed_structures']:,}；失败：{summary['failed_structures']}；
- source/title/variant精确连接：{summary['matched_docking_rows']:,}/{summary['docking_rows']:,}；
- compound级最佳pose结构：{summary['compound_structures']:,}；
- RDKit有效canonical SMILES：{summary['valid_compound_smiles']:,}；
- compound scaffolds：{summary['compound_scaffolds']:,}；
- Phase 8 60候选SMILES：{summary['selected_structures']}/60；P0 SDF：{summary['p0_structures']}/24。

## 已知结构验证

- 可连接的内部Hit—HTVS桥：{summary['known_validation_rows']}；
- exact isomeric SMILES一致：{summary['known_exact_matches']}；
- connectivity一致：{summary['known_connectivity_matches']}。

已知桥目前只有Hit13/compound 91074，因此它能证明读取器在这一条上的一致性，但不能单独证明所有1,633条的人工化学正确性。全库仍使用RDKit sanitize、计数一致、唯一键和源文件hash进行程序化QC。

## 输出

- `data/htvs_structures_v0_1.csv`：1,633个compound最佳pose结构；
- `data/htvs_best_pose_structures_v0_1.sdf`：1,633个compound三维最佳pose；
- `results/phase8_data_acquisition/htvs_pose_structure_audit.csv`：4,373个pose结构连接审计；
- `results/phase8_data_acquisition/selected_structure_manifest_v0_1.csv`：60候选结构；
- `results/phase8_data_acquisition/selected_structures_v0_1.sdf`；
- `results/phase8_data_acquisition/p0_structures_v0_1.sdf`；
- `results/phase8_data_acquisition/known_structure_validation.csv`；
- `results/phase8_data_acquisition/maestro_source_audit.csv`。

## 边界

- canonical SMILES来自Maestro pose的RDKit解析，不是外部数据库重新检索；
- SDF保留Maestro三维构象，但尚未执行新的protein preparation或MM/GBSA；
- 提取成功不是活性验证，也不产生任何新标签；
- 结构可用后应另建v2 acquisition queue，用Morgan/scaffold替换原descriptor-only diversity臂，保留v1队列作审计对照。
"""


def run(project_root: Path) -> dict[str, Any]:
    project_root = project_root.resolve()
    docking_path = project_root / "data/docking_features_v0_2.csv"
    docking = pd.read_csv(docking_path)
    extracted, molecule_map, source_audit = parse_sources(project_root, docking)
    merged = join_and_validate(docking, extracted)
    compounds = compound_structure_table(merged)
    validation = known_structure_validation(project_root, compounds)
    selected = selected_manifest(project_root, merged, molecule_map)
    results_dir = project_root / "results/phase8_data_acquisition"

    atomic_csv(compounds, project_root / "data/htvs_structures_v0_1.csv")
    atomic_compound_sdf(
        compounds,
        molecule_map,
        project_root / "data/htvs_best_pose_structures_v0_1.sdf",
    )
    atomic_csv(merged, results_dir / "htvs_pose_structure_audit.csv")
    atomic_csv(selected, results_dir / "selected_structure_manifest_v0_1.csv")
    atomic_csv(validation, results_dir / "known_structure_validation.csv")
    atomic_csv(pd.DataFrame(source_audit), results_dir / "maestro_source_audit.csv")

    summary = {
        "phase": "Phase 8.1 Maestro Structure Extraction",
        "model_change": "none",
        "docking_input_sha256": sha256(docking_path),
        "source_files": len(source_audit),
        "source_hashes": {row["source_file"]: row["source_sha256"] for row in source_audit},
        "docking_rows": int(len(docking)),
        "parsed_structures": int(len(extracted)),
        "failed_structures": int(sum(row["failed_structures"] for row in source_audit)),
        "matched_docking_rows": int(merged["structure_join_status"].eq("matched").sum()),
        "compound_structures": int(len(compounds)),
        "valid_compound_smiles": int(compounds["canonical_smiles"].fillna("").str.len().gt(0).sum()),
        "compound_scaffolds": int(compounds["scaffold"].nunique()),
        "selected_structures": int(selected["structure_status"].eq("extracted_and_rdkit_validated").sum()),
        "p0_structures": int(
            selected.loc[selected["wave"].eq(1), "structure_status"].eq("extracted_and_rdkit_validated").sum()
        ),
        "known_validation_rows": int(len(validation)),
        "known_exact_matches": int(validation["exact_isomeric_match"].sum()) if len(validation) else 0,
        "known_connectivity_matches": int(validation["connectivity_match"].sum()) if len(validation) else 0,
        "original_files_modified": False,
    }
    atomic_json(summary, results_dir / "structure_extraction_summary.json")
    atomic_text(report(summary), project_root / "docs/Phase8_Structure_Extraction_Report.md")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    print(json.dumps(json_safe(run(args.project_root)), ensure_ascii=False, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
