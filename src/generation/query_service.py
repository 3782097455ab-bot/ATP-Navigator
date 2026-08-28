"""Read-only Generated Candidate Registry questions."""
from __future__ import annotations

import re
from pathlib import Path
import pandas as pd


def answer(project: Path, question: str) -> dict:
    root=project/"results/phase16"
    registry=pd.read_csv(root/"generated_candidate_registry.csv",keep_default_na=False)
    space=pd.read_csv(root/"generated_chemical_space.csv",keep_default_na=False)
    panel=pd.read_csv(root/"generated_acquisition_panel_v1.csv",keep_default_na=False)
    qc=pd.read_csv(root/"generation_qc.csv",keep_default_na=False)
    text=question.strip(); generated=re.search(r"ATP-GEN-[A-F0-9]{12}",text,re.I); raw=re.search(r"RAW-\d{5}",text,re.I)
    if "围绕IN-2生成100个候选" in text:
        rows=registry.loc[registry["parent_alias"].eq("IN-2")].head(100)
        return {"status":"existing_registry_result","requested":100,"available":len(rows),
                "candidates":rows["generated_candidate_id"].tolist(),"new_generation_executed":False}
    if generated:
        candidate=generated.group(0).upper(); rows=registry.loc[registry["generated_candidate_id"].eq(candidate)]
        if rows.empty: return {"status":"not_found","candidate":candidate}
        row=rows.iloc[0]
        return {"candidate":candidate,"parent_candidate_id":row["parent_candidate_id"],"parent_alias":row["parent_alias"],
                "generator":row["generation_method"],"building_block":row["building_block_id"],
                "attachment_atom_index":int(row["attachment_atom_index"]),
                "parent_similarity":float(space.loc[space["generated_candidate_id"].eq(candidate),"parent_similarity"].iloc[0]),
                "provenance_hash":row["provenance_hash"]}
    if "历史1633最不相似" in text:
        rows=space.nsmallest(20,"nearest_neighbor_similarity")
        return {"criterion":"lowest nearest HTVS-1633 Tanimoto","candidates":rows[["generated_candidate_id","nearest_neighbor_similarity","nearest_htvs1633_id"]].to_dict("records")}
    if "值得进一步做MM/GBSA" in text:
        return {"criterion":"generated acquisition panel","candidates":panel[["generated_candidate_id","acquisition_priority","generated_candidate_score","recommended_next_evidence"]].to_dict("records")}
    if raw:
        row=qc.loc[qc["raw_generation_id"].eq(raw.group(0).upper())]
        return {"raw_generation_id":raw.group(0).upper(),"qc":row[["qc_status","rejection_reason","parent_candidate_id","building_block_id","attachment_atom_index"]].to_dict("records")}
    if "只保留核心骨架" in text:
        rows=registry.loc[registry["scaffold_retention"].astype(str).str.lower().eq("true")]
        return {"criterion":"exact parent Murcko scaffold retention","count":len(rows),"candidates":rows["generated_candidate_id"].head(100).tolist()}
    return {"status":"unsupported_question","supported":["围绕IN-2生成100个候选","generated parent/provenance","最不相似","MM/GBSA面板","RAW淘汰原因","核心骨架"]}
