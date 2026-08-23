"""ATP-Navigator Phase 6A robustness and benchmark validation module.

This module reads the preserved Phase 5 ranking and existing Dataset v1.0.
It does not train a supervised model, edit Model v0-v3, or treat computational
evidence as experimental truth.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import kendalltau, spearmanr

from decision_engine import atomic_to_csv, atomic_write_text, sha256, validate_weights


MODULE_VERSION = "ATP-Navigator_Phase6A_Robustness_v1.0"
COMPONENTS = [
    "binding_score",
    "ATP_target_score",
    "antibacterial_score",
    "druglikeness_score",
]

SCENARIOS: dict[str, dict[str, Any]] = {
    "default": {
        "description": "Phase 5 registered default",
        "weights": {
            "binding_score": 0.45,
            "ATP_target_score": 0.25,
            "antibacterial_score": 0.15,
            "druglikeness_score": 0.15,
        },
    },
    "A": {
        "description": "Binding-emphasis 60/20/10/10",
        "weights": {
            "binding_score": 0.60,
            "ATP_target_score": 0.20,
            "antibacterial_score": 0.10,
            "druglikeness_score": 0.10,
        },
    },
    "B": {
        "description": "ATP-target-emphasis 30/50/10/10",
        "weights": {
            "binding_score": 0.30,
            "ATP_target_score": 0.50,
            "antibacterial_score": 0.10,
            "druglikeness_score": 0.10,
        },
    },
    "C": {
        "description": "Equal weighting 25/25/25/25",
        "weights": {
            "binding_score": 0.25,
            "ATP_target_score": 0.25,
            "antibacterial_score": 0.25,
            "druglikeness_score": 0.25,
        },
    },
    "D": {
        "description": "Balanced binding/ATP/AB/drug 40/25/20/15",
        "weights": {
            "binding_score": 0.40,
            "ATP_target_score": 0.25,
            "antibacterial_score": 0.20,
            "druglikeness_score": 0.15,
        },
    },
}


def _safe_correlation(
    first: pd.Series, second: pd.Series, method: str
) -> float | None:
    valid = pd.DataFrame({"first": first, "second": second}).dropna()
    if len(valid) < 3 or valid["first"].nunique() < 2 or valid["second"].nunique() < 2:
        return None
    if method == "spearman":
        value = spearmanr(valid["first"], valid["second"]).statistic
    elif method == "kendall":
        value = kendalltau(valid["first"], valid["second"]).statistic
    else:
        raise ValueError(f"Unsupported correlation method: {method}")
    return None if np.isnan(value) else float(value)


def _weighted_component_score(
    frame: pd.DataFrame, weights: dict[str, float]
) -> pd.Series:
    validate_weights(weights, "Phase 6A scenario")
    missing = frame[list(weights)].isna().any(axis=1)
    score = sum(frame[column] * float(weight) for column, weight in weights.items())
    score.loc[missing] = np.nan
    return score


class Phase6ARobustness:
    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root.resolve()
        self.input_path = self.project_root / "results" / "final_candidate_ranking.csv"
        self.config_path = self.project_root / "scoring_config.json"
        self.dataset_v1_path = (
            self.project_root / "data" / "dataset_v1.0" / "ATP_Navigator_Dataset_v1.csv"
        )
        self.optional_benchmark_path = (
            self.project_root / "data" / "external" / "curated" / "phase6a_benchmark.csv"
        )
        self.output_dir = self.project_root / "results" / "phase6A"
        self.docs_dir = self.project_root / "docs"

    def load_candidates(self) -> pd.DataFrame:
        frame = pd.read_csv(self.input_path, low_memory=False)
        required = {
            "compound_id",
            "historical_alias",
            "canonical_smiles",
            "final_score",
            "final_rank",
            *COMPONENTS,
        }
        missing = required.difference(frame.columns)
        if missing:
            raise ValueError(f"Phase 5 ranking missing fields: {sorted(missing)}")
        if len(frame) != 17 or frame["compound_id"].nunique() != 17:
            raise ValueError("Phase 6A requires exactly 17 unique preserved internal candidates")
        if frame[COMPONENTS].isna().any().any():
            raise ValueError("A required Phase 5 component score is missing")

        config = json.loads(self.config_path.read_text(encoding="utf-8"))
        registered = {key: float(value) for key, value in config["component_weights"].items()}
        expected = SCENARIOS["default"]["weights"]
        if registered != expected:
            raise ValueError("Phase 5 registered weights differ from the frozen Phase 6A default")

        recomputed = _weighted_component_score(frame, registered)
        maximum_error = float((recomputed - frame["final_score"]).abs().max())
        if maximum_error > 1e-9:
            raise ValueError(f"Phase 5 score formula check failed: max error={maximum_error}")
        return frame.copy()

    def weight_sensitivity(
        self, candidates: pd.DataFrame
    ) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        long_rows: list[pd.DataFrame] = []
        matrix = candidates[["compound_id", "historical_alias"]].copy()
        scenario_ranks: dict[str, pd.Series] = {}

        for scenario_id, specification in SCENARIOS.items():
            weights = specification["weights"]
            scores = _weighted_component_score(candidates, weights)
            ranks = scores.rank(method="min", ascending=False).astype("Int64")
            scenario_ranks[scenario_id] = ranks
            matrix[f"{scenario_id}_score"] = scores
            matrix[f"{scenario_id}_rank"] = ranks

            scenario_frame = candidates[["compound_id", "historical_alias"]].copy()
            scenario_frame.insert(0, "scenario_id", scenario_id)
            scenario_frame.insert(1, "scenario_description", specification["description"])
            for component in COMPONENTS:
                scenario_frame[f"weight_{component}"] = float(weights[component])
            scenario_frame["scenario_score"] = scores
            scenario_frame["scenario_rank"] = ranks
            scenario_frame["default_rank"] = candidates["final_rank"].astype("Int64")
            scenario_frame["rank_shift_vs_default"] = (
                scenario_frame["default_rank"] - scenario_frame["scenario_rank"]
            )
            scenario_frame["is_top3"] = ranks.le(3)
            scenario_frame["is_top5"] = ranks.le(5)
            long_rows.append(scenario_frame)

        sensitivity = pd.concat(long_rows, ignore_index=True)
        matrix["max_rank_shift_across_A_to_D"] = matrix[
            [f"{scenario}_rank" for scenario in "ABCD"]
        ].max(axis=1) - matrix[[f"{scenario}_rank" for scenario in "ABCD"]].min(axis=1)
        matrix = matrix.sort_values(["default_rank", "compound_id"], kind="stable")

        stability_rows: list[dict[str, Any]] = []
        scenario_ids = list(SCENARIOS)
        for row_id in scenario_ids:
            for column_id in scenario_ids:
                first = scenario_ranks[row_id].astype(float)
                second = scenario_ranks[column_id].astype(float)
                stability_rows.append(
                    {
                        "scenario_row": row_id,
                        "scenario_column": column_id,
                        "n_candidates": int(len(candidates)),
                        "spearman_correlation": _safe_correlation(first, second, "spearman"),
                        "kendall_tau": _safe_correlation(first, second, "kendall"),
                    }
                )
        stability = pd.DataFrame(stability_rows)

        consistency = candidates[
            ["compound_id", "historical_alias", "final_rank", "final_score"]
        ].copy()
        sensitivity_only = sensitivity[sensitivity["scenario_id"].isin(list("ABCD"))]
        grouped = sensitivity_only.groupby("compound_id", sort=False)
        summary = grouped.agg(
            top3_count_4_scenarios=("is_top3", "sum"),
            top5_count_4_scenarios=("is_top5", "sum"),
            mean_rank_4_scenarios=("scenario_rank", "mean"),
            median_rank_4_scenarios=("scenario_rank", "median"),
            best_rank_4_scenarios=("scenario_rank", "min"),
            worst_rank_4_scenarios=("scenario_rank", "max"),
        ).reset_index()
        consistency = consistency.merge(summary, on="compound_id", how="left", validate="one_to_one")
        consistency["top3_frequency"] = consistency["top3_count_4_scenarios"] / 4.0
        consistency["top5_frequency"] = consistency["top5_count_4_scenarios"] / 4.0
        consistency["rank_range_4_scenarios"] = (
            consistency["worst_rank_4_scenarios"] - consistency["best_rank_4_scenarios"]
        )
        consistency = consistency.sort_values(
            ["top3_count_4_scenarios", "top5_count_4_scenarios", "mean_rank_4_scenarios"],
            ascending=[False, False, True],
            kind="stable",
        )
        return sensitivity, matrix, stability, consistency

    def decision_ablation(self, candidates: pd.DataFrame) -> pd.DataFrame:
        default_weights = SCENARIOS["default"]["weights"]
        binding_atp_total = default_weights["binding_score"] + default_weights["ATP_target_score"]
        ablations = {
            "A_binding_only": {
                "description": "Binding score only",
                "weights": {
                    "binding_score": 1.0,
                    "ATP_target_score": 0.0,
                    "antibacterial_score": 0.0,
                    "druglikeness_score": 0.0,
                },
            },
            "B_binding_plus_ATP": {
                "description": "Binding and ATP target; default relative weights renormalized",
                "weights": {
                    "binding_score": default_weights["binding_score"] / binding_atp_total,
                    "ATP_target_score": default_weights["ATP_target_score"] / binding_atp_total,
                    "antibacterial_score": 0.0,
                    "druglikeness_score": 0.0,
                },
            },
            "C_full_ATP_Navigator": {
                "description": "Full registered Phase 5 decision formula",
                "weights": default_weights,
            },
        }

        full_rank = candidates["final_rank"].astype("Int64")
        rows: list[pd.DataFrame] = []
        for ablation_id, specification in ablations.items():
            weights = specification["weights"]
            score = _weighted_component_score(candidates, weights)
            rank = score.rank(method="min", ascending=False).astype("Int64")
            frame = candidates[["compound_id", "historical_alias"]].copy()
            frame.insert(0, "ablation_id", ablation_id)
            frame.insert(1, "description", specification["description"])
            for component in COMPONENTS:
                frame[f"weight_{component}"] = float(weights[component])
            frame["ablation_score"] = score
            frame["ablation_rank"] = rank
            frame["full_rank"] = full_rank
            frame["rank_shift_vs_full"] = full_rank - rank
            frame["is_top3"] = rank.le(3)
            frame["is_top5"] = rank.le(5)
            frame["spearman_vs_full"] = _safe_correlation(rank.astype(float), full_rank.astype(float), "spearman")
            frame["kendall_tau_vs_full"] = _safe_correlation(rank.astype(float), full_rank.astype(float), "kendall")
            rows.append(frame)
        return pd.concat(rows, ignore_index=True)

    def external_benchmark(self, candidates: pd.DataFrame) -> pd.DataFrame:
        dataset = pd.read_csv(self.dataset_v1_path, low_memory=False)
        external = dataset[dataset["dataset_layer"].ne("layer_3_internal_atp_navigator")].copy()
        candidate_smiles = set(candidates["canonical_smiles"].dropna().astype(str))
        rows: list[dict[str, Any]] = []

        layer_specs = [
            (
                "dataset_v1_layer1_exact_structure_overlap",
                "layer_1_general_antibacterial",
                "General antibacterial experimental knowledge",
            ),
            (
                "dataset_v1_layer2_exact_structure_overlap",
                "layer_2_atp_synthase_specific",
                "ATP synthase-specific experimental knowledge",
            ),
        ]
        for benchmark_id, layer, evidence_scope in layer_specs:
            subset = external[external["dataset_layer"].eq(layer)].copy()
            matched = subset[subset["canonical_smiles"].astype(str).isin(candidate_smiles)]
            matched_compounds = int(matched["canonical_smiles"].nunique())
            evaluable = matched_compounds >= 3
            rows.append(
                {
                    "benchmark_id": benchmark_id,
                    "source_file": str(self.dataset_v1_path.relative_to(self.project_root)).replace("\\", "/"),
                    "evidence_scope": evidence_scope,
                    "validation_only": True,
                    "internal_candidate_count": int(len(candidates)),
                    "external_record_count": int(len(subset)),
                    "unique_external_structures": int(subset["canonical_smiles"].dropna().nunique()),
                    "matched_internal_compounds": matched_compounds,
                    "evaluable": evaluable,
                    "status": "not_evaluable" if not evaluable else "requires_endpoint_stratification",
                    "spearman_correlation": None,
                    "kendall_tau": None,
                    "reason": (
                        "No exact canonical-SMILES overlap with the 17 internal candidates; "
                        "external compounds cannot serve as direct labels for these candidates."
                        if matched_compounds == 0
                        else "Matches must be stratified by target, organism, activity type, unit, and assay before metrics."
                    ),
                }
            )

        if not self.optional_benchmark_path.exists():
            rows.append(
                {
                    "benchmark_id": "optional_curated_independent_benchmark",
                    "source_file": str(self.optional_benchmark_path.relative_to(self.project_root)).replace("\\", "/"),
                    "evidence_scope": "Future independent candidate-level validation set",
                    "validation_only": True,
                    "internal_candidate_count": int(len(candidates)),
                    "external_record_count": 0,
                    "unique_external_structures": 0,
                    "matched_internal_compounds": 0,
                    "evaluable": False,
                    "status": "not_available",
                    "spearman_correlation": None,
                    "kendall_tau": None,
                    "reason": (
                        "No curated benchmark file is present. Expected fields: compound_id or canonical_smiles, "
                        "endpoint, activity_value, unit, direction, evidence_type, source, reference."
                    ),
                }
            )
        else:
            rows.append(self._evaluate_optional_benchmark(candidates))
        return pd.DataFrame(rows)

    def _evaluate_optional_benchmark(self, candidates: pd.DataFrame) -> dict[str, Any]:
        benchmark = pd.read_csv(self.optional_benchmark_path, low_memory=False)
        required = {
            "canonical_smiles",
            "endpoint",
            "activity_value",
            "unit",
            "direction",
            "evidence_type",
            "source",
            "reference",
        }
        missing = required.difference(benchmark.columns)
        if missing:
            reason = f"Curated benchmark schema invalid; missing fields: {sorted(missing)}"
            matched = pd.DataFrame()
            status = "invalid_schema"
            spearman = None
            kendall = None
        else:
            merged = candidates[["compound_id", "canonical_smiles", "final_score"]].merge(
                benchmark,
                on="canonical_smiles",
                how="inner",
                validate="one_to_many",
            )
            eligible = merged[
                merged["evidence_type"].astype(str).str.lower().eq("experimental")
                & merged["activity_value"].notna()
            ].copy()
            strata = eligible[["endpoint", "unit", "direction"]].drop_duplicates()
            if len(strata) != 1:
                reason = "Benchmark records are absent or mix endpoint/unit/direction strata."
                matched = eligible
                status = "not_evaluable"
                spearman = None
                kendall = None
            else:
                matched = eligible.drop_duplicates("compound_id")
                if len(matched) < 3:
                    reason = "Fewer than 3 independently measured internal candidates are matched."
                    status = "not_evaluable"
                    spearman = None
                    kendall = None
                else:
                    direction = str(strata.iloc[0]["direction"])
                    activity = pd.to_numeric(matched["activity_value"], errors="coerce")
                    reference_score = -activity if direction == "lower_is_better" else activity
                    spearman = _safe_correlation(matched["final_score"], reference_score, "spearman")
                    kendall = _safe_correlation(matched["final_score"], reference_score, "kendall")
                    reason = "Computed on a validation-only experimental stratum; no training performed."
                    status = "evaluated"

        return {
            "benchmark_id": "optional_curated_independent_benchmark",
            "source_file": str(self.optional_benchmark_path.relative_to(self.project_root)).replace("\\", "/"),
            "evidence_scope": "Independent candidate-level experimental validation",
            "validation_only": True,
            "internal_candidate_count": int(len(candidates)),
            "external_record_count": int(len(benchmark)),
            "unique_external_structures": int(benchmark.get("canonical_smiles", pd.Series(dtype=str)).nunique()),
            "matched_internal_compounds": int(matched.get("compound_id", pd.Series(dtype=str)).nunique()),
            "evaluable": status == "evaluated",
            "status": status,
            "spearman_correlation": spearman,
            "kendall_tau": kendall,
            "reason": reason,
        }

    @staticmethod
    def _top_ids(frame: pd.DataFrame, scenario: str, k: int) -> list[str]:
        subset = frame[(frame["scenario_id"] == scenario) & (frame["scenario_rank"] <= k)]
        return subset.sort_values("scenario_rank")["compound_id"].tolist()

    def benchmark_report(self, benchmark: pd.DataFrame) -> str:
        layer1 = benchmark.loc[
            benchmark["benchmark_id"].eq("dataset_v1_layer1_exact_structure_overlap")
        ].iloc[0]
        layer2 = benchmark.loc[
            benchmark["benchmark_id"].eq("dataset_v1_layer2_exact_structure_overlap")
        ].iloc[0]
        return f"""# ATP-Navigator Phase 6A External Benchmark Report

