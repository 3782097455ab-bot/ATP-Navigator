"""ATP-Navigator Phase 5 transparent multi-objective decision engine.

This module does not train or modify Model v0-v3. It combines existing
computational outputs with explicit weights from scoring_config.json. Missing
experimental MIC, ATP-enzyme, and toxicity evidence is always marked unknown.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import tempfile
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from rdkit import Chem


ENGINE_VERSION = "ATP-Navigator_Phase5_Decision_v1.0"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_to_csv(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", newline="", delete=False, dir=path.parent, suffix=".tmp"
    ) as handle:
        temporary = Path(handle.name)
        frame.to_csv(handle, index=False)
    temporary.replace(path)


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", delete=False, dir=path.parent, suffix=".tmp"
    ) as handle:
        temporary = Path(handle.name)
        handle.write(text)
    temporary.replace(path)


def validate_weights(weights: dict[str, float], label: str) -> None:
    total = sum(float(value) for value in weights.values())
    if not math.isclose(total, 1.0, rel_tol=0.0, abs_tol=1e-9):
        raise ValueError(f"{label} weights sum to {total}, expected 1.0")
    if any(float(value) < 0 for value in weights.values()):
        raise ValueError(f"{label} contains a negative weight")


def rank_percentile(values: pd.Series, direction: str) -> pd.Series:
    numeric = pd.to_numeric(values, errors="coerce")
    valid_count = int(numeric.notna().sum())
    output = pd.Series(np.nan, index=values.index, dtype=float)
    if valid_count == 0:
        return output
    if valid_count == 1:
        output.loc[numeric.notna()] = 50.0
        return output
    ranks = numeric.loc[numeric.notna()].rank(method="average", ascending=True)
    if direction == "lower_is_better":
        output.loc[ranks.index] = 100.0 * (valid_count - ranks) / (valid_count - 1)
    elif direction == "higher_is_better":
        output.loc[ranks.index] = 100.0 * (ranks - 1) / (valid_count - 1)
    else:
        raise ValueError(f"Unsupported direction: {direction}")
    return output


def weighted_score(frame: pd.DataFrame, weights: dict[str, float]) -> pd.Series:
    columns = list(weights)
    missing_required = frame[columns].isna().any(axis=1)
    output = sum(frame[column] * float(weight) for column, weight in weights.items())
    output.loc[missing_required] = np.nan
    return output


def rule_pass(values: pd.Series, rule: dict[str, float]) -> pd.Series:
    numeric = pd.to_numeric(values, errors="coerce")
    passed = pd.Series(True, index=values.index, dtype="boolean")
    passed.loc[numeric.isna()] = pd.NA
    if "minimum" in rule:
        passed.loc[numeric.notna()] &= numeric.loc[numeric.notna()].ge(float(rule["minimum"]))
    if "maximum" in rule:
        passed.loc[numeric.notna()] &= numeric.loc[numeric.notna()].le(float(rule["maximum"]))
    return passed


class DecisionEngine:
    def __init__(self, project_root: Path, config_path: Path | None = None) -> None:
        self.project_root = project_root.resolve()
        self.config_path = (config_path or self.project_root / "scoring_config.json").resolve()
        self.config = json.loads(self.config_path.read_text(encoding="utf-8"))
        if self.config.get("scoring_version") != ENGINE_VERSION:
            raise ValueError("Decision engine and scoring config versions do not match")
        validate_weights(self.config["component_weights"], "final")
        validate_weights(self.config["binding_score"]["subweights"], "binding")
        validate_weights(self.config["ATP_target_score"]["subweights"], "ATP target")
        validate_weights(self.config["antibacterial_score"]["subweights"], "antibacterial")
        validate_weights(self.config["druglikeness_score"]["subweights"], "druglikeness")
        validate_weights(self.config["confidence"]["weights"], "confidence")
        self._ranking: pd.DataFrame | None = None

    def _path(self, key: str) -> Path:
        return self.project_root / self.config["source_files"][key]

    def load_inputs(self) -> pd.DataFrame:
        samples = pd.read_csv(self._path("internal_candidates_and_binding"), low_memory=False)
        model_v3 = pd.read_csv(self._path("model_v3_prediction"), low_memory=False)
        priors = pd.read_csv(self._path("external_knowledge_priors"), low_memory=False)
        chemical = pd.read_csv(self._path("chemical_similarity"), low_memory=False)
        admet = pd.read_csv(self._path("predicted_admet"), low_memory=False)

        if len(samples) != 17:
            raise ValueError(f"Expected 17 preserved internal candidates, found {len(samples)}")
        if samples["compound_id"].duplicated().any():
            raise ValueError("Internal candidate IDs are not unique")
        expected = set(samples["compound_id"])
        sources = {
            "Model v3": set(model_v3["compound_id"]),
            "external priors": set(priors["compound_id"]),
            "chemical similarity": set(chemical["compound_id"]),
            "ADMET": set(admet["canonical_id"]),
        }
        for label, observed in sources.items():
            missing = expected.difference(observed)
            if missing:
                raise ValueError(f"{label} is missing internal IDs: {sorted(missing)}")

        base_columns = [
            "compound_id",
            "historical_alias",
            "canonical_smiles",
            "scaffold",
            "mapping_confidence",
            "desc_mol_wt",
            "desc_logp",
            "desc_tpsa",
            "desc_hbd",
            "desc_hba",
            "desc_rotatable_bonds",
            "glide_docking_score",
            "label_score",
        ]
        frame = samples[base_columns].copy()
        frame = frame.merge(
            model_v3[
                [
                    "compound_id",
                    "candidate_ranking_score_lower_is_better",
                    "candidate_priority_rank",
                ]
            ],
            on="compound_id",
            how="left",
            validate="one_to_one",
        )
        prior_columns = [column for column in priors.columns if column.startswith("prior_task_")]
        frame = frame.merge(
            priors[["compound_id", *prior_columns]],
            on="compound_id",
            how="left",
            validate="one_to_one",
        )
        frame = frame.merge(
            chemical[
                [
                    "compound_id",
                    "similarity_to_known_inhibitor",
                    "nearest_known_inhibitor_id",
                    "nearest_reference_source",
                ]
            ],
            on="compound_id",
            how="left",
            validate="one_to_one",
        )
        frame = frame.merge(
            admet[["canonical_id", "admet_endpoint_sum", "source_file"]].rename(
                columns={"canonical_id": "compound_id", "source_file": "admet_source_file"}
            ),
            on="compound_id",
            how="left",
            validate="one_to_one",
        )
        return frame

    def score(self) -> pd.DataFrame:
        frame = self.load_inputs()

        frame["model_v3_percentile"] = rank_percentile(
            frame["candidate_ranking_score_lower_is_better"], "lower_is_better"
        )
        frame["docking_percentile"] = rank_percentile(
            frame["glide_docking_score"], "lower_is_better"
        )
        frame["static_mmgbsa_percentile"] = rank_percentile(
            frame["label_score"], "lower_is_better"
        )
        frame["binding_score"] = weighted_score(
            frame, self.config["binding_score"]["subweights"]
        )

        frame["direct_ATP_similarity_percentile"] = rank_percentile(
            frame["similarity_to_known_inhibitor"], "higher_is_better"
        )
        frame["PA_ATP_IC50_prior_percentile"] = rank_percentile(
            frame["prior_task_b_pa_atp_ic50_log10_ug_ml"], "lower_is_better"
        )
        frame["Mtb_ATP_IC50_prior_percentile"] = rank_percentile(
            frame["prior_task_b_mtb_atp_ic50_log10_nm"], "lower_is_better"
        )
        frame["AB_ATP_IC50_prior_percentile"] = rank_percentile(
            frame["prior_task_b_ab_atp_ic50_log10_ng_ml"], "lower_is_better"
        )
        frame["ATP_target_score"] = weighted_score(
            frame, self.config["ATP_target_score"]["subweights"]
        )

        frame["AB_whole_cell_MIC_prior_percentile"] = rank_percentile(
            frame["prior_task_a_ab_mic_log10_ug_ml"], "lower_is_better"
        )
        frame["antibacterial_score"] = weighted_score(
            frame, self.config["antibacterial_score"]["subweights"]
        )

        rule_columns: list[str] = []
        for descriptor, rule in self.config["druglikeness_score"]["descriptor_rules"].items():
            column = f"rule_pass_{descriptor.removeprefix('desc_')}"
            frame[column] = rule_pass(frame[descriptor], rule)
            rule_columns.append(column)
        rule_numeric = frame[rule_columns].astype("Float64")
        frame["descriptor_rules_passed"] = rule_numeric.sum(axis=1, min_count=len(rule_columns))
        frame["descriptor_rules_total"] = len(rule_columns)
        frame["descriptor_rule_score"] = 100.0 * frame["descriptor_rules_passed"] / len(rule_columns)
        endpoint_count = float(self.config["druglikeness_score"]["admet_risk_endpoint_count"])
        frame["predicted_ADMET_safety_score"] = (
            100.0 * (1.0 - pd.to_numeric(frame["admet_endpoint_sum"], errors="coerce") / endpoint_count)
        ).clip(lower=0.0, upper=100.0)
        frame["druglikeness_score"] = weighted_score(
            frame, self.config["druglikeness_score"]["subweights"]
        )

        frame["final_score"] = weighted_score(frame, self.config["component_weights"])
        frame["final_rank"] = frame["final_score"].rank(method="min", ascending=False).astype("Int64")

        identity = frame["mapping_confidence"].eq("confirmed").astype(float)
        binding_coverage = frame[
            ["candidate_ranking_score_lower_is_better", "glide_docking_score", "label_score"]
        ].notna().all(axis=1).astype(float)
        atp_coverage = frame[
            [
                "similarity_to_known_inhibitor",
                "prior_task_b_pa_atp_ic50_log10_ug_ml",
                "prior_task_b_mtb_atp_ic50_log10_nm",
            ]
        ].notna().all(axis=1).astype(float)
        antibacterial_coverage = frame["prior_task_a_ab_mic_log10_ug_ml"].notna().astype(float)
        druglikeness_coverage = frame[[*self.config["druglikeness_score"]["descriptor_rules"], "admet_endpoint_sum"]].notna().all(axis=1).astype(float)
        confidence_inputs = {
            "identity_confirmed": identity,
            "binding_input_coverage": binding_coverage,
            "ATP_input_coverage": atp_coverage,
            "antibacterial_input_coverage": antibacterial_coverage,
            "druglikeness_input_coverage": druglikeness_coverage,
            "experimental_validation": pd.Series(
                float(self.config["confidence"]["current_experimental_validation"]),
                index=frame.index,
            ),
        }
        confidence_weights = self.config["confidence"]["weights"]
        frame["confidence_score"] = 100.0 * sum(
            confidence_inputs[key] * float(weight) for key, weight in confidence_weights.items()
        )
        high = float(self.config["confidence"]["thresholds"]["high"])
        medium = float(self.config["confidence"]["thresholds"]["medium"])
        frame["confidence"] = np.select(
            [
                frame["final_score"].isna(),
                frame["confidence_score"].ge(high),
                frame["confidence_score"].ge(medium),
            ],
            ["insufficient_computational_data", "high", "medium_computational_only"],
            default="low_computational_only",
        )

        unknown = self.config["missing_data_policy"]["unknown_literal"]
        frame["experimental_MIC_status"] = unknown
        frame["experimental_ATP_enzyme_status"] = unknown
        frame["experimental_toxicity_status"] = unknown
        frame["score_scope"] = "relative_to_current_17_candidate_batch_not_probability"
        frame["explanation_summary"] = frame.apply(
            lambda row: (
                f"binding={row['binding_score']:.1f}; ATP-computational={row['ATP_target_score']:.1f}; "
                f"antibacterial-prior={row['antibacterial_score']:.1f}; "
                f"druglikeness-computational={row['druglikeness_score']:.1f}; experiments=unknown"
            )
            if pd.notna(row["final_score"])
            else "required computational evidence missing; final score unknown",
            axis=1,
        )

        rename = {
            "candidate_ranking_score_lower_is_better": "model_v3_prediction_score",
            "glide_docking_score": "docking_score",
            "label_score": "static_mmgbsa_score",
        }
        frame = frame.rename(columns=rename)
        leading = [
            "compound_id",
            "historical_alias",
            "final_rank",
            "binding_score",
            "ATP_target_score",
            "antibacterial_score",
            "druglikeness_score",
            "final_score",
            "confidence",
            "confidence_score",
        ]
        remaining = [column for column in frame.columns if column not in leading]
        frame = frame[leading + remaining].sort_values(
            ["final_score", "compound_id"], ascending=[False, True], na_position="last"
        )
        self._ranking = frame.reset_index(drop=True)
        return self._ranking.copy()

    def candidate_payload(self, compound_id: str) -> dict[str, Any]:
        ranking = self._ranking if self._ranking is not None else self.score()
        selected = ranking.loc[ranking["compound_id"].eq(compound_id)]
        if len(selected) != 1:
            raise KeyError(f"Unknown existing compound_id: {compound_id}")
        row = selected.iloc[0]
        return {
            "compound_id": row["compound_id"],
            "score": None if pd.isna(row["final_score"]) else round(float(row["final_score"]), 4),
            "confidence": row["confidence"],
            "explanation": row["explanation_summary"],
            "evidence_status": {
                "MIC_experiment": row["experimental_MIC_status"],
                "ATP_enzyme_experiment": row["experimental_ATP_enzyme_status"],
                "toxicity_experiment": row["experimental_toxicity_status"],
            },
        }

    def prepare_smiles_payload(self, smiles: str) -> dict[str, Any]:
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            raise ValueError("RDKit could not parse the supplied SMILES")
        canonical = Chem.MolToSmiles(mol, canonical=True, isomericSmiles=True)
        request_id = "ATP-REQUEST-" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:12].upper()
        return {
            "compound_id": request_id,
            "canonical_smiles": canonical,
            "score": None,
            "confidence": "unknown",
            "explanation": (
                "A new SMILES requires upstream Docking, Model v3-compatible features, external-prior "
                "predictions, and ADMET computation before the transparent decision formula can run."
            ),
            "status": "requires_upstream_computational_evidence",
            "missing_experimental_evidence": {
                "MIC": "unknown",
                "ATP_enzyme": "unknown",
                "toxicity": "unknown",
            },
        }

    def write_outputs(self) -> pd.DataFrame:
        ranking = self.score()
        atomic_to_csv(ranking, self.project_root / "results" / "final_candidate_ranking.csv")
        atomic_write_text(
            self.project_root / "docs" / "Decision_Engine_Report.md",
            decision_report(self, ranking),
        )
        atomic_write_text(
            self.project_root / "docs" / "Candidate_Explanation_Report.md",
            candidate_report(self, ranking),
        )
        return ranking


def decision_report(engine: DecisionEngine, ranking: pd.DataFrame) -> str:
    config = engine.config
    top = ranking.head(5)
    top_rows = [
        f"| {int(row.final_rank)} | {row.compound_id} | {row.final_score:.2f} | "
        f"{row.binding_score:.2f} | {row.ATP_target_score:.2f} | "
        f"{row.antibacterial_score:.2f} | {row.druglikeness_score:.2f} | {row.confidence} |"
        for row in top.itertuples(index=False)
    ]
    source_rows = []
    for name, relative in config["source_files"].items():
        source = engine.project_root / relative
        source_rows.append(f"| `{name}` | `{relative}` | `{sha256(source)}` |")
    example = json.dumps(
        engine.candidate_payload(top.iloc[0]["compound_id"]),
        ensure_ascii=False,
        indent=2,
    )
    smiles_example = json.dumps(
        engine.prepare_smiles_payload("CCO"), ensure_ascii=False, indent=2
    )
    return f"""# ATP-Navigator Decision Engine Report

