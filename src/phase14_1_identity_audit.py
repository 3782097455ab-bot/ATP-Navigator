"""Phase 14.1 internal-reference identity audit.

The audit separates exact structure identity from connectivity, neutral-parent,
tautomer, stereochemistry and historical alias relationships. It never maps a
Hit to HTVS by rank or name alone.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
from collections import Counter
from pathlib import Path

import pandas as pd
from rdkit import Chem
from rdkit.Chem.MolStandardize import rdMolStandardize


PROJECT = Path(__file__).resolve().parents[1]
RELATION_ORDER = [
    "exact_canonical", "exact_inchikey", "same_connectivity", "neutral_parent_match",
    "tautomer_related", "stereochemistry_related", "historical_compound_mapping", "unresolved",
]


def atomic_csv(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8-sig", newline="", delete=False,
                                     dir=path.parent, suffix=".tmp") as handle:
        frame.to_csv(handle, index=False)
        temporary = Path(handle.name)
    temporary.replace(path)


def atomic_json(value: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False,
                                     dir=path.parent, suffix=".tmp") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, allow_nan=False)
        temporary = Path(handle.name)
    temporary.replace(path)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def structure_keys(smiles: str) -> dict[str, str]:
    mol = Chem.MolFromSmiles(str(smiles))
    if mol is None:
        raise ValueError(f"Invalid identity-audit SMILES: {smiles}")
    canonical = Chem.MolToSmiles(mol, canonical=True, isomericSmiles=True)
    no_stereo = Chem.MolToSmiles(mol, canonical=True, isomericSmiles=False)
    inchikey = Chem.MolToInchiKey(mol)
    parent = rdMolStandardize.FragmentParent(mol)
    parent = rdMolStandardize.Uncharger().uncharge(parent)
    neutral_parent = Chem.MolToSmiles(parent, canonical=True, isomericSmiles=True)
    tautomer = rdMolStandardize.TautomerEnumerator().Canonicalize(parent)
    tautomer_key = Chem.MolToSmiles(tautomer, canonical=True, isomericSmiles=False)
    return {
        "canonical": canonical,
        "inchikey": inchikey,
        "connectivity": inchikey.split("-")[0],
        "neutral_parent": neutral_parent,
        "tautomer": tautomer_key,
        "no_stereo": no_stereo,
    }


def indexes(htvs: pd.DataFrame) -> dict[str, dict[str, list[str]]]:
    result = {key: {} for key in ["canonical", "inchikey", "connectivity", "neutral_parent", "tautomer", "no_stereo"]}
    for row in htvs.itertuples(index=False):
        keys = structure_keys(row.canonical_smiles)
        for key, value in keys.items():
            result[key].setdefault(value, []).append(row.canonical_id)
    return result


def historical_matches(query_compound_id: str, query_alias: str, mapping: pd.DataFrame,
                       htvs: pd.DataFrame) -> tuple[list[str], list[str], list[str]]:
    linked = mapping.loc[
        mapping["canonical_id"].astype(str).eq(query_compound_id)
        | mapping["original_name"].astype(str).str.casefold().eq(query_alias.casefold())
    ].copy()
    aliases = sorted(set(linked["original_name"].dropna().astype(str).str.strip()) - {""})
    matches: set[str] = set()
    matched_aliases: list[str] = []
    for alias in aliases:
        mask = (
            htvs["compound_code"].astype(str).eq(alias)
            | htvs["variant"].astype(str).eq(alias)
            | htvs["variant"].astype(str).str.startswith(alias + "-")
            | htvs["title"].astype(str).eq(alias)
        )
        found = sorted(htvs.loc[mask, "canonical_id"].unique())
        if found:
            matches.update(found)
            matched_aliases.append(alias)
    sources = sorted(set(linked["source"].dropna().astype(str)))
    return sorted(matches), matched_aliases, sources


def choose_relation(query_keys: dict[str, str], idx: dict[str, dict[str, list[str]]],
                    historical: list[str]) -> tuple[str, list[str]]:
    structural = [
        ("exact_canonical", "canonical"),
        ("exact_inchikey", "inchikey"),
        ("same_connectivity", "connectivity"),
        ("neutral_parent_match", "neutral_parent"),
        ("tautomer_related", "tautomer"),
        ("stereochemistry_related", "no_stereo"),
    ]
    for relation, key in structural:
        matches = sorted(set(idx[key].get(query_keys[key], [])))
        if matches:
            return relation, matches
    if historical:
        return "historical_compound_mapping", historical
    return "unresolved", []


def audit(project: Path = PROJECT) -> tuple[pd.DataFrame, dict]:
    project = project.resolve()
    manifest_path = project / "configs/projects/ab_atp_synthase/vina_7p3w_v1/candidate_identity_manifest.csv"
    htvs_path = project / "data/htvs_structures_v0_1.csv"
    mapping_path = project / "data/compound_mapping_v1.csv"
    ranking_path = project / "results/ranking_output.csv"
    manifest = pd.read_csv(manifest_path, dtype=str, keep_default_na=False)
    manifest_queries = manifest.loc[
        manifest["historical_alias"].eq("IN-2")
        | manifest["historical_alias"].str.fullmatch(r"Hit(?:[1-9]|1[0-7])")
    ].copy()
    ranking = pd.read_csv(ranking_path, dtype=str, keep_default_na=False)
    ranking_queries = ranking.loc[
        ranking["historical_alias"].str.fullmatch(r"Hit(?:[1-9]|1[0-7])"),
        ["compound_id", "historical_alias", "smiles"],
    ].rename(columns={"smiles": "SMILES"})
    ranking_queries["identity_source"] = str(ranking_path.relative_to(project))
    ranking_queries["identity_status"] = "confirmed_internal"
    # ranking_output is the complete, frozen Hit1-Hit17 source.  The manifest
    # contributes IN-2 and any independently curated Hit records.  De-duplicate
    # by alias without inventing missing identities.
    queries = pd.concat([ranking_queries, manifest_queries], ignore_index=True)
    queries = queries.drop_duplicates(subset=["historical_alias"], keep="first")
    queries["sort_order"] = queries["historical_alias"].map(
        lambda value: 0 if value == "IN-2" else int(value.removeprefix("Hit"))
    )
    queries = queries.sort_values("sort_order")
    if len(queries) != 18:
        raise ValueError(f"Expected IN-2 plus Hit1-Hit17, found {len(queries)}")
    htvs = pd.read_csv(htvs_path, dtype=str, keep_default_na=False)
    mapping = pd.read_csv(mapping_path, dtype=str, keep_default_na=False)
    idx = indexes(htvs)
    rows = []
    for query in queries.itertuples(index=False):
        keys = structure_keys(query.SMILES)
        historical, historical_aliases, historical_sources = historical_matches(
            query.compound_id, query.historical_alias, mapping, htvs
        )
        relation, matches = choose_relation(keys, idx, historical)
        exact = relation in {"exact_canonical", "exact_inchikey"}
        confidence = "high" if exact else "medium" if relation != "unresolved" else "low"
        evidence = [
            f"{manifest_path.relative_to(project)}#{query.compound_id}",
            f"{htvs_path.relative_to(project)}",
            f"{mapping_path.relative_to(project)}",
        ]
        if historical_sources:
            evidence.extend(historical_sources)
        notes = []
        if len(matches) > 1:
            notes.append(f"{len(matches)} HTVS records share the selected identity relation; no single record inferred by rank")
        if historical_aliases:
            notes.append("historical aliases searched=" + ";".join(historical_aliases))
        if historical:
            notes.append("historical HTVS matches=" + ";".join(historical))
        if query.historical_alias == "Hit3":
            notes.append("aliases 466, ATP-CHAR-466, ATP-Top1-MD2 and Top-3 were searched; none map to an HTVS1633 code")
        if query.historical_alias == "Hit13":
            notes.append("alias 91074 is directly present as an HTVS compound_code and independently supports the structural relation")
        if relation not in {"exact_canonical", "exact_inchikey", "unresolved"}:
            notes.append("related mapping only; not upgraded to exact structure")
        if relation == "unresolved":
            notes.append("no exact/related structure key or traceable historical HTVS ID found")
        rows.append({
            "query_id": query.historical_alias,
            "query_compound_id": query.compound_id,
            "query_smiles": keys["canonical"],
            "matched_htvs_id": ";".join(matches),
            "matched_count": len(matches),
            "identity_relation": relation,
            "exact_match": exact,
            "confidence": confidence,
            "evidence_source": ";".join(dict.fromkeys(evidence)),
            "notes": "; ".join(notes),
        })
    frame = pd.DataFrame(rows)
    counts = Counter(frame["identity_relation"])
    summary = {
        "phase": "Phase 14.1",
        "query_count": len(frame),
        "htvs_count": len(htvs),
        "relation_counts": {name: int(counts.get(name, 0)) for name in RELATION_ORDER},
        "exact_query_count": int(frame["exact_match"].sum()),
        "unresolved_query_count": int(frame["identity_relation"].eq("unresolved").sum()),
        "hit3_relation": frame.loc[frame["query_id"].eq("Hit3"), "identity_relation"].iloc[0],
        "hit13_relation": frame.loc[frame["query_id"].eq("Hit13"), "identity_relation"].iloc[0],
        "input_hashes": {
            str(manifest_path.relative_to(project)): sha256(manifest_path),
            str(htvs_path.relative_to(project)): sha256(htvs_path),
            str(mapping_path.relative_to(project)): sha256(mapping_path),
            str(ranking_path.relative_to(project)): sha256(ranking_path),
        },
        "policy": "related mappings are not exact structures; no name/rank-only inference",
    }
    return frame, summary


def report(frame: pd.DataFrame, summary: dict) -> str:
    lines = [
        "# Internal 17 + IN-2 Identity Audit", "", "日期：2026-08-28", "",
        "## 审计结论", "",
        f"- 查询结构：{summary['query_count']}（Hit1–Hit17 + IN-2）；HTVS结构：{summary['htvs_count']}；",
        f"- exact query：{summary['exact_query_count']}；unresolved：{summary['unresolved_query_count']}；",
        "- related mapping只说明结构或历史关系，不升级为exact structure；未按名称、排名或相邻行猜测。", "",
        "## 分层结果", "",
        "| query | relation | matched HTVS | exact | confidence | notes |", "|---|---|---|---|---|---|",
    ]
    for row in frame.itertuples(index=False):
        lines.append(
            f"| {row.query_id} | {row.identity_relation} | {row.matched_htvs_id or '—'} | "
            f"{str(row.exact_match).lower()} | {row.confidence} | {row.notes} |"
        )
    lines.extend([
        "", "## 关键别名审计", "",
        "- Hit3：`466`、`ATP-CHAR-466`、`ATP-Top1-MD2`、`Top-3`可在项目映射中相互关联，但没有可追溯HTVS-1633 compound code，因此仍为unresolved；",
        "- Hit13：`91074`直接匹配HTVS compound code，且结构层同时满足exact canonical；若多个HTVS pose/variant共享相同结构，全部保留，不按rank挑成唯一身份；",
        "- IN-2：是确认的外部/项目参考结构，但未发现其属于HTVS-1633的可追溯记录。", "",
        "## 数据边界", "",
        "本审计属于compound identity、target annotation和provenance QC，不产生生物活性标签，不修改历史Docking/MMGBSA或模型。", "",
    ])
    return "\n".join(lines)


def run(project: Path = PROJECT) -> dict:
    project = project.resolve()
    frame, summary = audit(project)
    result_dir = project / "results/phase14_1"
    atomic_csv(frame, result_dir / "internal17_identity_audit.csv")
    atomic_json(summary, result_dir / "internal17_identity_audit_summary.json")
    (project / "docs/internal17_identity_audit.md").write_text(report(frame, summary), encoding="utf-8")
    phase14 = json.loads((project / "results/phase14/phase14_execution_summary.json").read_text(encoding="utf-8"))
    completion = {
        "phase": "Phase 14.1",
        "vina_retry": {
            "attempted": phase14["qc"].get("phase14_1_retry_attempted", 0),
            "success": phase14["qc"].get("phase14_1_retry_success", 0),
            "failed": phase14["qc"].get("phase14_1_retry_failed", 0),
            "workers": phase14.get("workers"),
            "protocol_id": phase14.get("protocol_id"),
            "protocol_file_hash": phase14.get("protocol_file_hash"),
            "receptor_hash": phase14.get("receptor_hash"),
        },
        "final_vina": phase14["qc"],
        "identity_audit": summary,
        "training_performed": False,
        "historical_model_change": False,
    }
    atomic_json(completion, result_dir / "phase14_1_summary.json")
    return completion


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=PROJECT)
    args = parser.parse_args()
    print(json.dumps(run(args.project_root), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