生成模块：`{MODULE_VERSION}`

## 结论

当前没有可对17个内部候选实施独立外部性能评价的数据。`benchmark_results.csv`中的相关性字段保持空值，不把内部Docking、静态MM/GBSA、Model v3预测、外部prior或Phase 5 Final Score冒充外部实验真值。

## 已执行检查

| 外部知识层 | 外部记录数 | 与17候选精确canonical SMILES重叠 | 状态 |
|---|---:|---:|---|
| Layer 1 general antibacterial | {int(layer1['external_record_count'])} | {int(layer1['matched_internal_compounds'])} | `{layer1['status']}` |
| Layer 2 ATP synthase specific | {int(layer2['external_record_count'])} | {int(layer2['matched_internal_compounds'])} | `{layer2['status']}` |

Dataset v1.0的Layer 3是本项目内部计算证据，已明确排除在external benchmark之外。Layer 1和Layer 2与内部候选均没有精确结构重叠，因此不能直接给内部候选赋MIC或IC50标签。

## 可复用验证接口

模块会检查可选文件`data/external/curated/phase6a_benchmark.csv`。最低字段为：

- `canonical_smiles`
- `endpoint`
- `activity_value`
- `unit`
- `direction`
- `evidence_type`
- `source`
- `reference`

只有`evidence_type=experimental`、与内部候选精确结构匹配、且endpoint/unit/direction构成单一可比stratum时才计算相关性；至少需要3个匹配候选。该文件永远只用于验证，不并入训练。