版本：{config['scoring_version']}

状态：代码已运行并生成当前 17 候选的综合排序；没有训练或修改 Model v0–v3。

## 1. 目标与边界

Decision Engine 将已有计算证据转换为透明的多目标候选排序。`final_score` 是当前 17 候选批次内的相对决策分数，不是成功概率、活性概率或实验结论。

内部 MIC、ATP 酶抑制和实验毒性数据当前均不存在，输出中统一标记为 `unknown`，没有进行填补。

## 2. 最终公式

```text
{config['final_formula']}
```

所有分量先转换为 0–100、higher-is-better 的批次内 rank percentile，然后再加权。原始 lower-is-better 字段在标准化时反向，因此最终公式不再使用隐藏的负号。

### Binding Score

```text
{config['binding_score']['formula']}
```

Model v3 prediction 与静态 MM/GBSA 高度相关，这三项是相关的计算证据，不是三个独立实验。权重是人工透明决策规则，不是从 17 个样本中优化得到。

### ATP Target Score

```text
{config['ATP_target_score']['formula']}
```

AB ATP IC50 prior 保留在结果中供审计，但权重为 0，因为该外部子任务只有 10 个化合物、3 个 scaffold，且 Model v2 scaffold OOF Spearman 为负。PA 与 Mtb prior 也属于跨体系计算先验，不是内部候选 ATP 酶实验。

