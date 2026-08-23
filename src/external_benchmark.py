"""ATP-Navigator Phase 6B external benchmark pipeline.

The pipeline standardizes public ATP synthase inhibitor records, deduplicates
structures, calculates Morgan fingerprints, and asks the unchanged Phase 5
Decision Engine for scores. Novel structures without the required upstream
computational evidence remain unscored. No model is trained by this module.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from rdkit import Chem
from rdkit.Chem import rdFingerprintGenerator
from scipy.stats import kendalltau, spearmanr

from decision_engine import DecisionEngine, atomic_to_csv, atomic_write_text, sha256


MODULE_VERSION = "ATP-Navigator_Phase6B_External_Benchmark_v1.0"
DEFAULT_DATASET_LAYER = "layer_2_atp_synthase_specific"
MORGAN_RADIUS = 2
MORGAN_BITS = 2048

REQUIRED_INPUT_FIELDS = [
    "compound_id",
    "SMILES",
    "target",
    "organism",
    "activity_type",
    "activity_value",
    "reference",
]

RANKING_COLUMNS = [
    "benchmark_rank",
    "compound_id",
    "SMILES",
    "canonical_smiles",
    "target",
    "organism",
    "activity_type",
    "activity_value",
    "activity_relation",
    "activity_numeric",
    "activity_value_status",
    "activity_direction",
    "unit",
    "reference",
    "atp_navigator_score",
    "confidence",
    "confidence_score",
    "scoring_status",
    "independence_status",
]

METRIC_COLUMNS = [
    "benchmark_scope",
    "target",
    "organism",
    "activity_type",
    "unit",
    "activity_direction",
    "n_scored_compounds",
    "n_exact_numeric_compounds",
    "spearman_correlation",
    "kendall_tau",
    "status",
    "reason",
]


def _normalize_text(value: Any, unknown: str = "unknown") -> str:
    if pd.isna(value):
        return unknown
    text = re.sub(r"\s+", " ", str(value).strip())
    return text if text else unknown


def _canonicalize_smiles(value: Any) -> tuple[str | None, str]:
    if pd.isna(value) or not str(value).strip():
        return None, "missing_smiles"
    molecule = Chem.MolFromSmiles(str(value).strip())
    if molecule is None:
        return None, "invalid_smiles"
    return Chem.MolToSmiles(molecule, canonical=True, isomericSmiles=True), "valid"


def _fingerprint(canonical_smiles: str) -> tuple[str, int]:
    molecule = Chem.MolFromSmiles(canonical_smiles)
    if molecule is None:
        raise ValueError("Canonical SMILES could not be parsed for Morgan fingerprint")
    generator = rdFingerprintGenerator.GetMorganGenerator(
        radius=MORGAN_RADIUS, fpSize=MORGAN_BITS
    )
    fingerprint = generator.GetFingerprint(molecule)
    bit_string = fingerprint.ToBitString()
    fingerprint_hex = format(int(bit_string, 2), f"0{MORGAN_BITS // 4}x")
    return fingerprint_hex, int(fingerprint.GetNumOnBits())


def _parse_activity(value: Any) -> tuple[str, float | None, str]:
    if pd.isna(value) or not str(value).strip():
        return "unknown", None, "missing"
    text = str(value).strip().replace("≤", "<=").replace("≥", ">=")
    relation_match = re.match(r"^(<=|>=|<|>|=|~)?\s*(-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)$", text)
    if not relation_match:
        return "unknown", None, "non_numeric_or_range"
    relation = relation_match.group(1) or "="
    numeric = float(relation_match.group(2))
    status = "exact_numeric" if relation == "=" else "censored_numeric"
    return relation, numeric, status


def _activity_direction(activity_type: str) -> str:
    normalized = activity_type.lower()
    if any(token in normalized for token in ("mic", "ic50", "ki", "kd", "ec50")):
        return "lower_is_better"
    if "inhibition" in normalized or "activity" in normalized:
        return "higher_is_better"
    return "unknown"


def _safe_correlation(first: pd.Series, second: pd.Series, method: str) -> float | None:
    valid = pd.DataFrame({"first": first, "second": second}).dropna()
    if len(valid) < 3 or valid["first"].nunique() < 2 or valid["second"].nunique() < 2:
        return None
    if method == "spearman":
        value = spearmanr(valid["first"], valid["second"]).statistic
    elif method == "kendall":
        value = kendalltau(valid["first"], valid["second"]).statistic
    else:
        raise ValueError(f"Unsupported method: {method}")
    return None if np.isnan(value) else float(value)


def _stable_join(values: pd.Series) -> str:
    unique = sorted({_normalize_text(value) for value in values if _normalize_text(value) != "unknown"})
    return " | ".join(unique) if unique else "unknown"


def _structure_id(canonical_smiles: str) -> str:
    digest = hashlib.sha256(canonical_smiles.encode("utf-8")).hexdigest()[:12].upper()
    return f"EXT-SMI-{digest}"


STANDARDIZED_RECORD_COLUMNS = [
    "source_row",
    "source_compound_id",
    "source_smiles",
    "canonical_smiles",
    "structure_status",
    "target",
    "organism",
    "activity_type",
    "activity_value",
    "activity_relation",
    "activity_numeric",
    "activity_value_status",
    "activity_direction",
    "unit",
    "reference",
    "data_source",
    "label_confidence",
]


class ExternalBenchmarkPipeline:
    def __init__(self, project_root: Path, input_path: Path | None = None) -> None:
        self.project_root = project_root.resolve()
        self.dataset_v1_path = (
            self.project_root / "data" / "dataset_v1.0" / "ATP_Navigator_Dataset_v1.csv"
        )
        self.input_path = (input_path.resolve() if input_path else self.dataset_v1_path)
        self.output_dir = self.project_root / "results" / "phase6B"
        self.report_path = self.project_root / "docs" / "Phase6B_External_Validation_Report.md"
        self._using_default_layer = self.input_path == self.dataset_v1_path.resolve()

    def load_input(self) -> pd.DataFrame:
        if not self.input_path.exists():
            return pd.DataFrame(columns=REQUIRED_INPUT_FIELDS)
        source = pd.read_csv(self.input_path, low_memory=False)
        if self._using_default_layer:
            required = {
                "compound_id",
                "canonical_smiles",
                "target",
                "organism",
                "activity_type",
                "activity_value",
                "reference",
                "dataset_layer",
            }
            missing = required.difference(source.columns)
            if missing:
                raise ValueError(f"Dataset v1.0 missing fields: {sorted(missing)}")
            source = source[source["dataset_layer"].eq(DEFAULT_DATASET_LAYER)].copy()
            source = source.rename(columns={"canonical_smiles": "SMILES"})
        else:
            if "SMILES" not in source.columns:
                for alias in ("smiles", "canonical_smiles"):
                    if alias in source.columns:
                        source = source.rename(columns={alias: "SMILES"})
                        break
            missing = set(REQUIRED_INPUT_FIELDS).difference(source.columns)
            if missing:
                raise ValueError(f"External benchmark missing fields: {sorted(missing)}")

        for optional in ("unit", "data_source", "label_confidence"):
            if optional not in source.columns:
                source[optional] = "unknown"
        return source[[*REQUIRED_INPUT_FIELDS, "unit", "data_source", "label_confidence"]].copy()

    def standardize_records(self, source: pd.DataFrame) -> pd.DataFrame:
        rows: list[dict[str, Any]] = []
        for source_row, row in source.reset_index(drop=True).iterrows():
            canonical_smiles, structure_status = _canonicalize_smiles(row["SMILES"])
            relation, numeric, activity_status = _parse_activity(row["activity_value"])
            rows.append(
                {
                    "source_row": source_row + 1,
                    "source_compound_id": _normalize_text(row["compound_id"]),
                    "source_smiles": _normalize_text(row["SMILES"]),
                    "canonical_smiles": canonical_smiles,
                    "structure_status": structure_status,
                    "target": _normalize_text(row["target"]),
                    "organism": _normalize_text(row["organism"]),
                    "activity_type": _normalize_text(row["activity_type"]),
                    "activity_value": _normalize_text(row["activity_value"]),
                    "activity_relation": relation,
                    "activity_numeric": numeric,
                    "activity_value_status": activity_status,
                    "activity_direction": _activity_direction(_normalize_text(row["activity_type"])),
                    "unit": _normalize_text(row["unit"]),
                    "reference": _normalize_text(row["reference"]),
                    "data_source": _normalize_text(row["data_source"]),
                    "label_confidence": _normalize_text(row["label_confidence"]),
                }
            )
        return pd.DataFrame(rows, columns=STANDARDIZED_RECORD_COLUMNS)

    def known_external_training_structures(self) -> set[str]:
        if not self.dataset_v1_path.exists():
            return set()
        dataset = pd.read_csv(
            self.dataset_v1_path,
            usecols=["canonical_smiles", "dataset_layer"],
            low_memory=False,
        )
        layer = dataset[dataset["dataset_layer"].eq(DEFAULT_DATASET_LAYER)]
        output: set[str] = set()
        for value in layer["canonical_smiles"].dropna():
            canonical, status = _canonicalize_smiles(value)
            if status == "valid" and canonical:
                output.add(canonical)
        return output

    def deduplicate_structures(
        self, records: pd.DataFrame, decision_ranking: pd.DataFrame
    ) -> pd.DataFrame:
        valid = records[records["structure_status"].eq("valid")].copy()
        if valid.empty:
            return pd.DataFrame(
                columns=[
                    "benchmark_compound_id",
                    "source_compound_ids",
                    "canonical_smiles",
                    "source_record_count",
                    "targets",
                    "organisms",
                    "activity_types",
                    "units",
                    "references",
                    "morgan_radius",
                    "morgan_n_bits",
                    "morgan2048_hex",
                    "morgan2048_on_bit_count",
                    "external_training_structure_overlap",
                    "decision_engine_compound_id",
                    "atp_navigator_score",
                    "confidence",
                    "confidence_score",
                    "scoring_status",
                    "independence_status",
                ]
            )

        training_structures = self.known_external_training_structures()
        decision_by_smiles = decision_ranking.set_index("canonical_smiles")
        rows: list[dict[str, Any]] = []
        for canonical_smiles, group in valid.groupby("canonical_smiles", sort=True):
            fingerprint_hex, bit_count = _fingerprint(canonical_smiles)
            training_overlap = canonical_smiles in training_structures
            if canonical_smiles in decision_by_smiles.index:
                decision = decision_by_smiles.loc[canonical_smiles]
                if isinstance(decision, pd.DataFrame):
                    raise ValueError("Decision Engine contains duplicated canonical SMILES")
                score = float(decision["final_score"])
                confidence = str(decision["confidence"])
                confidence_score = float(decision["confidence_score"])
                decision_id = str(decision["compound_id"])
                scoring_status = "scored_existing_phase5_evidence"
            else:
                score = None
                confidence = "unknown"
                confidence_score = None
                decision_id = "unknown"
                scoring_status = "unscored_missing_required_computational_evidence"

            if training_overlap:
                independence = "external_knowledge_training_overlap"
            else:
                independence = "no_known_structure_overlap_with_external_training"
            rows.append(
                {
                    "benchmark_compound_id": _structure_id(canonical_smiles),
                    "source_compound_ids": _stable_join(group["source_compound_id"]),
                    "canonical_smiles": canonical_smiles,
                    "source_record_count": int(len(group)),
                    "targets": _stable_join(group["target"]),
                    "organisms": _stable_join(group["organism"]),
                    "activity_types": _stable_join(group["activity_type"]),
                    "units": _stable_join(group["unit"]),
                    "references": _stable_join(group["reference"]),
                    "morgan_radius": MORGAN_RADIUS,
                    "morgan_n_bits": MORGAN_BITS,
                    "morgan2048_hex": fingerprint_hex,
                    "morgan2048_on_bit_count": bit_count,
                    "external_training_structure_overlap": training_overlap,
                    "decision_engine_compound_id": decision_id,
                    "atp_navigator_score": score,
                    "confidence": confidence,
                    "confidence_score": confidence_score,
                    "scoring_status": scoring_status,
                    "independence_status": independence,
                }
            )
        return pd.DataFrame(rows)

    def build_ranking(
        self, records: pd.DataFrame, structures: pd.DataFrame
    ) -> pd.DataFrame:
        if structures.empty or structures["atp_navigator_score"].notna().sum() == 0:
            return pd.DataFrame(columns=RANKING_COLUMNS)
        scores = structures[
            [
                "canonical_smiles",
                "atp_navigator_score",
                "confidence",
                "confidence_score",
                "scoring_status",
                "independence_status",
            ]
        ]
        scored_records = records.merge(scores, on="canonical_smiles", how="inner", validate="many_to_one")
        scored_records = scored_records[scored_records["atp_navigator_score"].notna()].copy()
        if scored_records.empty:
            return pd.DataFrame(columns=RANKING_COLUMNS)

        scored_records["benchmark_rank"] = scored_records["atp_navigator_score"].rank(
            method="dense", ascending=False
        ).astype("Int64")
        scored_records["compound_id"] = scored_records["source_compound_id"]
        scored_records["SMILES"] = scored_records["source_smiles"]
        ranking = scored_records[RANKING_COLUMNS].sort_values(
            ["benchmark_rank", "compound_id", "target", "organism", "activity_type"],
            kind="stable",
        )
        return ranking.reset_index(drop=True)

    def compute_metrics(self, ranking: pd.DataFrame) -> pd.DataFrame:
        independent = ranking[
            ranking["independence_status"].eq("no_known_structure_overlap_with_external_training")
            & ranking["activity_value_status"].eq("exact_numeric")
            & ranking["activity_direction"].ne("unknown")
        ].copy() if "activity_value_status" in ranking.columns else pd.DataFrame()

        rows: list[dict[str, Any]] = []
        if independent.empty:
            rows.append(
                {
                    "benchmark_scope": "independent_external_validation",
                    "target": "unknown",
                    "organism": "unknown",
                    "activity_type": "unknown",
                    "unit": "unknown",
                    "activity_direction": "unknown",
                    "n_scored_compounds": int(ranking["canonical_smiles"].nunique()) if not ranking.empty else 0,
                    "n_exact_numeric_compounds": 0,
                    "spearman_correlation": None,
                    "kendall_tau": None,
                    "status": "empty",
                    "reason": (
                        "No independently eligible scored compounds. Novel external structures lack the "
                        "required Decision Engine evidence, and known external-training structures are excluded."
                    ),
                }
            )
            return pd.DataFrame(rows, columns=METRIC_COLUMNS)

        group_fields = ["target", "organism", "activity_type", "unit", "activity_direction"]
        for keys, group in independent.groupby(group_fields, dropna=False, sort=True):
            target, organism, activity_type, unit, direction = keys
            collapsed = group.groupby("canonical_smiles", as_index=False).agg(
                atp_navigator_score=("atp_navigator_score", "first"),
                activity_numeric=("activity_numeric", "median"),
            )
            n = int(len(collapsed))
            if n < 3:
                status = "not_evaluable"
                reason = "Fewer than 3 independent exact-numeric compounds in this endpoint stratum."
                spearman = None
                kendall = None
            else:
                experimental_desirability = (
                    -collapsed["activity_numeric"]
                    if direction == "lower_is_better"
                    else collapsed["activity_numeric"]
                )
                spearman = _safe_correlation(
                    collapsed["atp_navigator_score"], experimental_desirability, "spearman"
                )
                kendall = _safe_correlation(
                    collapsed["atp_navigator_score"], experimental_desirability, "kendall"
                )
                status = "evaluated" if spearman is not None and kendall is not None else "not_evaluable"
                reason = (
                    "Validation-only rank correlation; no training performed."
                    if status == "evaluated"
                    else "Scores or experimental values do not provide enough variation."
                )
            rows.append(
                {
                    "benchmark_scope": "independent_external_validation",
                    "target": target,
                    "organism": organism,
                    "activity_type": activity_type,
                    "unit": unit,
                    "activity_direction": direction,
                    "n_scored_compounds": n,
                    "n_exact_numeric_compounds": n,
                    "spearman_correlation": spearman,
                    "kendall_tau": kendall,
                    "status": status,
                    "reason": reason,
                }
            )
        return pd.DataFrame(rows, columns=METRIC_COLUMNS)

    def report(
        self,
        source: pd.DataFrame,
        records: pd.DataFrame,
        structures: pd.DataFrame,
        ranking: pd.DataFrame,
        metrics: pd.DataFrame,
    ) -> str:
        valid_records = int(records["structure_status"].eq("valid").sum()) if not records.empty else 0
        invalid_records = int(len(records) - valid_records)
        unique_structures = int(len(structures))
        duplicates_removed = max(valid_records - unique_structures, 0)
        training_overlap = int(
            structures["external_training_structure_overlap"].fillna(False).astype(bool).sum()
        ) if not structures.empty else 0
        scored_structures = int(structures["atp_navigator_score"].notna().sum()) if not structures.empty else 0
        evaluated_metrics = int(metrics["status"].eq("evaluated").sum()) if not metrics.empty else 0
        activity_counts = (
            records["activity_type"].value_counts(dropna=False).to_dict() if not records.empty else {}
        )
        activity_lines = "\n".join(
            f"| {activity_type} | {count} |" for activity_type, count in activity_counts.items()
        ) or "| empty | 0 |"
        input_hash = sha256(self.input_path) if self.input_path.exists() else "not_available"
        try:
            input_display = self.input_path.relative_to(self.project_root).as_posix()
        except ValueError:
            input_display = str(self.input_path)

        return f"""# ATP-Navigator Phase 6B External Validation Report