## 当前限制

- 无内部候选MIC、ATP enzyme inhibition或实验毒性结果；
- 无独立前瞻性候选集；
- 公开外部化合物与17候选不重叠；
- 因而当前benchmark状态是data availability audit，不是外部性能证明。
"""

    def robustness_report(
        self,
        sensitivity: pd.DataFrame,
        stability: pd.DataFrame,
        consistency: pd.DataFrame,
        ablation: pd.DataFrame,
        benchmark: pd.DataFrame,
    ) -> str:
        off_diagonal = stability[stability["scenario_row"].ne(stability["scenario_column"])]
        min_spearman = float(off_diagonal["spearman_correlation"].min())
        min_kendall = float(off_diagonal["kendall_tau"].min())
        top3_all = consistency[consistency["top3_count_4_scenarios"].eq(4)]
        top5_all = consistency[consistency["top5_count_4_scenarios"].eq(4)]
        top3_all_names = ", ".join(
            f"{row.compound_id} ({row.historical_alias})" for row in top3_all.itertuples()
        ) or "none"
        top5_all_names = ", ".join(
            f"{row.compound_id} ({row.historical_alias})" for row in top5_all.itertuples()
        ) or "none"
        top_rows: list[str] = []
        for scenario in SCENARIOS:
            top = sensitivity[
                (sensitivity["scenario_id"] == scenario) & (sensitivity["scenario_rank"] == 1)
            ].iloc[0]
            top_rows.append(
                f"| {scenario} | {top['compound_id']} | {top['historical_alias']} | {float(top['scenario_score']):.4f} |"
            )

        ablation_summary: list[str] = []
        for ablation_id, group in ablation.groupby("ablation_id", sort=False):
            first = group.sort_values("ablation_rank").iloc[0]
            ablation_summary.append(
                f"| {ablation_id} | {first['compound_id']} | {int(first['ablation_rank'])} | "
                f"{float(first['spearman_vs_full']):.4f} | {float(first['kendall_tau_vs_full']):.4f} |"
            )

        return f"""# ATP-Navigator Phase 6A Robustness Report

