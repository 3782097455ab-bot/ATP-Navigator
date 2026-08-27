"""Phase 15 budget-aware evidence acquisition engine.

All quantities are deterministic heuristics over existing computational
evidence. They are not biological activity probabilities, economic value, or
new training labels. No historical model is loaded or modified.
"""
from __future__ import annotations

import hashlib
import json
import math
import tempfile
from collections import Counter
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .gnina_adapter import certify


def _csv(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8-sig", newline="", delete=False,
                                     dir=path.parent, suffix=".tmp") as handle:
        frame.to_csv(handle, index=False)
        temporary = Path(handle.name)
    temporary.replace(path)


def _json(value: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False,
                                     dir=path.parent, suffix=".tmp") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, allow_nan=False)
        temporary = Path(handle.name)
    temporary.replace(path)


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _strength(rank: pd.Series, n: int) -> pd.Series:
    return 1.0 - (rank.astype(float) - 1.0) / max(n - 1, 1)


def _percentile_utility(values: pd.Series, lower_better: bool = False) -> pd.Series:
    numeric = pd.to_numeric(values, errors="coerce")
    return numeric.rank(pct=True, ascending=not lower_better, na_option="bottom").clip(0, 1)


def _rank_entropy(vina_rank: float, glide_rank: float, n: int) -> float:
    a = min(9, int((vina_rank - 1) * 10 / n))
    b = min(9, int((glide_rank - 1) * 10 / n))
    return 0.0 if a == b else 1.0


