"""ATP-Navigator Phase 9 researcher-in-the-loop decision agent.

The agent orchestrates preserved ATP-Navigator evidence and model outputs. It
does not train a model, create biological labels, or modify Model v0-v4-alpha.
Its advanced decision layer consists of preference-conditioned stochastic
multi-criteria ranking, Pareto analysis, contrastive explanations, and a
budget-aware next-experiment acquisition proxy.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd


AGENT_VERSION = "ATP-Navigator_Phase9_Collaborative_Decision_Agent_v1.0"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    if isinstance(value, np.generic):
        return json_safe(value.item())
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


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


def validate_weights(weights: dict[str, float], components: list[str], label: str) -> None:
    if set(weights) != set(components):
        raise ValueError(f"{label} weights do not match configured components")
    values = np.asarray([float(weights[column]) for column in components], dtype=float)
    if np.any(values < 0) or not np.isclose(values.sum(), 1.0, atol=1e-10):
        raise ValueError(f"{label} weights must be non-negative and sum to one")


def validate_config(config: dict[str, Any]) -> None:
    if config.get("agent_version") != AGENT_VERSION:
        raise ValueError("Agent source and configuration versions do not match")
    components = list(config["component_columns"])
    for name, profile in config["profiles"].items():
        validate_weights(profile["central_weights"], components, name)
    for component in components:
        lower, upper = config["weight_uncertainty"]["global_bounds"][component]
        if not 0 <= float(lower) < float(upper) <= 1:
            raise ValueError(f"Invalid weight bounds for {component}")


@dataclass(frozen=True)
class IntentResolution:
    selected_profile: str
    source: str
    research_question: str
    matched_keywords: tuple[str, ...]
    requires_human_confirmation: bool


def resolve_intent(
    config: dict[str, Any], explicit_profile: str | None, research_question: str | None
) -> IntentResolution:
    profiles = config["profiles"]
    question = (research_question or "").strip()
    if explicit_profile:
        if explicit_profile not in profiles:
            raise ValueError(f"Unknown profile {explicit_profile}; choose from {sorted(profiles)}")
        return IntentResolution(explicit_profile, "explicit_profile", question, (), False)
    lowered = question.lower()
    matches: dict[str, list[str]] = {}
    for profile, keywords in config["intent_keywords"].items():
        hits = [keyword for keyword in keywords if keyword.lower() in lowered]
        if hits:
            matches[profile] = hits
    if not matches:
        return IntentResolution("balanced", "default_no_keyword_match", question, (), True)
    ordered = sorted(matches.items(), key=lambda item: (-len(item[1]), item[0]))
    winner, keywords = ordered[0]
    tied = len(ordered) > 1 and len(ordered[0][1]) == len(ordered[1][1])
    return IntentResolution(winner, "keyword_inference", question, tuple(keywords), tied or True)


def constrained_dirichlet(
    central: dict[str, float],
    components: list[str],
    bounds: dict[str, list[float]],
    draws: int,
    concentration: float,
    seed: int,
) -> np.ndarray:
    alpha = np.asarray([central[column] for column in components], dtype=float) * concentration
    rng = np.random.default_rng(seed)
    accepted: list[np.ndarray] = []
    accepted_count = 0
    attempts = 0
    while accepted_count < draws and attempts < 100:
        batch_size = max(2048, min(draws * 2, (draws - accepted_count) * 4))
        sample = rng.dirichlet(alpha, size=batch_size)
        mask = np.ones(batch_size, dtype=bool)
        for index, component in enumerate(components):
            lower, upper = map(float, bounds[component])
            mask &= sample[:, index] >= lower
            mask &= sample[:, index] <= upper
        if mask.any():
            kept = sample[mask]
            accepted.append(kept)
            accepted_count += len(kept)
        attempts += 1
    if accepted_count < draws:
        raise RuntimeError(
            f"Could only sample {accepted_count}/{draws} weight vectors within configured bounds"
        )
    return np.vstack(accepted)[:draws]


def competition_ranks_descending(scores: np.ndarray) -> np.ndarray:
    # Scores have shape candidates x simulations. Continuous sampled weights make
    # exact ties extremely rare; deterministic compound order resolves any tie.
    order = np.argsort(-scores, axis=0, kind="mergesort")
    ranks = np.empty_like(order, dtype=np.int16)
    columns = np.arange(scores.shape[1])
    ranks[order, columns] = np.arange(1, scores.shape[0] + 1, dtype=np.int16)[:, None]
    return ranks


def robust_profile(
    frame: pd.DataFrame,
    config: dict[str, Any],
    profile_name: str,
    seed_offset: int,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    components = list(config["component_columns"])
    uncertainty = config["weight_uncertainty"]
    profile = config["profiles"][profile_name]
    weights = constrained_dirichlet(
        profile["central_weights"],
        components,
        uncertainty["global_bounds"],
        int(uncertainty["draws"]),
        float(uncertainty["concentration"]),
        int(uncertainty["seed"]) + seed_offset,
    )
    values = frame[components].to_numpy(dtype=float)
    if not np.isfinite(values).all():
        raise ValueError("All four current computational decision components are required")
    simulated_scores = values @ weights.T
    ranks = competition_ranks_descending(simulated_scores)
    central_vector = np.asarray(
        [profile["central_weights"][column] for column in components], dtype=float
    )
    central_scores = values @ central_vector
    central_ranks = pd.Series(central_scores).rank(method="min", ascending=False).astype(int)
    result = frame[["compound_id", "historical_alias", "scaffold"]].copy()
    result["profile"] = profile_name
    result["central_score"] = central_scores
    result["central_rank"] = central_ranks.to_numpy()
    result["expected_score"] = simulated_scores.mean(axis=1)
    result["mean_rank"] = ranks.mean(axis=1)
    result["median_rank"] = np.median(ranks, axis=1)
    result["rank_p05"] = np.quantile(ranks, 0.05, axis=1, method="nearest")
    result["rank_p95"] = np.quantile(ranks, 0.95, axis=1, method="nearest")
    result["p_top1"] = (ranks <= 1).mean(axis=1)
    result["p_top3"] = (ranks <= 3).mean(axis=1)
    result["p_top5"] = (ranks <= 5).mean(axis=1)
    result["p_bottom5"] = (ranks > len(frame) - 5).mean(axis=1)
    result["robust_order"] = result["mean_rank"].rank(method="min", ascending=True).astype(int)
    result["probability_semantics"] = (
        "conditional_rank_acceptability_under_configured_weight_distribution_not_activity_probability"
    )
    result = result.sort_values(["robust_order", "compound_id"]).reset_index(drop=True)
    weight_summary = pd.DataFrame(
        {
            "profile": profile_name,
            "component": components,
            "central_weight": central_vector,
            "sample_mean": weights.mean(axis=0),
            "sample_sd": weights.std(axis=0, ddof=1),
            "sample_p05": np.quantile(weights, 0.05, axis=0),
            "sample_p95": np.quantile(weights, 0.95, axis=0),
        }
    )
    return result, weight_summary


def pareto_layers(frame: pd.DataFrame, components: list[str]) -> pd.DataFrame:
    values = frame[components].to_numpy(dtype=float)
    remaining = list(range(len(frame)))
    layers = np.zeros(len(frame), dtype=int)
    dominance_count = np.zeros(len(frame), dtype=int)
    for index in range(len(frame)):
        dominance_count[index] = sum(
            bool(np.all(values[other] >= values[index]) and np.any(values[other] > values[index]))
            for other in range(len(frame))
            if other != index
        )
    layer = 1
    while remaining:
        front = []
        for index in remaining:
            dominated_within_remaining = any(
                np.all(values[other] >= values[index]) and np.any(values[other] > values[index])
                for other in remaining
                if other != index
            )
            if not dominated_within_remaining:
                front.append(index)
        if not front:
            raise RuntimeError("Pareto layer computation failed")
        layers[front] = layer
        remaining = [index for index in remaining if index not in set(front)]
        layer += 1
    result = frame[["compound_id", "historical_alias", "scaffold", *components]].copy()
    result["pareto_layer"] = layers
    result["global_dominance_count"] = dominance_count
    result["pareto_optimal"] = result["pareto_layer"].eq(1)
    return result.sort_values(["pareto_layer", "global_dominance_count", "compound_id"])


def model_disagreement(project_root: Path, config: dict[str, Any]) -> pd.DataFrame:
    paths = config["source_files"]
    v3 = pd.read_csv(project_root / paths["model_v3_oof"])
    v4 = pd.read_csv(project_root / paths["model_v4_alpha_oof"])
    v3 = v3[["compound_id", "predicted_rank", "oof_prediction"]].rename(
        columns={"predicted_rank": "model_v3_oof_rank", "oof_prediction": "model_v3_oof_prediction"}
    )
    v4 = v4[["compound_id", "model_v4_alpha_oof_prediction"]].copy()
    v4["model_v4_alpha_oof_rank"] = v4["model_v4_alpha_oof_prediction"].rank(
        method="min", ascending=True
    ).astype(int)
    result = v3.merge(v4, on="compound_id", validate="one_to_one")
    result["absolute_oof_rank_disagreement"] = (
        result["model_v3_oof_rank"] - result["model_v4_alpha_oof_rank"]
    ).abs()
    result["disagreement_semantics"] = (
        "model_version_scaffold_oof_rank_disagreement_not_biological_uncertainty"
    )
    return result.sort_values(["absolute_oof_rank_disagreement", "compound_id"], ascending=[False, True])


def evidence_ledger(project_root: Path, config: dict[str, Any]) -> pd.DataFrame:
    semantics = {
        "phase5_ranking": ("derived_decision", "yes", "Current transparent four-component input"),
        "phase5_config": ("decision_rule", "yes", "Historical Phase 5 formula preserved"),
        "model_v3_oof": ("computational_model_output", "diagnostic", "Current supervised ranking model OOF"),
        "model_v4_alpha_oof": ("computational_model_output", "diagnostic", "Experimental model; did not replace v3"),
        "binding_features": ("computational_evidence", "trace_only", "Sparse MD and binding evidence audit"),
        "development_history": ("provenance_document", "trace_only", "Completed-work history"),
    }
    rows = []
    for key, relative in config["source_files"].items():
        path = project_root / relative
        evidence_type, usage, note = semantics[key]
        rows.append(
            {
                "evidence_id": key,
                "path": relative,
                "exists": path.exists(),
                "sha256": sha256(path) if path.exists() else "",
                "size_bytes": path.stat().st_size if path.exists() else np.nan,
                "evidence_type": evidence_type,
                "agent_usage": usage,
                "experimental_measurement": False,
                "note": note,
            }
        )
    rows.extend(
        [
            {
                "evidence_id": "internal_ATP_enzyme_assay",
                "path": "",
                "exists": False,
                "sha256": "",
                "size_bytes": np.nan,
                "evidence_type": "experimental_activity",
                "agent_usage": "missing_required_for_validation",
                "experimental_measurement": True,
                "note": "unknown; not imputed",
            },
            {
                "evidence_id": "internal_MIC_assay",
                "path": "",
                "exists": False,
                "sha256": "",
                "size_bytes": np.nan,
                "evidence_type": "experimental_activity",
                "agent_usage": "missing_required_for_validation",
                "experimental_measurement": True,
                "note": "unknown; not imputed",
            },
            {
                "evidence_id": "internal_experimental_toxicity",
                "path": "",
                "exists": False,
                "sha256": "",
                "size_bytes": np.nan,
                "evidence_type": "experimental_safety",
                "agent_usage": "missing_required_for_validation",
                "experimental_measurement": True,
                "note": "unknown; not imputed",
            },
        ]
    )
    return pd.DataFrame(rows)


def counterfactuals(
    frame: pd.DataFrame,
    robust: pd.DataFrame,
    config: dict[str, Any],
    profile_name: str,
) -> pd.DataFrame:
    components = list(config["component_columns"])
    weights = config["profiles"][profile_name]["central_weights"]
    merged = frame.merge(
        robust[["compound_id", "central_score", "central_rank", "mean_rank", "p_top5"]],
        on="compound_id",
        validate="one_to_one",
    )
    leader = merged.sort_values(["central_rank", "compound_id"]).iloc[0]
    rows = []
    for row in merged.itertuples(index=False):
        gap = float(leader.central_score - row.central_score)
        feasible = []
        for component in components:
            weight = float(weights[component])
            current = float(getattr(row, component))
            delta = max(0.0, gap + 1e-6) / weight if weight > 0 else np.inf
            if current + delta <= 100.0 + 1e-9:
                feasible.append((delta, component, current + delta))
        if gap <= 1e-9:
            component = "already_profile_leader"
            delta = 0.0
            target = float(row.central_score)
            status = "already_profile_leader"
        elif feasible:
            delta, component, target = min(feasible, key=lambda item: (item[0], item[1]))
            status = "single_component_score_counterfactual_available"
        else:
            component = "multi_component_change_required"
            delta = np.nan
            target = np.nan
            status = "no_single_component_change_within_0_100_can_overtake_leader"
        contributions = {
            name: float(weights[name]) * (float(getattr(leader, name)) - float(getattr(row, name)))
            for name in components
        }
        largest_gap_component = max(contributions, key=contributions.get)
        rows.append(
            {
                "profile": profile_name,
                "compound_id": row.compound_id,
                "historical_alias": row.historical_alias,
                "leader_compound_id": leader.compound_id,
                "leader_historical_alias": leader.historical_alias,
                "central_score_gap_to_leader": max(gap, 0.0),
                "largest_weighted_gap_component": largest_gap_component,
                "minimal_single_component": component,
                "required_component_score_increase": delta,
                "counterfactual_component_target": target,
                "counterfactual_status": status,
                "counterfactual_warning": "normalized decision-score scenario only; not a predicted experimental effect",
            }
        )
    return pd.DataFrame(rows).sort_values(["central_score_gap_to_leader", "compound_id"])


def add_panel_role(selected: dict[str, list[str]], compound_id: str, role: str) -> None:
    selected.setdefault(compound_id, [])
    if role not in selected[compound_id]:
        selected[compound_id].append(role)


def plan_experiments(
    frame: pd.DataFrame,
    robust: pd.DataFrame,
    disagreement: pd.DataFrame,
    config: dict[str, Any],
    budget: int,
) -> pd.DataFrame:
    plan_config = config["experiment_planning"]
    if not int(plan_config["minimum_budget"]) <= budget <= int(plan_config["maximum_budget"]):
        raise ValueError(
            f"Experiment budget must be between {plan_config['minimum_budget']} and {plan_config['maximum_budget']}"
        )
    data = robust.merge(
        frame[["compound_id", "historical_alias", "scaffold", "final_rank", "confidence_score"]],
        on=["compound_id", "historical_alias", "scaffold"],
        validate="one_to_one",
    ).merge(
        disagreement[["compound_id", "absolute_oof_rank_disagreement"]],
        on="compound_id",
        validate="one_to_one",
    )
    n = len(data)
    scaffold_counts = data["scaffold"].value_counts()
    data["rank_interval_width"] = (data["rank_p95"] - data["rank_p05"]) / max(n - 1, 1)
    data["top5_boundary_uncertainty"] = 4.0 * data["p_top5"] * (1.0 - data["p_top5"])
    data["model_version_disagreement"] = data["absolute_oof_rank_disagreement"] / max(n - 1, 1)
    data["scaffold_rarity"] = data["scaffold"].map(lambda value: 1.0 / scaffold_counts[value])
    data["legacy_hit3_evidence"] = data["historical_alias"].eq(
        config["legacy_candidate_alias"]
    ).astype(float)
    proxy_weights = plan_config["information_value_proxy_weights"]
    data["information_value_proxy"] = sum(
        data[column] * float(weight) for column, weight in proxy_weights.items()
    )

    selected: dict[str, list[str]] = {}
    ranked = data.sort_values(["robust_order", "compound_id"])
    add_panel_role(selected, ranked.iloc[0]["compound_id"], "robust_profile_leader")
    stable = data.sort_values(["p_top3", "mean_rank", "compound_id"], ascending=[False, True, True]).iloc[0]
    add_panel_role(selected, stable["compound_id"], "weight_robust_high_priority")
    legacy = data.loc[data["historical_alias"].eq(config["legacy_candidate_alias"])]
    if len(legacy) == 1:
        add_panel_role(selected, legacy.iloc[0]["compound_id"], "legacy_Hit3_MD_and_chemical_characterization_bridge")
    disagreement_top = data.sort_values(
        ["absolute_oof_rank_disagreement", "information_value_proxy", "compound_id"],
        ascending=[False, False, True],
    ).iloc[0]
    add_panel_role(selected, disagreement_top["compound_id"], "model_version_disagreement_probe")
    lower_pool = data.loc[data["robust_order"].ge(math.ceil(2 * n / 3))]
    comparator = lower_pool.sort_values(
        ["information_value_proxy", "compound_id"], ascending=[False, True]
    ).iloc[0]
    add_panel_role(selected, comparator["compound_id"], "lower_priority_comparator_not_assumed_inactive")

    chosen_scaffolds = set(data.loc[data["compound_id"].isin(selected), "scaffold"])
    for row in data.sort_values(
        ["information_value_proxy", "p_top5", "compound_id"], ascending=[False, False, True]
    ).itertuples(index=False):
        if len(selected) >= budget:
            break
        if row.compound_id in selected:
            continue
        role = "information_value_and_scaffold_diversity"
        if row.scaffold in chosen_scaffolds:
            role = "information_value_fill"
        add_panel_role(selected, row.compound_id, role)
        chosen_scaffolds.add(row.scaffold)

    panel = data.loc[data["compound_id"].isin(selected)].copy()
    panel["panel_role"] = panel["compound_id"].map(lambda value: ";".join(selected[value]))
    panel["recommended_primary_assay"] = plan_config["primary_assay"]
    panel["recommended_secondary_assay"] = plan_config["secondary_assay"]
    panel["experimental_result_status"] = "unknown"
    panel["selection_is_activity_claim"] = False
    panel["panel_order"] = panel["panel_role"].str.contains("robust_profile_leader").map(
        {True: 0, False: 1}
    )
    panel = panel.sort_values(
        ["panel_order", "robust_order", "information_value_proxy", "compound_id"],
        ascending=[True, True, False, True],
    ).reset_index(drop=True)
    panel["panel_order"] = np.arange(1, len(panel) + 1)
    return panel[
        [
            "panel_order",
            "compound_id",
            "historical_alias",
            "scaffold",
            "panel_role",
            "robust_order",
            "mean_rank",
            "rank_p05",
            "rank_p95",
            "p_top3",
            "p_top5",
            "absolute_oof_rank_disagreement",
            "information_value_proxy",
            "recommended_primary_assay",
            "recommended_secondary_assay",
            "experimental_result_status",
            "selection_is_activity_claim",
        ]
    ]


def legacy_comparison(
    frame: pd.DataFrame, robust: pd.DataFrame, pareto: pd.DataFrame, config: dict[str, Any]
) -> pd.DataFrame:
    merged = frame.merge(
        robust[["compound_id", "central_rank", "robust_order", "mean_rank", "rank_p05", "rank_p95", "p_top3", "p_top5"]],
        on="compound_id",
        validate="one_to_one",
    ).merge(
        pareto[["compound_id", "pareto_layer", "pareto_optimal"]],
        on="compound_id",
        validate="one_to_one",
    )
    leader = merged.sort_values(["robust_order", "compound_id"]).iloc[0]
    legacy = merged.loc[merged["historical_alias"].eq(config["legacy_candidate_alias"])]
    if len(legacy) != 1:
        raise ValueError("The legacy Hit3 candidate must map to exactly one internal compound")
    legacy = legacy.iloc[0]
    rows = []
    for role, row in [("agent_robust_leader", leader), ("legacy_Hit3", legacy)]:
        item = {
            "role": role,
            "compound_id": row["compound_id"],
            "historical_alias": row["historical_alias"],
            "phase5_rank": int(row["final_rank"]),
            "robust_order": int(row["robust_order"]),
            "mean_rank": float(row["mean_rank"]),
            "rank_p05": float(row["rank_p05"]),
            "rank_p95": float(row["rank_p95"]),
            "p_top3": float(row["p_top3"]),
            "p_top5": float(row["p_top5"]),
            "pareto_layer": int(row["pareto_layer"]),
            "pareto_optimal": bool(row["pareto_optimal"]),
            "historical_evidence": (
                "traditional selection + MD/MMGBSA + NMR/LC-MS chemical characterization"
                if role == "legacy_Hit3"
                else "highest robust priority under selected computational preference distribution"
            ),
            "experimental_ATP_activity": "unknown",
            "experimental_MIC": "unknown",
            "interpretation": (
                "Preserve in the prospective panel; AI disagreement is a validation opportunity, not proof the legacy choice was wrong."
                if role == "legacy_Hit3"
                else "Test prospectively; rank acceptability is not an activity probability."
            ),
        }
        for component in config["component_columns"]:
            item[component] = float(row[component])
        rows.append(item)
    return pd.DataFrame(rows)


def correlation_table(frame: pd.DataFrame, components: list[str]) -> pd.DataFrame:
    correlation = frame[components].corr(method="spearman")
    return correlation.rename_axis("component").reset_index()


def report_text(
    config: dict[str, Any],
    intent: IntentResolution,
    selected_robust: pd.DataFrame,
    pareto: pd.DataFrame,
    panel: pd.DataFrame,
    legacy: pd.DataFrame,
) -> str:
    top = selected_robust.sort_values("robust_order").head(5)
    top_rows = "\n".join(
        f"| {int(row.robust_order)} | {row.historical_alias} | {row.compound_id} | "
        f"{row.mean_rank:.2f} | {int(row.rank_p05)}–{int(row.rank_p95)} | "
        f"{row.p_top3:.3f} | {row.p_top5:.3f} |"
        for row in top.itertuples(index=False)
    )
    panel_rows = "\n".join(
        f"| {int(row.panel_order)} | {row.historical_alias} | {row.panel_role} | "
        f"{row.mean_rank:.2f} | {row.information_value_proxy:.3f} | unknown |"
        for row in panel.itertuples(index=False)
    )
    hit3 = legacy.loc[legacy["role"].eq("legacy_Hit3")].iloc[0]
    leader = legacy.loc[legacy["role"].eq("agent_robust_leader")].iloc[0]
    pareto_count = int(pareto["pareto_optimal"].sum())
    profile = intent.selected_profile
    return f"""# Phase 9 Collaborative Decision Agent Report