生成模块：`{MODULE_VERSION}`

分析范围：Phase 5已有17个内部候选和四个计算决策分量。没有训练监督模型，没有修改Model v0-v3，没有加入实验标签。

## 1. 权重敏感性

共比较Phase 5默认权重和A-D四个预设场景。分数仍是当前17候选批次内的决策分数，不是活性或成功概率。

| 场景 | Top 1 compound | 历史别名 | 场景分数 |
|---|---|---|---:|
{chr(10).join(top_rows)}

不同场景两两比较的最低Spearman为{min_spearman:.4f}，最低Kendall tau为{min_kendall:.4f}。完整矩阵见`results/phase6A/ranking_stability_matrix.csv`。

## 2. Top候选一致性

- 在A-D四个扰动场景中始终进入Top 3的候选数：{len(top3_all)}；候选：{top3_all_names}；
- 在A-D四个扰动场景中始终进入Top 5的候选数：{len(top5_all)}；候选：{top5_all_names}；
- 每个候选的Top 3/Top 5出现次数、平均排名和排名范围见`top_candidate_consistency.csv`。

## 3. Decision Engine消融

“Binding + ATP”保留默认二者相对比例并归一化为0.642857/0.357143；完整方案使用45/25/15/15。

| 消融 | Top 1 compound | Top rank | Spearman vs full | Kendall vs full |
|---|---|---:|---:|---:|
{chr(10).join(ablation_summary)}