class AcquisitionEngine:
    def __init__(self, project: str | Path):
        self.project = Path(project).resolve()
        self.config_path = self.project / "configs/acquisition_phase15.json"
        self.config = json.loads(self.config_path.read_text(encoding="utf-8"))
        self.output = self.project / "results/phase15"

    def _inputs(self) -> tuple[pd.DataFrame, dict]:
        paths = {
            "ranking": self.project / "results/phase14/full_library_vina_ranking.csv",
            "disagreement": self.project / "results/phase14/glide_vina_protocol_disagreement.csv",
            "completeness": self.project / "results/phase14/evidence_completeness_matrix.csv",
            "docking": self.project / "data/docking_features_v0_2.csv",
            "identity": self.project / "results/phase14_1/internal17_identity_audit.csv",
            "phase8": self.project / "results/phase8_data_acquisition/mmgbsa_acquisition_queue_v2.csv",
        }
        rank = pd.read_csv(paths["ranking"])
        disagreement = pd.read_csv(paths["disagreement"])
        complete = pd.read_csv(paths["completeness"])
        docking = pd.read_csv(paths["docking"], low_memory=False)
        # Select the historical pose row whose Glide score equals the frozen
        # candidate-level score; ties resolve by pose_index, never by Vina.
        docking["glide_docking_score"] = pd.to_numeric(docking["glide_docking_score"], errors="coerce")
        docking = docking.sort_values(["canonical_id", "glide_docking_score", "pose_index"]).drop_duplicates("canonical_id")
        qp = [column for column in docking if column.startswith("quickprop_")]
        docking["quickprop_completeness"] = docking[qp].notna().mean(axis=1)
        dock_cols = ["canonical_id", "glide_emodel", "glide_ligand_efficiency", "quickprop_completeness"]
        frame = rank.merge(disagreement.drop(columns=["vina_affinity", "scaffold"], errors="ignore"), on="canonical_id", how="inner")
        frame = frame.merge(complete[["canonical_id", "structure_valid", "ligand_prepared", "vina_available", "pose_qc_pass"]], on="canonical_id", how="left")
        frame = frame.merge(docking[dock_cols], on="canonical_id", how="left")
        if len(frame) != 1633 or frame["canonical_id"].duplicated().any():
            raise ValueError("Phase 15 requires exactly 1633 unique matched Glide/Vina candidates")
        return frame, {name: _file_hash(path) for name, path in paths.items()}

    def build_features(self) -> tuple[pd.DataFrame, dict]:
        frame, hashes = self._inputs()
        n = len(frame)
        frame["vina_rank"] = frame["global_rank"].astype(int)
        frame["glide_rank"] = frame["glide_rank"].astype(int)
        frame["rank_delta"] = frame["vina_rank"] - frame["glide_rank"]
        frame["protocol_disagreement"] = frame["rank_delta"].abs() / (n - 1)
        frame["protocol_uncertainty"] = frame["protocol_disagreement"]
        frame["vina_strength"] = _strength(frame["vina_rank"], n)
        frame["glide_strength"] = _strength(frame["glide_rank"], n)
        frame["rank_consensus"] = (frame["vina_rank"] + frame["glide_rank"]) / 2.0
        frame["consensus_strength"] = (frame["vina_strength"] + frame["glide_strength"]) / 2.0
        frame["normalized_rank_variance"] = ((frame["vina_rank"] - frame["glide_rank"]) / (n - 1)) ** 2 / 4.0
        frame["rank_entropy"] = [_rank_entropy(v, g, n) for v, g in zip(frame["vina_rank"], frame["glide_rank"])]
        frame["protocol_disagreement_score"] = frame["protocol_disagreement"]

        scaffold_counts = frame["scaffold"].fillna("").value_counts()
        cluster_counts = frame["chemical_space_cluster"].value_counts()
        max_scaffold = max(scaffold_counts.max(), 2)
        max_cluster = max(cluster_counts.max(), 2)
        frame["scaffold_size"] = frame["scaffold"].fillna("").map(scaffold_counts).astype(int)
        frame["cluster_size"] = frame["chemical_space_cluster"].map(cluster_counts).astype(int)
        frame["scaffold_novelty"] = 1 - np.log(frame["scaffold_size"]) / math.log(max_scaffold)
        frame["cluster_novelty"] = 1 - np.log(frame["cluster_size"]) / math.log(max_cluster)
        frame["chemical_space_uncertainty"] = (frame["scaffold_novelty"] + frame["cluster_novelty"]) / 2

        observed = (
            frame["structure_valid"].astype(bool).astype(float)
            + frame["ligand_prepared"].astype(bool).astype(float)
            + frame["vina_available"].astype(bool).astype(float)
            + frame["pose_qc_pass"].astype(bool).astype(float)
            + 1.0  # historical Glide is present for the matched subset
            + frame["quickprop_completeness"].fillna(0)
        )
        # Seven declared evidence groups: structure, preparation, Glide,
        # QuickProp, Vina, pose QC, and candidate-level MM/GBSA.
        frame["evidence_completeness"] = observed / 7.0
        frame["evidence_uncertainty"] = 1.0 - frame["evidence_completeness"]
        frame["mmgbsa_available"] = False
        frame["independent_admet_available"] = False

        ligand_utility = _percentile_utility(frame["glide_ligand_efficiency"], lower_better=True)
        heavy_atom = frame["canonical_smiles"].str.count(r"[A-Z][a-z]?").clip(lower=1)
        size_utility = (1 - (heavy_atom - 25).abs() / 30).clip(0, 1)
        objective_matrix = np.vstack([frame["consensus_strength"], ligand_utility, size_utility]).T
        frame["objective_uncertainty"] = np.std(objective_matrix, axis=1) / 0.4714045208
        frame["objective_uncertainty"] = frame["objective_uncertainty"].clip(0, 1)
        frame["model_uncertainty"] = np.nan
        frame["model_disagreement_if_available"] = np.nan
        frame["model_uncertainty_status"] = "not_available_no_comparable_full_library_model_outputs"

        boundaries = self.config["rank_boundaries"]
        distance = frame["rank_consensus"].map(lambda rank: min(abs(rank - boundary) for boundary in boundaries))
        frame["distance_to_decision_boundary"] = distance
        window = float(self.config["boundary_window"])
        frame["rank_boundary_proximity"] = (1 - distance / window).clip(0, 1)
        available_uncertainty = frame[["protocol_uncertainty", "objective_uncertainty", "evidence_uncertainty", "chemical_space_uncertainty"]]
        frame["combined_available_uncertainty"] = available_uncertainty.mean(axis=1)
        frame["uncertainty_available_components"] = 4
        labels = available_uncertainty.idxmax(axis=1).str.replace("_uncertainty", "", regex=False)
        frame["uncertainty_dominant_source"] = labels

        frame["recommended_next_evidence"] = "Prime MM/GBSA under one reviewed frozen protocol"
        frame["acquisition_cost"] = float(self.config["estimated_cost_units"]["prime_mmgbsa"])
        potential_change = (frame["rank_boundary_proximity"] + frame["protocol_uncertainty"]) / 2
        evidence_importance = (frame["evidence_uncertainty"] + frame["consensus_strength"]) / 2
        frame["voi_proxy"] = potential_change * frame["combined_available_uncertainty"] * evidence_importance / frame["acquisition_cost"]
        frame["voi_potential_decision_change"] = potential_change
        frame["voi_uncertainty"] = frame["combined_available_uncertainty"]
        frame["voi_evidence_importance"] = evidence_importance

        w = self.config["hybrid_weights"]
        frame["hybrid_score"] = (
            w["exploitation"] * frame["consensus_strength"]
            + w["protocol_disagreement"] * frame["protocol_uncertainty"]
            + w["evidence_uncertainty"] * frame["evidence_uncertainty"]
            + w["scaffold_diversity"] * frame["scaffold_novelty"]
            + w["chemical_space_coverage"] * frame["cluster_novelty"]
            + w["rank_boundary_proximity"] * frame["rank_boundary_proximity"]
        ) / frame["acquisition_cost"]
        frame["hybrid_rank"] = frame["hybrid_score"].rank(method="first", ascending=False).astype(int)
        return frame, hashes

    def _strategy_orders(self, frame: pd.DataFrame) -> dict[str, list[str]]:
        seed = int(self.config["random_seed"])
        random_order = frame.sample(frac=1, random_state=seed)["canonical_id"].tolist()
        def order(column: str, ascending: bool = False) -> list[str]:
            return frame.sort_values([column, "canonical_id"], ascending=[ascending, True])["canonical_id"].tolist()
        diversity_score = 0.50 * frame["consensus_strength"] + 0.30 * frame["scaffold_novelty"] + 0.20 * frame["cluster_novelty"]
        temporary = frame.assign(diversity_score=diversity_score)
        return {
            "random": random_order,
            "vina_top": order("vina_strength"),
            "glide_top": order("glide_strength"),
            "consensus_top": order("consensus_strength"),
            "diversity_aware": temporary.sort_values(["diversity_score", "canonical_id"], ascending=[False, True])["canonical_id"].tolist(),
            "disagreement_aware": order("protocol_uncertainty"),
            "uncertainty_aware": order("combined_available_uncertainty"),
            "rank_boundary": order("rank_boundary_proximity"),
            "evidence_gap": order("evidence_uncertainty"),
            "ATP_Navigator_hybrid": order("hybrid_score"),
        }

    def _select_panel(self, frame: pd.DataFrame, orders: dict[str, list[str]]) -> pd.DataFrame:
        selected: list[tuple[str, str, str]] = []
        used: set[str] = set()
        by_id = frame.set_index("canonical_id")

        def take(candidates, count: int, category: str, reason: str) -> None:
            if sum(item[1] == category for item in selected) >= count:
                return
            for candidate in candidates:
                if candidate in used:
                    continue
                selected.append((candidate, category, reason))
                used.add(candidate)
                if sum(item[1] == category for item in selected) >= count:
                    break

        strong = frame.loc[(frame["vina_rank"] <= 250) & (frame["glide_rank"] <= 250)].sort_values(["rank_consensus", "canonical_id"])["canonical_id"]
        take(strong, 15, "multi_protocol_strong", "both docking protocols rank the candidate in the upper region")
        take(orders["consensus_top"], 15, "multi_protocol_strong", "best remaining multi-protocol consensus")
        take(orders["disagreement_aware"], 15, "extreme_disagreement", "large Glide/Vina rank disagreement could change the decision")
        boundary_uncertain = frame.assign(
            boundary_uncertainty_score=0.65 * frame["rank_boundary_proximity"]
            + 0.35 * frame["combined_available_uncertainty"]
        ).sort_values(["boundary_uncertainty_score", "canonical_id"], ascending=[False, True])["canonical_id"]
        take(boundary_uncertain, 10, "rank_boundary_uncertain",
             "near a configured selection boundary or high-uncertainty after earlier class de-duplication")
        diversity = frame.sort_values(["scaffold_novelty", "cluster_novelty", "consensus_strength", "canonical_id"], ascending=[False, False, False, True])["canonical_id"]
        take(diversity, 10, "scaffold_diverse", "rare scaffold/cluster improves chemical-space coverage")
        medium = frame.assign(mid_distance=(frame["rank_consensus"] - (len(frame) + 1) / 2).abs()).sort_values(["mid_distance", "protocol_uncertainty", "canonical_id"])["canonical_id"]
        take(medium, 5, "medium_controls", "middle-ranked low-disagreement computational control")

        exact_bridges: list[str] = []
        identity = pd.read_csv(self.project / "results/phase14_1/internal17_identity_audit.csv")
        exact = identity.loc[identity["exact_match"].astype(bool), "matched_htvs_id"].dropna().astype(str)
        for value in exact:
            exact_bridges.extend(item for item in value.split(";") if item)
        take(exact_bridges, 1, "historical_bridge_interpretable",
             "exact structure bridge to a frozen internal historical candidate")
        phase8 = pd.read_csv(self.project / "results/phase8_data_acquisition/mmgbsa_acquisition_queue_v2.csv")
        prior_plan = phase8.sort_values("acquisition_order_v2")["canonical_id"].astype(str).tolist()
        take(prior_plan, 5, "historical_bridge_interpretable",
             "traceable prior Phase 8 acquisition-plan candidate; not an internal exact identity bridge")
        if len(selected) < int(self.config["panel_size"]):
            take(orders["ATP_Navigator_hybrid"], int(self.config["panel_size"]) - len(selected),
                 "hybrid_rebalanced", "quota de-duplication remainder selected by configured hybrid score")
        panel = by_id.loc[[item[0] for item in selected]].reset_index()
        panel["acquisition_class"] = [item[1] for item in selected]
        panel["why_selected"] = [item[2] for item in selected]
        panel["panel_order"] = np.arange(1, len(panel) + 1)
        panel["evidence_missing"] = "candidate-level MM/GBSA; independent ADMET"
        if len(panel) != int(self.config["panel_size"]) or panel["canonical_id"].duplicated().any():
            raise ValueError("Panel must contain exactly 60 unique candidates")
        return panel

    @staticmethod
    def _selection_metrics(frame: pd.DataFrame, selected_ids: list[str], strategy: str, budget: int) -> dict:
        subset = frame.set_index("canonical_id").loc[selected_ids]
        boundaries = subset["rank_boundary_proximity"].gt(0).sum()
        bins = pd.cut(subset["protocol_uncertainty"], bins=[-0.01, .2, .4, .6, .8, 1.01], labels=False)
        return {
            "strategy": strategy, "budget": budget, "selected": len(subset),
            "unique_scaffolds": int(subset["scaffold"].nunique()),
            "scaffold_coverage": float(subset["scaffold"].nunique() / len(subset)),
            "protocol_uncertainty_bins_covered": int(bins.nunique()),
            "mean_protocol_uncertainty": float(subset["protocol_uncertainty"].mean()),
            "uncertainty_coverage": float(subset["combined_available_uncertainty"].sum() / frame["combined_available_uncertainty"].sum()),
            "evidence_gain_proxy": float(subset["evidence_uncertainty"].sum()),
            "rank_boundary_coverage": int(boundaries),
            "estimated_calculation_cost": float(subset["acquisition_cost"].sum()),
        }

    def _plots(self, frame: pd.DataFrame, panel: pd.DataFrame, simulations: pd.DataFrame) -> None:
        folder = self.output / "figures"; folder.mkdir(parents=True, exist_ok=True)
        plt.figure(figsize=(6, 5)); plt.scatter(frame["glide_rank"], frame["vina_rank"], s=8, alpha=.35)
        plt.xlabel("Glide rank"); plt.ylabel("Vina rank"); plt.title("Glide vs Vina rank (protocol comparison)")
        plt.tight_layout(); plt.savefig(folder / "glide_vina_rank_plot.png", dpi=180); plt.close()
        plt.figure(figsize=(7, 4)); plt.scatter(frame["rank_consensus"], frame["protocol_uncertainty"], s=8, alpha=.35)
        plt.xlabel("Consensus rank"); plt.ylabel("Protocol uncertainty"); plt.title("Protocol disagreement map")
        plt.tight_layout(); plt.savefig(folder / "protocol_disagreement_map.png", dpi=180); plt.close()
        counts = panel["acquisition_class"].value_counts().sort_index()
        plt.figure(figsize=(8, 4)); counts.plot.bar(); plt.ylabel("Candidates"); plt.title("Acquisition panel composition")
        plt.tight_layout(); plt.savefig(folder / "acquisition_class_composition.png", dpi=180); plt.close()
        focus = simulations.loc[simulations["strategy"].isin(["vina_top", "glide_top", "consensus_top", "diversity_aware", "disagreement_aware", "ATP_Navigator_hybrid"])]
        plt.figure(figsize=(7, 4))
        for strategy, group in focus.groupby("strategy"):
            plt.plot(group["budget"], group["scaffold_coverage"], marker="o", label=strategy)
        plt.xlabel("Budget (candidates)"); plt.ylabel("Unique scaffold fraction"); plt.legend(fontsize=7)
        plt.tight_layout(); plt.savefig(folder / "scaffold_coverage_vs_budget.png", dpi=180); plt.close()
        means = frame[["protocol_uncertainty", "objective_uncertainty", "evidence_uncertainty", "chemical_space_uncertainty"]].mean()
        plt.figure(figsize=(7, 4)); means.plot.bar(); plt.ylabel("Mean normalized uncertainty")
        plt.tight_layout(); plt.savefig(folder / "uncertainty_composition.png", dpi=180); plt.close()

    def run(self) -> dict:
        frame, input_hashes = self.build_features()
        orders = self._strategy_orders(frame)
        panel = self._select_panel(frame, orders)
        simulations = []
        for strategy, order in orders.items():
            for budget in self.config["budgets"]:
                simulations.append(self._selection_metrics(frame, order[:budget], strategy, budget))
        simulation = pd.DataFrame(simulations)
        hybrid60 = set(orders["ATP_Navigator_hybrid"][:60])
        comparison = simulation.loc[simulation["budget"].eq(60)].copy()
        comparison["overlap_with_hybrid60"] = [len(set(orders[name][:60]) & hybrid60) for name in comparison["strategy"]]

        protocol_cols = ["canonical_id", "compound_code", "vina_rank", "glide_rank", "rank_consensus",
                         "normalized_rank_variance", "rank_entropy", "protocol_disagreement_score",
                         "consensus_strength"]
        uncertainty_cols = ["canonical_id", "protocol_uncertainty", "model_uncertainty",
                            "model_disagreement_if_available",
                            "model_uncertainty_status", "objective_uncertainty", "evidence_uncertainty",
                            "chemical_space_uncertainty", "combined_available_uncertainty",
                            "uncertainty_available_components", "uncertainty_dominant_source",
                            "distance_to_decision_boundary"]
        voi_cols = ["canonical_id", "recommended_next_evidence", "voi_proxy",
                    "voi_potential_decision_change", "voi_uncertainty", "voi_evidence_importance",
                    "acquisition_cost", "protocol_uncertainty", "rank_boundary_proximity",
                    "scaffold_novelty", "evidence_uncertainty"]
        panel_cols = ["canonical_id", "compound_code", "canonical_smiles", "scaffold", "chemical_space_cluster",
                      "vina_rank", "glide_rank", "rank_delta", "protocol_disagreement", "rank_consensus",
                      "scaffold_size", "cluster_size", "evidence_completeness", "distance_to_decision_boundary",
                      "protocol_uncertainty", "model_uncertainty", "model_disagreement_if_available",
                      "objective_uncertainty", "evidence_uncertainty",
                      "chemical_space_uncertainty", "uncertainty_dominant_source", "voi_proxy", "hybrid_score",
                      "hybrid_rank", "acquisition_cost", "recommended_next_evidence", "evidence_missing",
                      "acquisition_class", "why_selected", "panel_order"]
        _csv(panel[panel_cols], self.output / "acquisition_panel_v1.csv")
        _csv(comparison, self.output / "acquisition_strategy_comparison.csv")
        _csv(frame[protocol_cols].sort_values("rank_consensus"), self.output / "protocol_robustness.csv")
        _csv(frame[uncertainty_cols].sort_values("canonical_id"), self.output / "uncertainty_decomposition.csv")
        _csv(frame[voi_cols].sort_values("voi_proxy", ascending=False), self.output / "voi_proxy.csv")
        _csv(simulation, self.output / "budget_simulation.csv")
        gnina = certify(self.project, timeout_seconds=30)
        _json(gnina, self.output / "gnina_shadow_status.json")
        self._plots(frame, panel, simulation)
        summary = {
            "phase": "Phase 15", "candidate_pool": len(frame), "panel_size": len(panel),
            "panel_class_counts": {str(k): int(v) for k, v in panel["acquisition_class"].value_counts().items()},
            "budgets": self.config["budgets"], "strategies": sorted(orders),
            "protocol_robustness": {
                "mean_disagreement": float(frame["protocol_uncertainty"].mean()),
                "median_disagreement": float(frame["protocol_uncertainty"].median()),
                "extreme_ge_0_8": int(frame["protocol_uncertainty"].ge(.8).sum()),
                "low_le_0_2": int(frame["protocol_uncertainty"].le(.2).sum()),
            },
            "voi_proxy": {"minimum": float(frame["voi_proxy"].min()), "median": float(frame["voi_proxy"].median()),
                          "mean": float(frame["voi_proxy"].mean()), "maximum": float(frame["voi_proxy"].max()),
                          "interpretation": "evidence-acquisition heuristic only"},
            "gnina": gnina, "input_hashes": input_hashes, "config_hash": _file_hash(self.config_path),
            "training_performed": False, "historical_models_modified": False,
            "biological_activity_claim": False,
        }
        _json(summary, self.output / "phase15_summary.json")
        return summary