日期：2026-08-26  
版本：`{AGENT_VERSION}`  
模型变化：无；Model v0-v4-alpha与Phase 5 Decision Engine均保留

## 1. 系统定位

Phase 9把既有模型、决策分量、稳健性分析和实验规划组织为一个受控的研究者协作Agent。Agent的任务不是替研究者宣称活性，而是将研究意图翻译为可审计的偏好分布，调用现有专业工具，暴露排序不稳定性，比较人工历史选择，并建议在有限预算下最有信息价值的下一批验证。

选择的研究意图配置：`{profile}`。来源：`{intent.source}`。是否需要人工确认：`{str(intent.requires_human_confirmation).lower()}`。

## 2. 前沿方法的项目化实现

- 工具编排：读取冻结的Phase 5分量、Model v3/v4-alpha OOF和证据注册，而不是让语言模型生成化学分数；
- 偏好条件化：四个决策目标不固定为唯一权重，按研究任务选择profile；
- 稳健多目标排序：使用SMAA-inspired受限Dirichlet Monte Carlo，报告rank acceptability；
- Pareto分析：识别不存在单一目标全面更差的候选；当前Pareto第一层有{pareto_count}个候选；
- 反事实解释：回答单个候选主要被哪个分量拉开，以及需要多大归一化分量变化才可能改变顺序；
- 主动验证：用排名区间、Top-5边界不确定性、Model v3/v4分歧、scaffold稀有度和Hit3历史证据建立透明的信息价值代理。