消融结果用于观察多目标分量对候选顺序的影响，不代表任何方案具有更高实验准确率。

## 4. External benchmark

当前可评价benchmark数量：{int(benchmark['evaluable'].fillna(False).astype(bool).sum())}。Dataset v1.0外部Layer 1/2与17候选没有精确canonical SMILES重叠，因此未计算外部性能指标。详见`results/phase6A/benchmark_report.md`。

## 5. 产物与可复现性

- `results/phase6A/weight_sensitivity_results.csv`
- `results/phase6A/ranking_matrix.csv`
- `results/phase6A/ranking_stability_matrix.csv`
- `results/phase6A/top_candidate_consistency.csv`
- `results/phase6A/decision_ablation.csv`
- `results/phase6A/benchmark_results.csv`
- `results/phase6A/benchmark_report.md`

输入文件SHA-256：

- `results/final_candidate_ranking.csv`: `{sha256(self.input_path)}`
- `scoring_config.json`: `{sha256(self.config_path)}`
- `data/dataset_v1.0/ATP_Navigator_Dataset_v1.csv`: `{sha256(self.dataset_v1_path)}`
"""

    def limitation_report(self, benchmark: pd.DataFrame) -> str:
        return f"""# ATP-Navigator Phase 6A Limitation Report

## 已确认限制