生成模块：`{MODULE_VERSION}`

## 结论

External Benchmark Pipeline已经建立并成功执行数据标准化、结构去重和Morgan2048 fingerprint计算。当前ATP-Navigator可评分外部集合为**empty**，因此`benchmark_ranking.csv`只有表头，`benchmark_metrics.csv`明确记录`status=empty`，没有生成虚假相关性或实验结果。

## 输入审计

- 输入文件：`{input_display}`
- 输入SHA-256：`{input_hash}`
- 原始记录：{len(source)}
- RDKit可解析结构记录：{valid_records}
- 缺失或无效结构记录：{invalid_records}
- 去重后唯一结构：{unique_structures}
- 合并的重复结构记录：{duplicates_removed}
- 与已知Model v2外部知识训练结构重叠：{training_overlap}

### Activity type分布

| activity_type | records |
|---|---:|
{activity_lines}

MIC、IC50、细胞毒性、Activity和Inhibition保持不同端点，不作为同一个label或metric混合。

## Pipeline

1. 接收`compound_id, SMILES, target, organism, activity_type, activity_value, reference`；`unit`为推荐可选字段；
2. 使用RDKit生成isomeric canonical SMILES并记录无效结构；
3. 按canonical SMILES去重，同时保留来源compound ID、端点、organism和reference集合；
4. 计算Morgan fingerprint：radius={MORGAN_RADIUS}、nBits={MORGAN_BITS}；
5. 调用未修改的Phase 5 Decision Engine。只有已具备完整Phase 5计算证据的结构才能取得分数；
6. 仅对成功评分的结构生成ranking；
7. metric只在外部训练结构不重叠、实验值为精确数值、且target/organism/activity type/unit/direction单一的stratum内计算。