### Antibacterial Score

```text
{config['antibacterial_score']['formula']}
```

该分量来自外部 AB whole-cell MIC 模型预测。它不证明 ATP 作用机制，也不是对当前候选完成的 MIC 测定。

### Drug-likeness Score

```text
{config['druglikeness_score']['formula']}
```

descriptor rule score 是 6 条公开阈值规则的通过比例；ADMET safety score 使用 27 个预测风险端点总和。二者都是启发式/预测证据，不是实验安全性。

## 3. 缺失数据策略

- 任一必需计算分量缺失：`final_score` 保持 unknown，不重新归一化剩余权重；
- 实验数据缺失：状态写为 `unknown`；
- 禁止以外部模型预测或零值填充实验 MIC、ATP enzyme 或 toxicity；
- confidence 最高 40% 权重来自实验验证。当前实验验证为 0，因此完整计算记录也只能达到 `medium_computational_only`。

## 4. 当前 Top 5

| Rank | Compound | Final | Binding | ATP target | Antibacterial | Drug-likeness | Confidence |
|---:|---|---:|---:|---:|---:|---:|---|
{chr(10).join(top_rows)}

该表是决策排序，不用于报告新的预测性能。Phase 5 没有新的监督标签，因此没有 Spearman/RMSE/NDCG 性能增量声明。