1. 样本只有17个，且来自经过筛选的候选集合，不代表完整化学空间。
2. 权重敏感性只能说明规则在指定A-D场景内的排名稳定程度，不能证明真实活性预测有效。
3. 四个决策分量并非相互独立：Binding含Model v3、Docking和静态MM/GBSA；Model v3本身以静态MM/GBSA为计算标签。
4. ATP target和antibacterial分量含外部模型prior，存在organism、assay和chemical-domain shift。
5. Drug-likeness包含启发式描述符阈值和预测ADMET，不是实验安全性。
6. Final Score采用批内rank percentile，候选集合变化时分数和排名可能改变，不能直接跨批次比较。
7. 当前没有MIC、ATP enzyme inhibition、实验毒性或独立前瞻性结果；所有这些实验状态仍是`unknown`。
8. Dataset v1.0外部Layer 1/2与17个内部候选精确结构重叠为0；当前external benchmark可评价条目为{int(benchmark['evaluable'].fillna(False).astype(bool).sum())}。
9. 消融或权重场景的Top候选变化只能解释决策规则依赖性，不能选择“实验上最佳”的公式。
10. Phase 6A没有形成Model v4，也没有产生新的监督性能指标。

## 禁止性解释

- 不得把场景稳定性写成实验验证；
- 不得把外部prior写成内部候选MIC/IC50；
- 不得把Phase 5/6A分数回流成监督标签；
- 不得用当前17候选内的高相关性声称跨项目泛化；
- 不得将`not_evaluable` benchmark描述为通过验证。