## 当前评分与验证状态

- 可评分唯一结构：{scored_structures}
- ranking行数：{len(ranking)}
- 成功评价metric strata：{evaluated_metrics}
- 当前状态：`empty`

现有Layer 2结构是Model v2外部知识数据来源，不能作为完全独立验证集；同时这些外部分子没有内部Docking、静态MM/GBSA、Model v3和完整ADMET等Decision Engine必需证据。因此不修改评分逻辑、不补假特征，分数保持空值。

## 输出

- `results/phase6B/standardized_benchmark_compounds.csv`：去重结构、Morgan fingerprint、训练重叠和评分状态；
- `results/phase6B/benchmark_ranking.csv`：仅成功评分的外部候选；当前empty；
- `results/phase6B/benchmark_metrics.csv`：验证metric及不可评价原因；当前empty。

## 不变性

- `src/decision_engine.py` SHA-256：`{sha256(self.project_root / 'src' / 'decision_engine.py')}`
- `scoring_config.json` SHA-256：`{sha256(self.project_root / 'scoring_config.json')}`
- 未训练或修改Model v0-v3；
- 未改变Phase 5 Decision Engine评分公式或权重；
- 公开activity只用于未来验证分层，不进入训练或当前评分。

## 下一步满足可评价条件所需数据