## 5. 输入追溯

| 输入 | 文件 | SHA-256 |
|---|---|---|
{chr(10).join(source_rows)}

完整公式、子权重、方向、阈值和缺失策略位于 `scoring_config.json`。

## 6. 软件调用接口准备

现有候选接口：

```json
{example}
```

对应 Python 调用：`DecisionEngine(project_root).candidate_payload(compound_id)`。

新 SMILES 接口已经定义，但当前不会在缺少 Docking、外部先验和 ADMET 时虚构分数：

```json
{smiles_example}
```

对应 Python 调用：`DecisionEngine(project_root).prepare_smiles_payload(smiles)`。未来软件层需要先调用特征提取、Docking/评分和外部 prior 模型，再进入本决策公式。

## 7. 命令行入口

- 生成排序与两份报告：`.venv/Scripts/python.exe src/decision_engine.py run`
- 查询已有候选 JSON：`.venv/Scripts/python.exe src/decision_engine.py explain --compound-id <ID>`
- 准备新 SMILES 请求：`.venv/Scripts/python.exe src/decision_engine.py prepare-smiles --smiles <SMILES>`

## 8. 限制

- 评分权重是可审计的项目决策规则，尚未由前瞻性实验优化；
- 分位分数依赖当前候选批次，不能跨批次直接比较；
- Binding 内部证据相关，存在重复强调计算结合证据的风险；
- ATP 与抗菌分量来自外部模型和结构相似性，存在 domain shift；
- 当前没有真实实验闭环，不能把 final score 描述为发现新药的成功概率。
"""


def candidate_report(engine: DecisionEngine, ranking: pd.DataFrame) -> str:
    count = int(engine.config["top_candidate_explanations"])
    sections: list[str] = []
    for row in ranking.head(count).itertuples(index=False):
        sections.append(
            f"""## Rank {int(row.final_rank)} — {row.compound_id} ({row.historical_alias})