## 3. 当前profile稳健Top 5

| Robust order | Alias | Compound ID | Mean rank | 90% rank interval | P(Top3) | P(Top5) |
|---:|---|---|---:|---:|---:|---:|
{top_rows}

这里的P(Top-k)只表示在已声明权重分布下进入Top-k的频率，不是活性概率、成功概率或置信度校准结果。

## 4. Hit3与Agent结果的正确关系

- Agent稳健首位：{leader['historical_alias']}（{leader['compound_id']}），mean rank={leader['mean_rank']:.2f}；
- 历史Hit3：{hit3['compound_id']}，Phase 5 rank={int(hit3['phase5_rank'])}，robust order={int(hit3['robust_order'])}，90% rank interval={int(hit3['rank_p05'])}–{int(hit3['rank_p95'])}；
- Hit3仍保留原始人工选择、100 ns MD/MMGBSA及NMR/LC-MS化学表征优势，但ATP enzyme、MIC和实验毒性仍为unknown；
- 最有价值的验证不是让AI强行“同意”或“否定”Hit3，而是把Hit3与Agent稳健Top、模型分歧候选和低优先比较候选放进同一冻结实验面板。

## 5. 建议冻结的首轮实验面板

| Order | Candidate | Role | Mean rank | Information-value proxy | Result |
|---:|---|---|---:|---:|---|
{panel_rows}