## 解除限制所需数据

- 对预先冻结候选和评价方案取得同协议MIC及ATP enzyme inhibition实验；
- 记录毒性、选择性、溶解度和稳定性实验；
- 建立独立、未参与权重选择的前瞻性候选集；
- 在单一endpoint、organism/strain、unit和assay条件下积累至少可计算相关性的候选级外部/实验匹配数据。
"""

    def run(self) -> dict[str, Any]:
        candidates = self.load_candidates()
        sensitivity, matrix, stability, consistency = self.weight_sensitivity(candidates)
        ablation = self.decision_ablation(candidates)
        benchmark = self.external_benchmark(candidates)

        outputs = {
            "weight_sensitivity_results.csv": sensitivity,
            "ranking_matrix.csv": matrix,
            "ranking_stability_matrix.csv": stability,
            "top_candidate_consistency.csv": consistency,
            "decision_ablation.csv": ablation,
            "benchmark_results.csv": benchmark,
        }
        for name, frame in outputs.items():
            atomic_to_csv(frame, self.output_dir / name)
        atomic_write_text(self.output_dir / "benchmark_report.md", self.benchmark_report(benchmark))
        atomic_write_text(
            self.docs_dir / "Phase6A_Robustness_Report.md",
            self.robustness_report(sensitivity, stability, consistency, ablation, benchmark),
        )
        atomic_write_text(
            self.docs_dir / "Phase6A_Limitation_Report.md",
            self.limitation_report(benchmark),
        )

        scenario_top1 = {
            scenario: self._top_ids(sensitivity, scenario, 1)[0] for scenario in SCENARIOS
        }
        return {
            "module_version": MODULE_VERSION,
            "candidate_count": int(len(candidates)),
            "scenario_top1": scenario_top1,
            "external_benchmark_evaluable_count": int(
                benchmark["evaluable"].fillna(False).astype(bool).sum()
            ),
            "output_directory": str(self.output_dir),
        }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--project-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="ATP-Navigator repository root",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    payload = Phase6ARobustness(args.project_root).run()
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
