"""ATP-Navigator AI ranking pipeline v1.0 (Phase 3).

The pipeline trains a small-sample LightGBM ranking surrogate on the 17 VSW
candidates for which molecule identity, VSW docking/QuickProp evidence, and the
static MM/GBSA label are all traceable. It preserves all previous models and
results by writing versioned Phase 3 artifacts only.

The target is computational MM/GBSA candidate ordering, not biological activity.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import os
import re
import tempfile
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

if os.name == "nt":
    os.environ.setdefault("WINDIR", os.environ.get("SystemRoot", r"C:\Windows"))
os.environ.setdefault("MPLCONFIGDIR", str(Path(tempfile.gettempdir()) / "atp_navigator_phase3_mpl"))
os.environ.setdefault("NUMBA_CACHE_DIR", str(Path(tempfile.gettempdir()) / "atp_navigator_numba"))

import joblib
import lightgbm as lgb
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import shap
from rdkit import Chem, DataStructs, rdBase
from rdkit.Chem import Crippen, Descriptors, Lipinski, rdFingerprintGenerator, rdMolDescriptors
from rdkit.Chem.Scaffolds import MurckoScaffold
from scipy.stats import rankdata
from sklearn.model_selection import LeaveOneGroupOut

from evaluation import evaluate_predictions


DATASET_VERSION = "dataset_v0.2"
MODEL_VERSION = "lightgbm_enhanced_v1.0"
RANDOM_SEED = 42
TOP_K = 5

DESCRIPTORS: dict[str, Any] = {
    "desc_mol_wt": Descriptors.MolWt,
    "desc_logp": Crippen.MolLogP,
    "desc_tpsa": rdMolDescriptors.CalcTPSA,
    "desc_hbd": Lipinski.NumHDonors,
    "desc_hba": Lipinski.NumHAcceptors,
    "desc_rotatable_bonds": Lipinski.NumRotatableBonds,
    "desc_aromatic_ring_count": rdMolDescriptors.CalcNumAromaticRings,
    "desc_fraction_csp3": rdMolDescriptors.CalcFractionCSP3,
    "desc_heavy_atom_count": Lipinski.HeavyAtomCount,
    "desc_ring_count": Lipinski.RingCount,
    "desc_formal_charge": Chem.GetFormalCharge,
}

DOCKING_PROPERTY_MAP = {
    "r_i_docking_score": "glide_docking_score",
    "r_i_glide_gscore": "glide_gscore",
    "r_i_glide_emodel": "glide_emodel",
    "r_i_glide_energy": "glide_energy",
    "r_i_glide_evdw": "glide_evdw",
    "r_i_glide_ecoul": "glide_ecoul",
    "r_i_glide_einternal": "glide_einternal",
    "r_i_glide_eff_state_penalty": "glide_eff_state_penalty",
    "r_i_glide_ligand_efficiency": "glide_ligand_efficiency",
    "r_i_glide_ligand_efficiency_sa": "glide_ligand_efficiency_sa",
    "r_i_glide_ligand_efficiency_ln": "glide_ligand_efficiency_ln",
}


@dataclass(frozen=True)
class ModelConfig:
    objective: str = "regression"
    n_estimators: int = 160
    learning_rate: float = 0.03
    num_leaves: int = 7
    max_depth: int = 3
    min_child_samples: int = 2
    subsample: float = 0.9
    colsample_bytree: float = 0.45
    reg_alpha: float = 0.1
    reg_lambda: float = 1.0
    random_state: int = RANDOM_SEED
    n_jobs: int = 1


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_id_from_source_smiles(smiles: str) -> str:
    digest = hashlib.sha256(f"source-smiles|{smiles}".encode("utf-8")).hexdigest()
    return f"ATP-SMI-{digest[:12].upper()}"


def strip_maestro_value(value: str) -> str:
    trimmed = value.strip()
    if trimmed == "<>":
        return ""
    if len(trimmed) >= 2 and trimmed[0] == '"' and trimmed[-1] == '"':
        return trimmed[1:-1]
    return trimmed


def extract_fmct_blocks(text: str) -> list[str]:
    blocks: list[str] = []
    cursor = 0
    while True:
        marker = text.find("f_m_ct {", cursor)
        if marker < 0:
            break
        brace = text.find("{", marker)
        depth = 0
        in_quote = False
        escaped = False
        end = -1
        for index in range(brace, len(text)):
            char = text[index]
            if in_quote:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    in_quote = False
                continue
            if char == '"':
                in_quote = True
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    end = index + 1
                    break
        if end < 0:
            raise ValueError("Unterminated f_m_ct block in VSW.maegz")
        blocks.append(text[marker:end])
        cursor = end
    return blocks


def parse_maestro_metadata(text: str) -> list[dict[str, str]]:
    records: list[dict[str, str]] = []
    for block in extract_fmct_blocks(text):
        atom_match = re.search(r"\r?\n\s*m_atom\[", block)
        metadata = block[: atom_match.start()] if atom_match else block
        delimiter = metadata.find(":::")
        if delimiter < 0:
            continue
        properties = [
            line.strip()
            for line in metadata[metadata.find("{") + 1 : delimiter].splitlines()
            if line.strip()
        ]
        values = [
            strip_maestro_value(line)
            for line in metadata[delimiter + 3 :].splitlines()
            if line.strip()
        ]
        records.append({prop: values[index] if index < len(values) else "" for index, prop in enumerate(properties)})
    return records


def read_maestro(path: Path) -> str:
    raw = path.read_bytes()
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    return raw.decode("utf-8", errors="replace")


def decode_maestro_smiles(value: str) -> str:
    return re.sub(r"/([A-Za-z0-9@+\-]+)/", r"[\1]", str(value))


def canonical_smiles(smiles: str) -> str:
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        raise ValueError(f"Invalid SMILES: {smiles}")
    return Chem.MolToSmiles(mol, canonical=True, isomericSmiles=True)


def scaffold_key(smiles: str) -> str:
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        raise ValueError(f"Invalid SMILES: {smiles}")
    scaffold = MurckoScaffold.MurckoScaffoldSmiles(mol=mol, includeChirality=True)
    return scaffold or Chem.MolToSmiles(mol, canonical=True, isomericSmiles=True)


def slug(value: str) -> str:
    output = re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")
    return output or "unnamed"


def quickprop_feature_name(property_name: str) -> str:
    stripped = re.sub(r"^[ris]_qp_", "", property_name)
    return f"quickprop_{slug(stripped)}"


def numeric(value: Any) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return np.nan
    return result if np.isfinite(result) else np.nan


def load_verified_records(project_root: Path) -> tuple[pd.DataFrame, list[dict[str, str]], dict[str, Any]]:
    workspace_root = project_root.parent
    source_dir = workspace_root / "作图" / "作图" / "2-基于衍生数据库的虚拟筛选" / "数据"
    labels_path = source_dir / "VSW.csv"
    feature_path = source_dir / "VSW.maegz"
    if not labels_path.exists() or not feature_path.exists():
        raise FileNotFoundError("VSW.csv or VSW.maegz is missing")

    labels = pd.read_csv(labels_path)
    labels.columns = [str(column).strip() for column in labels.columns]
    smiles_column = next(column for column in labels.columns if "SMILES" in column.upper())
    label_column = next(column for column in labels.columns if "MMGBSA" in column.upper())
    labels = labels.loc[labels[smiles_column].notna()].copy()
    labels[smiles_column] = labels[smiles_column].astype(str).str.strip()
    labels[label_column] = pd.to_numeric(labels[label_column], errors="coerce")
    labels = labels.loc[labels[label_column].notna()].reset_index(drop=True)
    if len(labels) != 17:
        raise ValueError(f"Expected 17 verified VSW candidates, found {len(labels)}")
    labels["canonical_smiles"] = labels[smiles_column].map(canonical_smiles)
    labels["canonical_id"] = labels[smiles_column].map(canonical_id_from_source_smiles)
    labels["hit_alias"] = [f"Hit{index}" for index in range(1, len(labels) + 1)]

    raw_records = parse_maestro_metadata(read_maestro(feature_path))
    candidate_smiles = set(labels["canonical_smiles"])
    matched: list[dict[str, str]] = []
    for record in raw_records:
        encoded = record.get("s_user_SMILES", "")
        code = record.get("s_vsw_compound_code", "")
        if not encoded or not code:
            continue
        decoded = decode_maestro_smiles(encoded)
        try:
            normalized = canonical_smiles(decoded)
        except ValueError:
            continue
        if normalized in candidate_smiles:
            record = dict(record)
            record["_decoded_smiles"] = decoded
            record["_canonical_smiles"] = normalized
            matched.append(record)

    # Deduplicate exact serialized records; the final VSW asset should contain
    # one chemically identifiable result record per candidate.
    by_smiles: dict[str, list[dict[str, str]]] = {}
    for record in matched:
        by_smiles.setdefault(record["_canonical_smiles"], []).append(record)
    selected: list[dict[str, str]] = []
    selection_audit: dict[str, Any] = {}
    for normalized in labels["canonical_smiles"]:
        candidates = by_smiles.get(normalized, [])
        unique: dict[str, dict[str, str]] = {}
        for record in candidates:
            key = json.dumps(record, ensure_ascii=False, sort_keys=True)
            unique[key] = record
        candidates = list(unique.values())
        if len(candidates) != 1:
            summary = [
                {
                    "code": row.get("s_vsw_compound_code", ""),
                    "variant": row.get("s_vsw_variant", ""),
                    "title": row.get("s_m_title", ""),
                    "mmgbsa": row.get("r_psp_MMGBSA_dG_Bind", ""),
                }
                for row in candidates
            ]
            raise ValueError(f"Expected one VSW.maegz record for {normalized}, found {len(candidates)}: {summary}")
        selected.append(candidates[0])
        selection_audit[normalized] = {
            "matched_records": 1,
            "compound_code": candidates[0].get("s_vsw_compound_code", ""),
            "variant": candidates[0].get("s_vsw_variant", ""),
            "title": candidates[0].get("s_m_title", ""),
        }

    audit = {
        "labels_file": str(labels_path.relative_to(workspace_root)).replace("\\", "/"),
        "labels_sha256": sha256(labels_path),
        "feature_file": str(feature_path.relative_to(workspace_root)).replace("\\", "/"),
        "feature_sha256": sha256(feature_path),
        "raw_maestro_records": len(raw_records),
        "matched_candidate_records": len(selected),
        "selection": selection_audit,
    }
    return labels, selected, audit


def build_dataset(project_root: Path) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any], list[str]]:
    labels, records, source_audit = load_verified_records(project_root)
    labels_by_smiles = labels.set_index("canonical_smiles")
    record_by_smiles = {record["_canonical_smiles"]: record for record in records}

    # QuickProp eligibility is determined on the full verified 17-candidate set.
    quickprop_properties = sorted(
        {
            prop
            for record in records
            for prop in record
            if re.match(r"^[ris]_qp_", prop)
        }
    )
    quickprop_audit: list[dict[str, Any]] = []
    quickprop_used: list[str] = []
    quickprop_source_by_feature: dict[str, str] = {}
    for prop in quickprop_properties:
        values = np.asarray([numeric(record.get(prop, "")) for record in records], dtype=float)
        complete = bool(np.isfinite(values).all())
        unique_values = int(len(np.unique(values[np.isfinite(values)])))
        feature = quickprop_feature_name(prop)
        used = complete and unique_values > 1
        quickprop_audit.append(
            {
                "feature": feature,
                "feature_group": "quickprop",
                "source_property": prop,
                "source_file": source_audit["feature_file"],
                "data_type": "numeric",
                "non_missing_count": int(np.isfinite(values).sum()),
                "complete_on_dataset": complete,
                "unique_values": unique_values,
                "used_in_model2": used,
                "notes": "Complete numeric QuickProp field; constants are retained in the manifest but excluded from fitting." if complete else "Excluded because at least one verified candidate is missing/non-numeric.",
            }
        )
        if used:
            quickprop_used.append(feature)
            quickprop_source_by_feature[feature] = prop

    fingerprint_generator = rdFingerprintGenerator.GetMorganGenerator(
        radius=2, fpSize=1024, includeChirality=True
    )
    dataset_rows: list[dict[str, Any]] = []
    for normalized in labels["canonical_smiles"]:
        label = labels_by_smiles.loc[normalized]
        record = record_by_smiles[normalized]
        smiles = str(label["SMILES"])
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            raise ValueError(f"Invalid verified candidate SMILES: {smiles}")
        code = str(record.get("s_vsw_compound_code", ""))
        title = str(record.get("s_m_title", ""))
        variant = str(record.get("s_vsw_variant", ""))
        row: dict[str, Any] = {
            "dataset_version": DATASET_VERSION,
            "compound_id": str(label["canonical_id"]),
            "compound_code": code,
            "variant": variant,
            "historical_alias": str(label["hit_alias"]),
            "source_title": title,
            "smiles": smiles,
            "canonical_smiles": normalized,
            "inchi_key": Chem.MolToInchiKey(mol),
            "scaffold": scaffold_key(smiles),
            "mapping_confidence": "confirmed",
            "feature_source": source_audit["feature_file"],
            "label_source": source_audit["labels_file"],
            "label_type": "VSW_static_MMGBSA_dG_Bind",
            "label_protocol": "VSW_static_pose_MMGBSA_lower_is_better",
            "label_score": float(label["MMGBSA dG Bind"]),
        }
        for feature, function in DESCRIPTORS.items():
            row[feature] = float(function(mol))
        fingerprint = fingerprint_generator.GetFingerprint(mol)
        array = np.zeros(1024, dtype=np.int8)
        DataStructs.ConvertToNumpyArray(fingerprint, array)
        for index, value in enumerate(array):
            row[f"morgan1024_{index:04d}"] = int(value)
        for prop, feature in DOCKING_PROPERTY_MAP.items():
            row[feature] = numeric(record.get(prop, ""))
        for feature in quickprop_used:
            row[feature] = numeric(record.get(quickprop_source_by_feature[feature], ""))
        dataset_rows.append(row)

    dataset = pd.DataFrame(dataset_rows).sort_values("compound_id", kind="stable").reset_index(drop=True)
    if dataset["compound_id"].duplicated().any() or dataset["inchi_key"].duplicated().any():
        raise ValueError("dataset_v0.2 contains duplicate molecular identities")

    fingerprint_features = [f"morgan1024_{index:04d}" for index in range(1024)]
    descriptor_features = list(DESCRIPTORS)
    docking_features = list(DOCKING_PROPERTY_MAP.values())
    model_features = fingerprint_features + descriptor_features + docking_features + quickprop_used
    if dataset[model_features].isna().any().any():
        missing = dataset[model_features].isna().sum()
        raise ValueError(f"Model 2 feature matrix contains missing values: {missing[missing.gt(0)].to_dict()}")

    manifest_rows: list[dict[str, Any]] = []
    for feature in fingerprint_features:
        manifest_rows.append(
            {
                "feature": feature,
                "feature_group": "morgan",
                "source_property": "RDKit Morgan radius=2, 1024 bit, chirality=True",
                "source_file": source_audit["labels_file"],
                "data_type": "binary",
                "non_missing_count": len(dataset),
                "complete_on_dataset": True,
                "unique_values": int(dataset[feature].nunique()),
                "used_in_model2": True,
                "notes": "Structure-derived from the source SMILES after identity verification.",
            }
        )
    for feature in descriptor_features:
        manifest_rows.append(
            {
                "feature": feature,
                "feature_group": "rdkit_descriptor",
                "source_property": feature.removeprefix("desc_"),
                "source_file": source_audit["labels_file"],
                "data_type": "numeric",
                "non_missing_count": int(dataset[feature].notna().sum()),
                "complete_on_dataset": bool(dataset[feature].notna().all()),
                "unique_values": int(dataset[feature].nunique()),
                "used_in_model2": True,
                "notes": "Computed from the verified source SMILES; protonation and stereochemistry are preserved.",
            }
        )
    inverse_docking = {feature: prop for prop, feature in DOCKING_PROPERTY_MAP.items()}
    for feature in docking_features:
        manifest_rows.append(
            {
                "feature": feature,
                "feature_group": "docking",
                "source_property": inverse_docking[feature],
                "source_file": source_audit["feature_file"],
                "data_type": "numeric",
                "non_missing_count": int(dataset[feature].notna().sum()),
                "complete_on_dataset": bool(dataset[feature].notna().all()),
                "unique_values": int(dataset[feature].nunique()),
                "used_in_model2": True,
                "notes": "Taken from the same verified VSW pose record as compound code and SMILES.",
            }
        )
    manifest_rows.extend(quickprop_audit)
    manifest = pd.DataFrame(manifest_rows)

    group_counts = Counter(dataset["scaffold"])
    metadata = {
        "dataset_version": DATASET_VERSION,
        "purpose": "AI-assisted ranking of the 17 verified virtual-screening candidates; not biological-activity prediction",
        "sample_count": len(dataset),
        "unique_compound_ids": int(dataset["compound_id"].nunique()),
        "unique_inchi_keys": int(dataset["inchi_key"].nunique()),
        "unique_scaffolds": int(dataset["scaffold"].nunique()),
        "scaffold_group_sizes": sorted(group_counts.values(), reverse=True),
        "identity_rule": "Exact source SMILES/chemical identity matched between VSW.csv and VSW.maegz; unverifiable records excluded",
        "label": {
            "name": "label_score",
            "type": "VSW static MMGBSA dG Bind",
            "direction": "lower_is_better",
            "source": source_audit["labels_file"],
        },
        "feature_groups": {
            "morgan": len(fingerprint_features),
            "rdkit_descriptor": len(descriptor_features),
            "docking": len(docking_features),
            "quickprop_complete_nonconstant": len(quickprop_used),
            "model2_total": len(model_features),
        },
        "quickprop_discovered": len(quickprop_properties),
        "quickprop_complete": int(sum(row["complete_on_dataset"] for row in quickprop_audit)),
        "quickprop_used_nonconstant": len(quickprop_used),
        "source_audit": source_audit,
        "software": {
            "rdkit": rdBase.rdkitVersion,
            "lightgbm": lgb.__version__,
            "shap": shap.__version__,
            "pandas": pd.__version__,
        },
    }
    return dataset, manifest, metadata, model_features


def make_lightgbm(config: ModelConfig | None = None) -> lgb.LGBMRegressor:
    cfg = config or ModelConfig()
    return lgb.LGBMRegressor(
        **asdict(cfg),
        verbosity=-1,
        deterministic=True,
        force_col_wise=True,
    )


def enrichment_metrics(y_true: np.ndarray, y_pred: np.ndarray, top_k: int = TOP_K) -> dict[str, Any]:
    k = min(max(int(top_k), 1), len(y_true))
    true_top = set(np.argsort(y_true, kind="stable")[:k])
    predicted_top = set(np.argsort(y_pred, kind="stable")[:k])
    recovered = len(true_top.intersection(predicted_top))
    expected = k * k / len(y_true)
    return {
        "top_k": k,
        "recovered_hits": recovered,
        "true_hits": k,
        "top_k_enrichment": recovered / expected,
        "hit_recovery": recovered / k,
    }


def metric_row(
    *,
    model_id: str,
    model_name: str,
    feature_set: str,
    feature_count: int,
    protocol: str,
    y_true: np.ndarray,
    y_pred: np.ndarray,
    notes: str,
) -> dict[str, Any]:
    base = evaluate_predictions(y_true, y_pred, top_k=TOP_K)
    enrichment = enrichment_metrics(y_true, y_pred, TOP_K)
    return {
        "model_id": model_id,
        "model": model_name,
        "dataset_version": DATASET_VERSION,
        "evaluation_population": "verified_17_candidate_common_set",
        "evaluation_samples": len(y_true),
        "benchmark_protocol": protocol,
        "feature_set": feature_set,
        "feature_count": feature_count,
        "spearman": base["spearman"],
        "rmse": base["rmse"],
        "ndcg": base["ndcg"],
        **enrichment,
        "status": base["status"],
        "notes": notes,
    }


def load_legacy_lightgbm_oof(project_root: Path, compound_ids: list[str]) -> np.ndarray:
    rows = pd.DataFrame(json.loads((project_root / "results" / "phase15_predictions.json").read_text(encoding="utf-8")))
    rows = rows.loc[rows["model"].eq("lightgbm")].copy()
    if rows["canonical_id"].duplicated().any():
        raise ValueError("Legacy LightGBM OOF predictions contain duplicate canonical_id")
    prediction_map = rows.set_index("canonical_id")["predicted_score"]
    missing = sorted(set(compound_ids).difference(prediction_map.index))
    if missing:
        raise ValueError(f"Legacy LightGBM predictions missing candidates: {missing}")
    return prediction_map.loc[compound_ids].to_numpy(dtype=float)


def priority_scores(raw_scores: np.ndarray) -> np.ndarray:
    ranks = rankdata(raw_scores, method="average")
    if len(raw_scores) == 1:
        return np.asarray([100.0])
    return 100.0 * (len(raw_scores) - ranks) / (len(raw_scores) - 1)


def save_comparison_plot(comparison: pd.DataFrame, output_path: Path) -> None:
    metrics = [("spearman", "Spearman"), ("ndcg", "NDCG@5"), ("top_k_enrichment", "Top-5 enrichment"), ("hit_recovery", "Hit recovery")]
    colors = ["#7F8C8D", "#4C78A8", "#54A24B"]
    fig, axes = plt.subplots(1, 4, figsize=(14, 4.0))
    for axis, (column, title) in zip(axes, metrics):
        values = comparison[column].astype(float).to_numpy()
        bars = axis.bar(comparison["model_id"], values, color=colors)
        axis.set_title(title, fontweight="bold")
        axis.tick_params(axis="x", rotation=22, labelsize=8)
        axis.grid(axis="y", alpha=0.2)
        if column == "spearman":
            axis.axhline(0, color="#555555", linewidth=0.9)
            lower = min(-0.6, float(values.min()) * 1.2)
            axis.set_ylim(lower, 1.0)
            for bar, value in zip(bars, values):
                offset = 0.025 if value >= 0 else -0.055
                axis.text(bar.get_x() + bar.get_width() / 2, value + offset, f"{value:.2f}", ha="center", va="bottom" if value >= 0 else "top", fontsize=8)
        else:
            axis.bar_label(bars, fmt="%.2f", fontsize=8, padding=2)
            upper = max(1.0, float(values.max()) * 1.25) if column != "top_k_enrichment" else float(values.max()) * 1.25
            axis.set_ylim(0, upper)
    fig.suptitle("ATP-Navigator AI ranking v1.0 — verified 17-candidate common set", fontsize=14, fontweight="bold")
    fig.text(0.5, 0.01, "Scaffold-grouped OOF for LightGBM models; computational MM/GBSA ranking only, not biological activity.", ha="center", fontsize=8)
    fig.tight_layout(rect=(0, 0.06, 1, 0.92))
    fig.savefig(output_path, dpi=200, bbox_inches="tight")
    plt.close(fig)


def save_ranking_plot(ranking: pd.DataFrame, output_path: Path) -> None:
    ordered = ranking.sort_values("ai_rank", ascending=False)
    fig, axis = plt.subplots(figsize=(10.5, 6.2))
    axis.barh(ordered["historical_alias"], ordered["candidate_priority_score"], color="#2F6B8A")
    axis.set_xlabel("Candidate priority score (higher is better)")
    axis.set_ylabel("Candidate")
    axis.set_xlim(0, 105)
    axis.set_title("ATP-Navigator AI ranking output v1.0", fontweight="bold")
    axis.grid(axis="x", alpha=0.2)
    fig.text(0.5, 0.01, "Retrospective full-fit demonstration on dataset_v0.2; priority is rank-scaled, not a probability.", ha="center", fontsize=8)
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    fig.savefig(output_path, dpi=200, bbox_inches="tight")
    plt.close(fig)


def run_phase3(project_root: Path) -> dict[str, Any]:
    project_root = project_root.resolve()
    results_dir = project_root / "results"
    figures_dir = results_dir / "figures"
    models_dir = project_root / "models"
    dataset_dir = project_root / "data" / DATASET_VERSION
    for directory in (results_dir, figures_dir, models_dir, dataset_dir):
        directory.mkdir(parents=True, exist_ok=True)

    dataset, manifest, dataset_metadata, model_features = build_dataset(project_root)
    X = dataset[model_features].astype(float)
    y = dataset["label_score"].to_numpy(dtype=float)
    groups = dataset["scaffold"].to_numpy()
    ids = dataset["compound_id"].tolist()

    logo = LeaveOneGroupOut()
    enhanced_oof = np.full(len(dataset), np.nan, dtype=float)
    fold_ids = np.full(len(dataset), -1, dtype=int)
    for fold_id, (train_index, test_index) in enumerate(logo.split(X, y, groups), start=1):
        model = make_lightgbm()
        model.fit(X.iloc[train_index], y[train_index])
        enhanced_oof[test_index] = model.predict(X.iloc[test_index])
        fold_ids[test_index] = fold_id
    if not np.isfinite(enhanced_oof).all() or (fold_ids < 1).any():
        raise ValueError("Enhanced OOF prediction coverage is incomplete")

    docking_pred = dataset["glide_docking_score"].to_numpy(dtype=float)
    legacy_pred = load_legacy_lightgbm_oof(project_root, ids)
    comparison_rows = [
        metric_row(
            model_id="Model 0",
            model_name="docking_only",
            feature_set="Glide docking score",
            feature_count=1,
            protocol="same_population_direct_ranking",
            y_true=y,
            y_pred=docking_pred,
            notes="No model fitting; direct Glide ranking on the same verified 17 candidates.",
        ),
        metric_row(
            model_id="Legacy P1 LightGBM",
            model_name="lightgbm_baseline",
            feature_set="Morgan1024 + RDKit10 + ADMET_SUM",
            feature_count=1035,
            protocol="scaffold_grouped_leave_one_out",
            y_true=y,
            y_pred=legacy_pred,
            notes="Existing Phase 1.5 OOF predictions retained and re-evaluated on the same candidate order.",
        ),
        metric_row(
            model_id="Model 2",
            model_name="lightgbm_enhanced_v1",
            feature_set="Morgan1024 + RDKit11 + verified VSW docking + complete nonconstant QuickProp",
            feature_count=len(model_features),
            protocol="scaffold_grouped_leave_one_out",
            y_true=y,
            y_pred=enhanced_oof,
            notes="All feature extraction precedes no learned preprocessing; molecular identities are unique and scaffold groups are held out.",
        ),
    ]
    comparison = pd.DataFrame(comparison_rows)

    oof_rows: list[dict[str, Any]] = []
    prediction_sets = [
        ("Model 0", "docking_only", docking_pred, np.zeros(len(dataset), dtype=int)),
        ("Legacy P1 LightGBM", "lightgbm_baseline", legacy_pred, fold_ids),
        ("Model 2", "lightgbm_enhanced_v1", enhanced_oof, fold_ids),
    ]
    for model_id, model_name, predictions, folds in prediction_sets:
        for index, row in dataset.iterrows():
            oof_rows.append(
                {
                    "compound_id": row["compound_id"],
                    "compound_code": row["compound_code"],
                    "historical_alias": row["historical_alias"],
                    "model_id": model_id,
                    "model": model_name,
                    "fold_id": int(folds[index]),
                    "scaffold": row["scaffold"],
                    "observed_mmgbsa": float(y[index]),
                    "predicted_score": float(predictions[index]),
                    "score_direction": "lower_is_better",
                    "prediction_type": "direct_ranking" if model_name == "docking_only" else "out_of_fold",
                }
            )

    final_model = make_lightgbm()
    final_model.fit(X, y)
    full_fit_scores = final_model.predict(X)
    priority = priority_scores(full_fit_scores)
    ai_rank = rankdata(full_fit_scores, method="ordinal").astype(int)
    ranking = pd.DataFrame(
        {
            "compound_id": dataset["compound_id"],
            "compound_code": dataset["compound_code"],
            "historical_alias": dataset["historical_alias"],
            "smiles": dataset["smiles"],
            "model_version": MODEL_VERSION,
            "ai_rank": ai_rank,
            "candidate_priority_score": priority,
            "model_raw_score": full_fit_scores,
            "raw_score_direction": "lower_is_better",
            "glide_docking_score": dataset["glide_docking_score"],
            "reference_mmgbsa": dataset["label_score"],
            "feature_source": dataset["feature_source"],
            "prediction_scope": "retrospective_full_fit_demo",
        }
    ).sort_values(["ai_rank", "compound_id"], kind="stable")

    explainer = shap.TreeExplainer(final_model)
    shap_values = np.asarray(explainer.shap_values(X), dtype=float)
    if shap_values.shape != X.shape:
        raise ValueError(f"Unexpected SHAP shape: {shap_values.shape} vs {X.shape}")
    group_map = dict(zip(manifest["feature"], manifest["feature_group"]))
    importance = pd.DataFrame(
        {
            "feature": model_features,
            "feature_group": [group_map.get(feature, "unknown") for feature in model_features],
            "mean_abs_shap": np.mean(np.abs(shap_values), axis=0),
            "mean_shap": np.mean(shap_values, axis=0),
            "max_abs_shap": np.max(np.abs(shap_values), axis=0),
            "nonzero_samples": np.count_nonzero(np.abs(shap_values) > 1e-12, axis=0),
            "shap_scope": "full_fit_exploratory",
        }
    ).sort_values(["mean_abs_shap", "feature"], ascending=[False, True], kind="stable")
    importance.insert(0, "importance_rank", np.arange(1, len(importance) + 1))

    plt.figure(figsize=(10, 7))
    shap.summary_plot(shap_values, X, max_display=20, show=False, plot_size=None)
    plt.title("ATP-Navigator Model 2 SHAP summary\nfull-fit exploratory explanation, n=17", fontweight="bold")
    plt.tight_layout()
    plt.savefig(figures_dir / "shap_summary_v1.png", dpi=220, bbox_inches="tight")
    plt.close()

    save_comparison_plot(comparison, figures_dir / "phase3_model_comparison.png")
    save_ranking_plot(ranking, figures_dir / "phase3_ranking_output.png")

    bundle = {
        "model": final_model,
        "model_version": MODEL_VERSION,
        "dataset_version": DATASET_VERSION,
        "feature_columns": model_features,
        "feature_groups": {feature: group_map.get(feature, "unknown") for feature in model_features},
        "score_direction": "lower_is_better",
        "priority_score_definition": "rank-scaled 0-100 on the submitted candidate batch; higher is better",
        "model_config": asdict(ModelConfig()),
    }
    joblib.dump(bundle, models_dir / "lightgbm_enhanced_v1.joblib")

    dataset_headers = list(dataset.columns)
    manifest_headers = list(manifest.columns)
    dataset_payload = {
        "samples_headers": dataset_headers,
        "samples_rows": dataset.replace({np.nan: None}).to_dict(orient="records"),
        "feature_manifest_headers": manifest_headers,
        "feature_manifest_rows": manifest.replace({np.nan: None}).to_dict(orient="records"),
    }
    results_payload = {
        "comparison_headers": list(comparison.columns),
        "comparison_rows": comparison.replace({np.nan: None}).to_dict(orient="records"),
        "oof_headers": list(oof_rows[0]),
        "oof_rows": oof_rows,
        "importance_headers": list(importance.columns),
        "importance_rows": importance.replace({np.nan: None}).to_dict(orient="records"),
        "ranking_headers": list(ranking.columns),
        "ranking_rows": ranking.replace({np.nan: None}).to_dict(orient="records"),
    }
    (results_dir / "phase3_dataset_payload.json").write_text(
        json.dumps(dataset_payload, ensure_ascii=False), encoding="utf-8"
    )
    (results_dir / "phase3_results_payload.json").write_text(
        json.dumps(results_payload, ensure_ascii=False), encoding="utf-8"
    )
    (dataset_dir / "dataset_metadata.json").write_text(
        json.dumps(dataset_metadata, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    run_metadata = {
        "phase": "Phase 3",
        "dataset_version": DATASET_VERSION,
        "model_version": MODEL_VERSION,
        "preserved_prior_artifacts": True,
        "trained_large_model": False,
        "task_definition": "computational MMGBSA candidate ranking",
        "not_biological_activity_prediction": True,
        "sample_count": len(dataset),
        "scaffold_count": int(dataset["scaffold"].nunique()),
        "feature_count": len(model_features),
        "model_config": asdict(ModelConfig()),
        "comparison": comparison_rows,
        "top_shap_features": importance.head(20).to_dict(orient="records"),
        "outputs": {
            "model": "models/lightgbm_enhanced_v1.joblib",
            "shap_plot": "results/figures/shap_summary_v1.png",
            "comparison_plot": "results/figures/phase3_model_comparison.png",
            "ranking_plot": "results/figures/phase3_ranking_output.png",
        },
        "limitations": [
            "Only 17 verified candidates and 11 Bemis-Murcko scaffold groups are available.",
            "Labels are computational static MM/GBSA values, not measured biological activity.",
            "Candidates were selected by an upstream virtual-screening process, creating selection bias.",
            "SHAP values explain the full-fit small-sample model and are exploratory, non-causal, and not OOF explanations.",
            "The priority score is a rank-scaled batch score, not a calibrated probability.",
        ],
    }
    (results_dir / "phase3_run_metadata.json").write_text(
        json.dumps(run_metadata, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return run_metadata


def rank_candidates(candidate_features: pd.DataFrame, model_bundle_path: str | Path) -> pd.DataFrame:
    """Rank a candidate feature table with the saved Phase 3 model bundle.

    The caller must provide the exact verified feature columns stored in the
    bundle. Missing columns fail closed; unverifiable identities are not filled.
    """
    bundle = joblib.load(model_bundle_path)
    feature_columns = bundle["feature_columns"]
    missing = sorted(set(feature_columns).difference(candidate_features.columns))
    if missing:
        raise ValueError(f"Candidate table missing {len(missing)} required features: {missing[:20]}")
    X = candidate_features[feature_columns].apply(pd.to_numeric, errors="coerce")
    if X.isna().any().any():
        raise ValueError("Candidate table contains missing/non-numeric required features")
    raw = np.asarray(bundle["model"].predict(X), dtype=float)
    output = candidate_features.copy()
    output["model_version"] = bundle["model_version"]
    output["model_raw_score"] = raw
    output["candidate_priority_score"] = priority_scores(raw)
    output["ai_rank"] = rankdata(raw, method="ordinal").astype(int)
    return output.sort_values(["ai_rank"], kind="stable")


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    print(json.dumps(run_phase3(root), ensure_ascii=False, indent=2))