综合分数：{row.final_score:.2f}；置信度：`{row.confidence}` ({row.confidence_score:.1f}/100)。该置信度只表示计算证据覆盖，实验验证贡献为 0。

### 结构贡献

- MW {row.desc_mol_wt:.2f}，LogP {row.desc_logp:.2f}，TPSA {row.desc_tpsa:.2f}，HBD {row.desc_hbd:.0f}，HBA {row.desc_hba:.0f}，Rotatable bonds {row.desc_rotatable_bonds:.0f}；
- 通过 {int(row.descriptor_rules_passed)}/{int(row.descriptor_rules_total)} 条 descriptor rules；
- 与外部直接 ATP assay 参考结构的最大 Morgan-Tanimoto 相似度为 {row.similarity_to_known_inhibitor:.3f}，最近参考 ID 为 `{row.nearest_known_inhibitor_id}`；该参考来源尚未逐条内部复核。

### 结合贡献

- Binding score：{row.binding_score:.2f}；
- Model v3 计算预测：{row.model_v3_prediction_score:.3f}；Docking score：{row.docking_score:.3f}；静态 MM/GBSA：{row.static_mmgbsa_score:.3f}；三者均为计算结果；
- Model v3 与静态 MM/GBSA 相关，不能把两者当作相互独立的实验验证。

