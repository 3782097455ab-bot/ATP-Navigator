"""Integrated ATP-Navigator post-screening candidate decision workflow.

Input -> structure processing -> feature extraction -> preserved model tools ->
multi-objective decision -> robustness-aware ranking -> explanation -> self-audit.

No historical model is trained or modified. Missing experimental results remain
``unknown`` and missing computational components make the final score unknown.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import kendalltau

from decision_engine import rank_percentile, rule_pass, validate_weights, weighted_score
from explanation_generator import generate_report
from input_processor import CandidateInputProcessor, UNKNOWN, atomic_csv, sha256
from research_decision_agent import competition_ranks_descending, constrained_dirichlet
from workflow_evaluator import evaluate_workflow, write_evaluation


PIPELINE_VERSION = "ATP-Navigator_Phase10_IntegratedWorkflow_v1.0"


def json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, float) and not np.isfinite(value):
        return None
    return value


def atomic_json(payload: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", delete=False, dir=path.parent, suffix=".tmp"
    ) as handle:
        temporary = Path(handle.name)
        json.dump(json_safe(payload), handle, ensure_ascii=False, indent=2, allow_nan=False)
    temporary.replace(path)


def file_hash_or_unknown(path: Path) -> str:
    return sha256(path) if path.exists() else UNKNOWN


class NavigatorPipeline:
    def __init__(
        self,
        project_root: str | Path,
        profiles_path: str | Path | None = None,
    ) -> None:
        self.project_root = Path(project_root).resolve()
        self.profiles_path = Path(
            profiles_path
            or self.project_root / "configs" / "research_profiles.json"
        ).resolve()
        self.config = json.loads(self.profiles_path.read_text(encoding="utf-8"))
        self._validate_config()
        self.processor = CandidateInputProcessor(self.project_root)

    def _validate_config(self) -> None:
        components = list(self.config["component_columns"])
        for profile, values in self.config["profiles"].items():
            validate_weights(values["weights"], profile)
            if set(values["weights"]) != set(components):
                raise ValueError(f"Profile {profile} does not define all decision components")
        if self.config["default_profile"] not in self.config["profiles"]:
            raise ValueError("Default research profile is not defined")
        for label in ["binding_subweights", "ATP_subweights", "drug_subweights"]:
            validate_weights(self.config[label], label)

    def _risk(self, admet_sum: pd.Series) -> pd.Series:
        numeric = pd.to_numeric(admet_sum, errors="coerce")
        bands = self.config["predicted_risk_bands"]
        return pd.Series(
            np.select(
                [
                    numeric.isna(),
                    numeric.le(float(bands["lower_predicted_risk_max"])),
                    numeric.le(float(bands["moderate_predicted_risk_max"])),
                ],
                [UNKNOWN, "lower_predicted_risk", "moderate_predicted_risk"],
                default="higher_predicted_risk",
            ),
            index=admet_sum.index,
        )

    def _score_components(self, frame: pd.DataFrame) -> pd.DataFrame:
        result = frame.copy()
        required_numeric = {
            "model_score",
            "docking_score",
            "mmgbsa_score",
            "similarity_to_known_inhibitor",
            "prior_task_b_pa_atp_ic50_log10_ug_ml",
            "prior_task_b_mtb_atp_ic50_log10_nm",
            "prior_task_a_ab_mic_log10_ug_ml",
            "admet_endpoint_sum",
            *self.config["descriptor_rules"],
        }
        for column in required_numeric:
            if column not in result:
                result[column] = np.nan
        result["model_percentile"] = rank_percentile(result["model_score"], "lower_is_better")
        result["docking_percentile"] = rank_percentile(
            result["docking_score"], "lower_is_better"
        )
        result["mmgbsa_percentile"] = rank_percentile(
            result["mmgbsa_score"], "lower_is_better"
        )
        result["binding_score"] = weighted_score(
            result, self.config["binding_subweights"]
        )

        result["similarity_percentile"] = rank_percentile(
            result["similarity_to_known_inhibitor"], "higher_is_better"
        )
        result["PA_ATP_prior_percentile"] = rank_percentile(
            result["prior_task_b_pa_atp_ic50_log10_ug_ml"], "lower_is_better"
        )
        result["Mtb_ATP_prior_percentile"] = rank_percentile(
            result["prior_task_b_mtb_atp_ic50_log10_nm"], "lower_is_better"
        )
        result["ATP_score"] = weighted_score(result, self.config["ATP_subweights"])

        result["AB_MIC_prior_percentile"] = rank_percentile(
            result["prior_task_a_ab_mic_log10_ug_ml"], "lower_is_better"
        )
        result["antibacterial_score"] = result["AB_MIC_prior_percentile"]

        rule_columns: list[str] = []
        for descriptor, rule in self.config["descriptor_rules"].items():
            name = f"rule_pass_{descriptor.removeprefix('desc_')}"
            result[name] = rule_pass(result[descriptor], rule)
            rule_columns.append(name)
        numeric_rules = result[rule_columns].astype("Float64")
        result["descriptor_rules_passed"] = numeric_rules.sum(
            axis=1, min_count=len(rule_columns)
        )
        result["descriptor_rule_score"] = (
            100.0 * result["descriptor_rules_passed"] / len(rule_columns)
        )
        endpoint_count = float(self.config["predicted_risk_bands"]["endpoint_count"])
        result["predicted_ADMET_safety_score"] = (
            100.0
            * (
                1.0
                - pd.to_numeric(result.get("admet_endpoint_sum"), errors="coerce")
                / endpoint_count
            )
        ).clip(0.0, 100.0)
        result["drug_score"] = weighted_score(result, self.config["drug_subweights"])
        result["risk"] = self._risk(result["admet_endpoint_sum"])
        return result

    def _rank(
        self, frame: pd.DataFrame, profile: str
    ) -> tuple[pd.DataFrame, dict[str, Any]]:
        if profile not in self.config["profiles"]:
            raise ValueError(
                f"Unknown research profile {profile}; choose from {sorted(self.config['profiles'])}"
            )
        result = self._score_components(frame)
        weights = self.config["profiles"][profile]["weights"]
        result["final_score"] = weighted_score(result, weights)
        duplicate = result["duplicate_structure_of"].fillna("").str.strip().ne("")
        result.loc[duplicate, "final_score"] = np.nan
        result["central_rank"] = result["final_score"].rank(
            method="min", ascending=False
        ).astype("Int64")

        result["mean_rank"] = np.nan
        result["rank_p05"] = np.nan
        result["rank_p95"] = np.nan
        result["p_top3"] = np.nan
        result["p_top5"] = np.nan
        result["rank"] = pd.Series(pd.NA, index=result.index, dtype="Int64")
        eligible = result["final_score"].notna()
        eligible_frame = result.loc[eligible].copy()
        robustness = self.config["robustness"]
        if len(eligible_frame):
            components = list(self.config["component_columns"])
            sampled_weights = constrained_dirichlet(
                weights,
                components,
                robustness["global_bounds"],
                int(robustness["draws"]),
                float(robustness["concentration"]),
                int(robustness["seed"]),
            )
            values = eligible_frame[components].to_numpy(dtype=float)
            simulated = values @ sampled_weights.T
            ranks = competition_ranks_descending(simulated)
            stats = pd.DataFrame(
                {
                    "mean_rank": ranks.mean(axis=1),
                    "rank_p05": np.quantile(ranks, 0.05, axis=1, method="nearest"),
                    "rank_p95": np.quantile(ranks, 0.95, axis=1, method="nearest"),
                    "p_top3": (ranks <= min(3, len(eligible_frame))).mean(axis=1),
                    "p_top5": (ranks <= min(5, len(eligible_frame))).mean(axis=1),
                },
                index=eligible_frame.index,
            )
            for column in stats:
                result.loc[stats.index, column] = stats[column]
            robust_order = (
                result.loc[eligible, ["mean_rank", "compound_id"]]
                .sort_values(["mean_rank", "compound_id"])
                .assign(rank=lambda x: range(1, len(x) + 1))["rank"]
            )
            result.loc[robust_order.index, "rank"] = robust_order.astype("Int64")

        coverage_fields = [
            "model_score",
            "docking_score",
            "mmgbsa_score",
            "similarity_to_known_inhibitor",
            "prior_task_b_pa_atp_ic50_log10_ug_ml",
            "prior_task_b_mtb_atp_ic50_log10_nm",
            "prior_task_a_ab_mic_log10_ug_ml",
            "admet_endpoint_sum",
            *self.config["descriptor_rules"],
        ]
        result["evidence_coverage"] = result[coverage_fields].notna().mean(axis=1)
        result["decision_confidence"] = np.select(
            [
                result["final_score"].isna(),
                result["model_v3_status"].eq("available")
                & result["evidence_coverage"].eq(1.0),
            ],
            ["insufficient_computational_data", "medium_computational_only"],
            default="low_computational_only",
        )
        result["selected_profile"] = profile
        aliases = result["historical_alias"].fillna("").astype(str).str.strip()
        result["candidate"] = aliases.where(aliases.ne(""), result["compound_id"])
        result["profile_display_name"] = self.config["profiles"][profile]["display_name"]
        result["score_scope"] = "batch_relative_computational_decision_not_probability"
        result["experimental_activity_status"] = UNKNOWN
        result["pipeline_version"] = PIPELINE_VERSION

        leading = [
            "candidate",
            "compound_id",
            "rank",
            "central_rank",
            "model_score",
            "model_used",
            "binding_score",
            "ATP_score",
            "antibacterial_score",
            "drug_score",
            "risk",
            "final_score",
            "mean_rank",
            "rank_p05",
            "rank_p95",
            "p_top3",
            "p_top5",
            "decision_confidence",
            "evidence_coverage",
        ]
        result = result[[*leading, *[c for c in result.columns if c not in leading]]]
        result = result.sort_values(["rank", "compound_id"], na_position="last").reset_index(drop=True)
        rank_summary = {
            "profile": profile,
            "display_name": self.config["profiles"][profile]["display_name"],
            "intended_use": self.config["profiles"][profile]["intended_use"],
            "central_weights": weights,
            "robustness_method": robustness["method"],
            "robustness_draws": int(robustness["draws"]),
            "scored_candidates": int(result["final_score"].notna().sum()),
            "unscored_candidates": int(result["final_score"].isna().sum()),
        }
        return result, rank_summary

    def _compare_profiles(
        self,
        processed: pd.DataFrame,
        selected_profile: str,
        selected_ranking: pd.DataFrame,
        output_dir: Path,
    ) -> dict[str, Any]:
        profile_frames = []
        for profile in self.config["profiles"]:
            ranking = (
                selected_ranking.copy()
                if profile == selected_profile
                else self._rank(processed, profile)[0]
            )
            subset = ranking[
                [
                    "compound_id",
                    "historical_alias",
                    "rank",
                    "central_rank",
                    "final_score",
                    "mean_rank",
                    "p_top3",
                    "p_top5",
                ]
            ].copy()
            subset.insert(0, "profile", profile)
            profile_frames.append(subset)
        comparison = pd.concat(profile_frames, ignore_index=True)
        atomic_csv(comparison, output_dir / "profile_comparison.csv")

        pivot = comparison.pivot(index="compound_id", columns="profile", values="rank")
        stability_rows = []
        profiles = list(self.config["profiles"])
        for left in profiles:
            for right in profiles:
                if left == right:
                    valid = pivot[[left]].dropna()
                    spearman = 1.0 if len(valid) else np.nan
                    kendall = 1.0 if len(valid) else np.nan
                else:
                    valid = pivot[[left, right]].dropna()
                    spearman = valid[left].corr(valid[right], method="spearman")
                    kendall = (
                        kendalltau(valid[left], valid[right]).statistic
                        if len(valid) >= 2
                        else np.nan
                    )
                stability_rows.append(
                    {
                        "profile_a": left,
                        "profile_b": right,
                        "n_candidates": len(valid),
                        "spearman": spearman,
                        "kendall_tau": kendall,
                        "semantics": "decision_profile_rank_stability_not_biological_performance",
                    }
                )
        stability = pd.DataFrame(stability_rows)
        atomic_csv(stability, output_dir / "profile_rank_stability.csv")

        consistency = (
            comparison.assign(
                appears_top3=lambda x: x["rank"].le(3).fillna(False).astype(int),
                appears_top5=lambda x: x["rank"].le(5).fillna(False).astype(int),
            )
            .groupby(["compound_id", "historical_alias"], as_index=False)
            .agg(
                profiles_evaluated=("profile", "count"),
                top3_profile_count=("appears_top3", "sum"),
                top5_profile_count=("appears_top5", "sum"),
                best_rank=("rank", "min"),
                worst_rank=("rank", "max"),
                mean_profile_rank=("rank", "mean"),
            )
            .sort_values(
                ["top3_profile_count", "top5_profile_count", "mean_profile_rank", "compound_id"],
                ascending=[False, False, True, True],
            )
        )
        consistency["interpretation"] = (
            "cross-profile decision consistency; not experimental hit frequency"
        )
        atomic_csv(consistency, output_dir / "top_candidate_consistency.csv")
        leaders = (
            comparison.loc[comparison["rank"].eq(1), ["profile", "historical_alias", "compound_id"]]
            .set_index("profile")
            .to_dict(orient="index")
        )
        return {
            "profile_count": len(profiles),
            "leaders": leaders,
            "minimum_off_diagonal_spearman": float(
                stability.loc[stability["profile_a"].ne(stability["profile_b"]), "spearman"].min()
            ),
        }

    def run(
        self,
        input_path: str | Path,
        profile: str | None = None,
        output_dir: str | Path | None = None,
        report_path: str | Path | None = None,
        deterministic_replay: bool | None = None,
    ) -> dict[str, Any]:
        input_path = Path(input_path).resolve()
        selected_profile = profile or self.config["default_profile"]
        output_dir = Path(output_dir or self.project_root / "results").resolve()
        processed_path = output_dir / "processed_candidate_table.csv"
        ranking_path = output_dir / "final_navigation_report.csv"
        report_path = Path(
            report_path
            or (
                self.project_root / "docs" / "Candidate_Recommendation_Report.md"
                if output_dir == self.project_root / "results"
                else output_dir / "candidate_explanation.md"
            )
        ).resolve()
        audit_dir = (
            self.project_root / "results" / "phase10_workflow"
            if output_dir == self.project_root / "results"
            else output_dir
        )

        before_hashes = dict(self.processor.model_hashes)
        processed = self.processor.process(input_path, processed_path)
        ranking, rank_summary = self._rank(processed, selected_profile)
        atomic_csv(ranking, ranking_path)
        profile_analysis = self._compare_profiles(
            processed, selected_profile, ranking, audit_dir
        )
        generate_report(ranking, selected_profile, report_path, input_path.name)
        after_hashes = {
            key: file_hash_or_unknown(path)
            for key, path in {
                "model_v2a": self.project_root / "models/model_v2/model_v2_a_structure_only.joblib",
                "model_v3": self.project_root / "models/model_v3/model.joblib",
                **{
                    output: self.project_root / "models/model_v2" / filename
                    for output, filename in {
                        "prior_task_a_ab_mic_log10_ug_ml": "a_ab_mic_ugml.joblib",
                        "prior_task_b_pa_atp_ic50_log10_ug_ml": "b_pa_atp_ic50_ugml_2024.joblib",
                        "prior_task_b_mtb_atp_ic50_log10_nm": "b_mtb_atp_ic50_nm.joblib",
                        "prior_task_b_ab_atp_ic50_log10_ng_ml": "b_ab_atp_ic50_ngml_2025.joblib",
                    }.items()
                },
            }.items()
        }
        unchanged = before_hashes == after_hashes
        if not unchanged:
            raise RuntimeError("A preserved model file changed during the workflow run")
        evaluation = evaluate_workflow(
            processed, ranking, unchanged, deterministic_replay=deterministic_replay
        )
        write_evaluation(evaluation, audit_dir)

        trace = {
            "pipeline_version": PIPELINE_VERSION,
            "steps": [
                "validate_input_schema",
                "standardize_SMILES_and_scaffold",
                "calculate_RDKit_descriptors_and_Morgan1024",
                "calculate_direct_ATP_reference_similarity",
                "call_preserved_external_prior_models",
                "gate_Model_v3_or_use_declared_Model_v2A_fallback",
                "compute_four_decision_components",
                "apply_research_profile",
                "evaluate_weight_robustness",
                "compare_all_research_profiles",
                "generate_candidate_explanations",
                "self_audit_workflow_integrity",
            ],
            "input": str(input_path),
            "input_sha256": sha256(input_path),
            "profile": rank_summary,
            "profile_analysis": profile_analysis,
            "candidate_count": len(ranking),
            "model_change": "none",
            "supervised_training": False,
            "experimental_values_imputed": 0,
            "biological_performance_evaluated": False,
            "workflow_readiness": evaluation["workflow_readiness"],
            "outputs": {
                "processed_candidates": str(processed_path),
                "ranking": str(ranking_path),
                "explanations": str(report_path),
                "workflow_validation": str(audit_dir / "workflow_validation.json"),
                "profile_comparison": str(audit_dir / "profile_comparison.csv"),
                "profile_rank_stability": str(audit_dir / "profile_rank_stability.csv"),
                "top_candidate_consistency": str(audit_dir / "top_candidate_consistency.csv"),
            },
            "output_hashes": {
                "processed_candidates": sha256(processed_path),
                "ranking": sha256(ranking_path),
                "explanations": sha256(report_path),
            },
            "preserved_model_hashes": after_hashes,
        }
        atomic_json(trace, audit_dir / "pipeline_trace.json")
        return trace


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--profile", default=None)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    pipeline = NavigatorPipeline(args.project_root)
    trace = pipeline.run(args.input, args.profile, args.output_dir)
    print(json.dumps(trace, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