对新的独立候选，必须先按冻结协议生成Decision Engine所需计算证据，再取得与训练数据隔离的同endpoint、organism、unit和assay实验结果。验证集在评分和指标方案冻结后才能打开使用。
"""

    def run(self) -> dict[str, Any]:
        source = self.load_input()
        records = self.standardize_records(source)

        decision_engine = DecisionEngine(self.project_root)
        decision_ranking = decision_engine.score()
        structures = self.deduplicate_structures(records, decision_ranking)
        ranking = self.build_ranking(records, structures)
        metrics = self.compute_metrics(ranking)

        atomic_to_csv(structures, self.output_dir / "standardized_benchmark_compounds.csv")
        atomic_to_csv(ranking, self.output_dir / "benchmark_ranking.csv")
        atomic_to_csv(metrics, self.output_dir / "benchmark_metrics.csv")
        atomic_write_text(
            self.report_path,
            self.report(source, records, structures, ranking, metrics),
        )

        return {
            "module_version": MODULE_VERSION,
            "input_records": int(len(source)),
            "valid_structure_records": int(records["structure_status"].eq("valid").sum())
            if not records.empty
            else 0,
            "unique_structures": int(len(structures)),
            "scored_structures": int(structures["atp_navigator_score"].notna().sum())
            if not structures.empty
            else 0,
            "ranking_rows": int(len(ranking)),
            "evaluated_metric_strata": int(metrics["status"].eq("evaluated").sum()),
            "benchmark_status": "empty" if ranking.empty else "partially_scored",
        }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--project-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="ATP-Navigator repository root",
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=None,
        help=(
            "Optional external CSV. If omitted, Dataset v1.0 Layer 2 is audited. "
            "Required fields: compound_id, SMILES, target, organism, activity_type, "
            "activity_value, reference."
        ),
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    pipeline = ExternalBenchmarkPipeline(args.project_root, args.input)
    payload = pipeline.run()
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