### ATP 相关证据

- ATP target score：{row.ATP_target_score:.2f}；
- PA ATP IC50 prior（log10 ug/mL）：{row.prior_task_b_pa_atp_ic50_log10_ug_ml:.3f}；Mtb ATP IC50 prior（log10 nM）：{row.prior_task_b_mtb_atp_ic50_log10_nm:.3f}；
- AB ATP prior 保留值 {row.prior_task_b_ab_atp_ic50_log10_ng_ml:.3f}，但因外部子任务不稳定，在配置中权重为 0；
- 当前候选没有已完成的 ATP 酶抑制实验，状态为 `unknown`。

### 成药性评价

- Drug-likeness score：{row.druglikeness_score:.2f}；预测 ADMET risk endpoint sum：{row.admet_endpoint_sum:.0f}/27；
- Antibacterial score：{row.antibacterial_score:.2f}，来源是外部 AB whole-cell MIC 模型 prior，不是当前候选的实验 MIC。

### 当前未知风险

- MIC 实验：`unknown`；ATP enzyme 实验：`unknown`；实验毒性：`unknown`；
- 未知溶解度、稳定性、渗透/外排影响、选择性和重复实验误差不能由当前 final score 排除；
- 该推荐仅用于决定后续计算复核和实验优先级。
"""
        )
    body = "\n".join(sections).rstrip()
    return f"""# ATP-Navigator Candidate Explanation Report

生成范围：Decision Engine 当前 Top {count} 候选。

解释只使用已有结构、Docking、静态 MM/GBSA、Model v3、外部知识 prior 和预测 ADMET。没有把未完成的 MIC、ATP enzyme 或 toxicity 实验写成结果。

{body}
"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--project-root", type=Path, default=Path(__file__).resolve().parents[1]
    )
    parser.add_argument("--config", type=Path, default=None)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("run")
    explain = subparsers.add_parser("explain")
    explain.add_argument("--compound-id", required=True)
    prepare = subparsers.add_parser("prepare-smiles")
    prepare.add_argument("--smiles", required=True)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    engine = DecisionEngine(args.project_root, args.config)
    if args.command == "run":
        ranking = engine.write_outputs()
        print(
            json.dumps(
                {
                    "engine_version": ENGINE_VERSION,
                    "candidate_count": len(ranking),
                    "output": "results/final_candidate_ranking.csv",
                    "top_compound": ranking.iloc[0]["compound_id"],
                    "top_score": round(float(ranking.iloc[0]["final_score"]), 4),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    elif args.command == "explain":
        print(
            json.dumps(
                engine.candidate_payload(args.compound_id),
                ensure_ascii=False,
                indent=2,
            )
        )
    elif args.command == "prepare-smiles":
        print(
            json.dumps(
                engine.prepare_smiles_payload(args.smiles),
                ensure_ascii=False,
                indent=2,
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
