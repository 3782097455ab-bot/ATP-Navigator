"""Strict exports-to-evidence adapters. Never guess unknown units or identities."""
from __future__ import annotations
import csv
import math
import re
from pathlib import Path

GLIDE = {
    'r_i_docking_score':('docking_score','Glide_score'),
    'r_i_glide_gscore':('glide_gscore','Glide_score'),
    'r_i_glide_emodel':('glide_emodel','Glide_emodel'),
    'r_i_glide_energy':('glide_energy','kcal/mol'),
    'r_i_glide_evdw':('glide_evdw','kcal/mol'),
    'r_i_glide_ecoul':('glide_ecoul','kcal/mol'),
    'r_i_glide_einternal':('glide_einternal','kcal/mol'),
    'r_i_glide_eff_state_penalty':('glide_eff_state_penalty','unknown'),
    'r_i_glide_ligand_efficiency':('glide_ligand_efficiency','Glide_score/heavy_atom'),
    'r_i_glide_ligand_efficiency_sa':('glide_ligand_efficiency_sa','unknown'),
    'r_i_glide_ligand_efficiency_ln':('glide_ligand_efficiency_ln','unknown'),
    'docking_score':('docking_score','Glide_score'), 'glide_docking_score':('docking_score','Glide_score'),
}
PRIME = {'r_psp_MMGBSA_dG_Bind':('mmgbsa_score','kcal/mol'),
         'MMGBSA dG Bind':('mmgbsa_score','kcal/mol'),
         'mmgbsa_score':('mmgbsa_score','kcal/mol')}


def property_contract(tool, field):
    if tool == 'glide':
        return GLIDE.get(field)
    if tool == 'prime_mmgbsa':
        return PRIME.get(field)
    if tool == 'qikprop' and (field.startswith(('r_qp_','i_qp_','quickprop_'))):
        suffix = re.sub(r'[^a-z0-9]+','_',re.sub(r'^(r_qp_|i_qp_|quickprop_)','',field).lower()).strip('_')
        return 'quickprop_' + suffix, 'unknown'
    return None


def parse_records(records, tool, allowed_ids):
    if tool not in {'glide','prime_mmgbsa','qikprop'}:
        raise ValueError('Unsupported parser')
    output = []
    for row in records:
        compound = str(row.get('compound_id',row.get('s_m_title',''))).strip()
        recognized = [(key,property_contract(tool,key)) for key in row if property_contract(tool,key)]
        if not recognized:
            continue  # e.g. receptor entry of a poseviewer, not a ligand result
        if compound not in allowed_ids:
            raise ValueError('Unmapped output compound: ' + compound)
        for key, (feature,unit) in recognized:
            if str(row[key]).strip().lower() in {'','unknown','<>','nan','none'}:
                continue
            value = float(row[key])
            if not math.isfinite(value):
                raise ValueError('Nonfinite numerical result')
            output.append({'compound_id':compound,'evidence_type':feature,'raw_value':value,
                           'normalized_value':None,'unit':unit,'source_property':key})
    if not output:
        raise ValueError('No recognized finite tool results; cannot mark successful')
    # Multiple poses are not silently averaged. Keep per-pose selection outside parser.
    keys = [(r['compound_id'],r['evidence_type']) for r in output]
    if len(keys) != len(set(keys)):
        raise ValueError('Multiple poses/results require explicit pose selection before registration')
    required = {'glide':'docking_score','prime_mmgbsa':'mmgbsa_score'}.get(tool)
    if required and not any(r['evidence_type']==required for r in output):
        raise ValueError('Required scoring property absent')
    return output


def parse_csv(path, tool, allowed_ids):
    with Path(path).open(encoding='utf-8-sig',newline='') as stream:
        return parse_records(list(csv.DictReader(stream)),tool,allowed_ids)