首要终点应为同一protocol下ATP synthase功能/酶抑制剂量反应；随后再做同菌株MIC。必须包含IN-2阳性、vehicle、适当比较候选及技术/生物重复。面板中较低优先候选只是比较对象，不能预先称为阴性。

## 6. 可信度边界

- 现有17候选的监督标签是静态MM/GBSA，不是真实活性；
- Binding内部存在相关证据重复，Agent单独保留相关性警告；
- ATP和抗菌先验来自外部跨域模型，不能当作内部测量；
- 20,000次权重抽样量化的是决策偏好不确定性，不是模型预测误差的正式概率校准；
- 当前不具备用于可靠conformal calibration的独立实验标签，因此未伪造预测区间；
- 实验结果回填前，Agent只能证明候选决策过程更透明、可追踪和可执行，不能证明命中率已经提高。

## 7. 比赛主张

ATP-Navigator的核心创新应表述为：在传统Schrödinger虚拟筛选之后、合成与生物验证之前，建立研究者意图驱动的证据决策层，把依赖经验的候选取舍转化为可审计的多目标排序、稳健性分析和主动验证计划。项目当前最强证据是完整真实计算链、可运行代码、模型历史对照、结构恢复、决策敏感性与真实的验证接口，而不是未完成的实验命中率。
"""


class ResearchDecisionAgent:
    def __init__(self, project_root: Path, config_path: Path | None = None) -> None:
        self.project_root = project_root.resolve()
        self.config_path = (config_path or self.project_root / "config/decision_agent_v1.json").resolve()
        self.config = json.loads(self.config_path.read_text(encoding="utf-8"))
        validate_config(self.config)

    def load_candidates(self) -> pd.DataFrame:
        relative = self.config["source_files"]["phase5_ranking"]
        frame = pd.read_csv(self.project_root / relative)
        if len(frame) != 17 or frame["compound_id"].nunique() != 17:
            raise ValueError("Phase 9 requires the preserved 17 unique internal candidates")
        components = self.config["component_columns"]
        if frame[components].isna().any().any():
            raise ValueError("Required computational decision components contain missing values")
        if frame["historical_alias"].eq(self.config["legacy_candidate_alias"]).sum() != 1:
            raise ValueError("Legacy Hit3 identity is not unique")
        return frame

    def run(
        self,
        explicit_profile: str | None,
        research_question: str | None,
        budget: int | None,
    ) -> dict[str, Any]:
        results_dir = self.project_root / "results/phase9_decision_agent"
        docs_dir = self.project_root / "docs"
        intent = resolve_intent(self.config, explicit_profile, research_question)
        frame = self.load_candidates()
        components = list(self.config["component_columns"])

        all_robust = []
        weight_summaries = []
        selected_robust = None
        for offset, profile_name in enumerate(self.config["profiles"]):
            robust, weights = robust_profile(frame, self.config, profile_name, offset * 1009)
            all_robust.append(robust)
            weight_summaries.append(weights)
            if profile_name == intent.selected_profile:
                selected_robust = robust
        if selected_robust is None:
            raise RuntimeError("Selected intent profile was not evaluated")

        robust_all = pd.concat(all_robust, ignore_index=True)
        weight_summary = pd.concat(weight_summaries, ignore_index=True)
        pareto = pareto_layers(frame, components)
        disagreement = model_disagreement(self.project_root, self.config)
        counterfactual = counterfactuals(
            frame, selected_robust, self.config, intent.selected_profile
        )
        panel_budget = int(budget or self.config["experiment_planning"]["default_budget"])
        panel = plan_experiments(
            frame, selected_robust, disagreement, self.config, panel_budget
        )
        legacy = legacy_comparison(frame, selected_robust, pareto, self.config)
        ledger = evidence_ledger(self.project_root, self.config)
        correlations = correlation_table(frame, components)

        outputs = {
            "robust_rankings": results_dir / "robust_rankings.csv",
            "weight_distribution_summary": results_dir / "weight_distribution_summary.csv",
            "pareto_analysis": results_dir / "pareto_analysis.csv",
            "model_version_disagreement": results_dir / "model_version_disagreement.csv",
            "counterfactual_explanations": results_dir / "counterfactual_explanations.csv",
            "next_experiment_panel": results_dir / "next_experiment_panel.csv",
            "legacy_hit3_comparison": results_dir / "legacy_hit3_comparison.csv",
            "evidence_ledger": results_dir / "evidence_ledger.csv",
            "component_correlation": results_dir / "component_correlation.csv",
        }
        frames = {
            "robust_rankings": robust_all,
            "weight_distribution_summary": weight_summary,
            "pareto_analysis": pareto,
            "model_version_disagreement": disagreement,
            "counterfactual_explanations": counterfactual,
            "next_experiment_panel": panel,
            "legacy_hit3_comparison": legacy,
            "evidence_ledger": ledger,
            "component_correlation": correlations,
        }
        for key, output in outputs.items():
            atomic_csv(frames[key], output)

        intent_payload = {
            "selected_profile": intent.selected_profile,
            "source": intent.source,
            "research_question": intent.research_question,
            "matched_keywords": list(intent.matched_keywords),
            "requires_human_confirmation": intent.requires_human_confirmation,
            "profile_description": self.config["profiles"][intent.selected_profile]["description"],
            "central_weights": self.config["profiles"][intent.selected_profile]["central_weights"],
            "hard_evidence_rules": self.config["evidence_policy"],
        }
        atomic_json(intent_payload, results_dir / "intent_resolution.json")

        report = report_text(
            self.config, intent, selected_robust, pareto, panel, legacy
        )
        atomic_text(report, docs_dir / "Phase9_Collaborative_Decision_Agent_Report.md")

        trace = {
            "agent_version": AGENT_VERSION,
            "steps": [
                "resolve_research_intent",
                "validate_evidence_and_missing_experiments",
                "evaluate_all_preference_profiles",
                "compute_SMAA_inspired_rank_acceptability",
                "compute_Pareto_layers",
                "compare_Model_v3_and_v4_alpha_scaffold_OOF",
                "generate_contrastive_counterfactuals",
                "plan_budget_aware_prospective_experiment_panel",
                "write_auditable_outputs",
            ],
            "selected_profile": intent.selected_profile,
            "model_change": "none",
            "supervised_training": False,
            "experimental_labels_created": 0,
            "decision_score_used_as_label": False,
            "candidate_count": len(frame),
            "simulation_draws_per_profile": int(self.config["weight_uncertainty"]["draws"]),
            "profile_count": len(self.config["profiles"]),
            "experiment_panel_size": len(panel),
            "output_hashes": {key: sha256(path) for key, path in outputs.items()},
            "report_sha256": sha256(docs_dir / "Phase9_Collaborative_Decision_Agent_Report.md"),
            "config_sha256": sha256(self.config_path),
        }
        atomic_json(trace, results_dir / "agent_trace.json")

        summary = {
            "agent_version": AGENT_VERSION,
            "selected_profile": intent.selected_profile,
            "requires_human_confirmation": intent.requires_human_confirmation,
            "candidate_count": len(frame),
            "pareto_front_size": int(pareto["pareto_optimal"].sum()),
            "robust_leader": selected_robust.sort_values("robust_order").iloc[0][
                "historical_alias"
            ],
            "legacy_candidate": self.config["legacy_candidate_alias"],
            "experiment_panel": panel["historical_alias"].tolist(),
            "model_change": "none",
            "experimental_labels_created": 0,
            "experimental_activity_status": "unknown",
            "result_directory": str(results_dir.relative_to(self.project_root)),
        }
        atomic_json(summary, results_dir / "summary.json")
        return summary


def explain_existing(project_root: Path, compound_id: str, profile: str) -> dict[str, Any]:
    result_path = project_root / "results/phase9_decision_agent/robust_rankings.csv"
    counter_path = project_root / "results/phase9_decision_agent/counterfactual_explanations.csv"
    if not result_path.exists() or not counter_path.exists():
        raise FileNotFoundError("Run the Phase 9 agent before requesting an explanation")
    ranking = pd.read_csv(result_path)
    selected = ranking.loc[
        ranking["compound_id"].eq(compound_id) & ranking["profile"].eq(profile)
    ]
    counter = pd.read_csv(counter_path)
    counter = counter.loc[
        counter["compound_id"].eq(compound_id) & counter["profile"].eq(profile)
    ]
    if len(selected) != 1 or len(counter) != 1:
        raise KeyError(f"No unique Phase 9 explanation for {compound_id} under {profile}")
    row = selected.iloc[0]
    why = counter.iloc[0]
    return {
        "compound_id": compound_id,
        "historical_alias": row["historical_alias"],
        "profile": profile,
        "robust_order": int(row["robust_order"]),
        "mean_rank": float(row["mean_rank"]),
        "rank_interval_90_percent": [int(row["rank_p05"]), int(row["rank_p95"])],
        "rank_acceptability": {
            "top3": float(row["p_top3"]),
            "top5": float(row["p_top5"]),
            "semantics": row["probability_semantics"],
        },
        "contrastive_explanation": {
            "largest_weighted_gap_component": why["largest_weighted_gap_component"],
            "minimal_single_component": why["minimal_single_component"],
            "required_normalized_score_increase": (
                None
                if pd.isna(why["required_component_score_increase"])
                else float(why["required_component_score_increase"])
            ),
            "warning": why["counterfactual_warning"],
        },
        "experimental_ATP_activity": "unknown",
        "experimental_MIC": "unknown",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--config", type=Path)
    subparsers = parser.add_subparsers(dest="command", required=True)
    run_parser = subparsers.add_parser("run")
    run_parser.add_argument("--profile", choices=["balanced", "binding_first", "target_mechanism", "translational_balance"])
    run_parser.add_argument("--research-question")
    run_parser.add_argument("--budget", type=int)
    explain_parser = subparsers.add_parser("explain")
    explain_parser.add_argument("--compound-id", required=True)
    explain_parser.add_argument("--profile", default="balanced")
    args = parser.parse_args()
    project_root = args.project_root.resolve()
    if args.command == "run":
        agent = ResearchDecisionAgent(project_root, args.config)
        payload = agent.run(args.profile, args.research_question, args.budget)
    else:
        payload = explain_existing(project_root, args.compound_id, args.profile)
    print(json.dumps(json_safe(payload), ensure_ascii=False, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
