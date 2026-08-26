"""Independently ingest a supplied data release; supplied QA is not our QA.

No measurement is an internal candidate label merely because structures match.
Source-verified claims are preserved as claims; this audit checks identifiers,
formulas, units, hashes, task separation and source locators independently.
"""
from __future__ import annotations
import argparse
import json
import math
import re
import shutil
from pathlib import Path
import numpy as np
import pandas as pd
from rdkit import Chem,DataStructs
from rdkit.Chem import Descriptors,rdMolDescriptors,rdFingerprintGenerator
from rdkit.Chem.MolStandardize import rdMolStandardize
from rdkit.Chem.Scaffolds import MurckoScaffold
from workspace.state import State,file_hash,digest,encode,write_json
from collect_release_literature import PAPERS


def identity_key(smiles):
    mol=Chem.MolFromSmiles(smiles)
    if mol is None:
        raise ValueError('Invalid SMILES')
    parent=rdMolStandardize.FragmentParent(mol)
    parent=rdMolStandardize.Uncharger().uncharge(parent)
    Chem.RemoveStereochemistry(parent)
    return Chem.MolToSmiles(parent)


def molar_value(value,unit,mw):
    unit=unit.strip().replace('μ','u').replace('µ','u')
    value=float(value)
    if not math.isfinite(value) or value<=0:
        raise ValueError('Nonpositive/nonfinite measurement')
    if unit=='ug/mL':
        return value*.001/mw
    if unit=='ng/mL':
        return value*.000001/mw
    if unit in {'M','mM','uM','nM'}:
        return value*{'M':1,'mM':1e-3,'uM':1e-6,'nM':1e-9}[unit]
    raise ValueError('Unknown unit')


def audit(project,source):
    project,source=Path(project).resolve(),Path(source).resolve()
    manifest_path=source/'release_manifest.csv'
    manifest=pd.read_csv(manifest_path)
    integrity=[]
    for row in manifest.to_dict('records'):
        path=(source/row['file']).resolve()
        if not path.is_relative_to(source) or not path.is_file():
            raise ValueError('Manifest references absent/unsafe file')
        valid=file_hash(path)==row['sha256'] and path.stat().st_size==int(row['bytes'])
        integrity.append({'file':row['file'],'pass':valid,'actual_sha256':file_hash(path)})
    if not all(r['pass'] for r in integrity):
        raise ValueError('Release integrity mismatch; inspect before import')
    release_id='release_v1_'+file_hash(manifest_path)[:12]
    dest=project/'data/external/releases'/release_id
    dest.mkdir(parents=True,exist_ok=False)
    raw=dest/'supplied'
    raw.mkdir()
    for path in source.iterdir():
        if path.is_file() and path.suffix.lower() in {'.csv','.json','.md','.xlsx'}:
            shutil.copyfile(path,raw/path.name)
    compounds=pd.read_csv(raw/'compounds.csv',dtype=str,keep_default_na=False)
    measurements=pd.read_csv(raw/'measurements_model_ready.csv',dtype=str,keep_default_na=False)
    if compounds.compound_key.duplicated().any() or measurements.measurement_id.duplicated().any():
        raise ValueError('Duplicate entity or measurement identifier')
    structural=[]
    for row in compounds.to_dict('records'):
        issues=[]
        mol=Chem.MolFromSmiles(row['canonical_smiles'])
        if mol is None:
            issues.append('invalid_smiles')
            values={}
        else:
            formula=rdMolDescriptors.CalcMolFormula(mol)
            key=Chem.MolToInchiKey(mol)
            mw=Descriptors.MolWt(mol)
            if formula!=row['molecular_formula']:
                issues.append('formula_mismatch')
            if key!=row['inchi_key'] or key!=row['compound_key']:
                issues.append('inchikey_mismatch')
            if abs(mw-float(row['molecular_weight']))>.02:
                issues.append('molecular_weight_mismatch')
            values={'recomputed_formula':formula,'recomputed_mw':mw,'parent_identity':identity_key(row['canonical_smiles']),
                    'scaffold':MurckoScaffold.MurckoScaffoldSmiles(mol=mol,includeChirality=False)}
        structural.append({**row,**values,'independent_structural_qc':'pass' if not issues else 'quarantine',
                           'issues':';'.join(issues),'source_identity_claim':row['structure_verification'],
                           'independent_source_identity_verification':'not_all_schemes_redrawn_in_this_audit'})
    entities=pd.DataFrame(structural)
    merged=measurements.merge(entities,on='compound_key',validate='many_to_one',how='left')
    assays=pd.read_csv(raw/'assays.csv',dtype=str,keep_default_na=False).set_index('assay_id')
    rows=[]
    for row in merged.to_dict('records'):
        issues=[]
        if row.get('independent_structural_qc')!='pass':
            issues.append('structure_QC_failed')
        if str(row.get('identity_verified')).lower()!='true':
            issues.append('source_identity_not_claimed_verified')
        if row['target']!='F1Fo-ATP synthase' or row['endpoint']!='IC50_ATP_synthesis':
            issues.append('target_or_endpoint_not_direct_ATP_IC50')
        if row['doi'] not in PAPERS.values() or not row['source_locator']:
            issues.append('missing_or_unrecognized_primary_source')
        if row['assay_id'] not in assays.index:
            issues.append('assay_not_registered')
        else:
            assay=assays.loc[row['assay_id']]
            for key in ['target','organism','strain','assay_system','endpoint','doi']:
                if assay[key]!=row[key]:
                    issues.append('assay_semantic_mismatch_'+key)
        if row['value_relation']!='exact' or str(row['use_for_default_regression']).lower()!='true':
            issues.append('not_exact_regression_observation')
        if re.search(r'[<>≤≥~±]',row['raw_activity_value']):
            issues.append('raw_censoring_or_uncertainty_requires_review')
        try:
            molar=molar_value(row['value'],row['unit'],float(row['recomputed_mw']))
            pvalue=-math.log10(molar)
            if not math.isclose(molar,float(row['molar_value']),rel_tol=1e-5) or abs(pvalue-float(row['p_activity']))>1e-5:
                issues.append('unit_conversion_mismatch')
        except (ValueError,TypeError):
            molar,pvalue=None,None
            issues.append('unusable_numeric_or_unit')
        rows.append({**row,'audit_status':'eligible_for_conditional_pilot' if not issues else 'quarantined',
                     'audit_issues':';'.join(issues),'recomputed_molar_value':molar,'recomputed_p_activity':pvalue,
                     'label_semantics':'external_source_ATP_synthesis_IC50_assay_specific_not_internal_activity',
                     'primary_source_validation_scope':'source DOI/locator and automated structure/unit QC; not independent verification of every drawn bond'})
    reviewed=pd.DataFrame(rows)
    duplicates=reviewed.duplicated(['compound_key','assay_id'],keep=False)
    reviewed.loc[duplicates,'audit_status']='quarantined'
    reviewed.loc[duplicates,'audit_issues']+=';duplicate_compound_assay'
    eligible=reviewed.loc[reviewed.audit_status.eq('eligible_for_conditional_pilot')].copy()
    entities.to_csv(dest/'compounds_independent_audit.csv',index=False)
    reviewed.to_csv(dest/'measurement_independent_audit.csv',index=False)
    eligible.to_csv(dest/'pilot_eligible_measurements.csv',index=False)
    # Register all supplied partitions as knowledge, not as internal computational/experimental evidence.
    state=State(project)
    counts={}
    for name in ['measurements_model_ready.csv','measurements_auxiliary.csv','measurements_reference_only.csv',
                 'measurements_quarantine.csv','chemical_space_bridge_quarantine.csv','structure_references.csv']:
        frame=pd.read_csv(raw/name,dtype=str,keep_default_na=False)
        artifact=state.artifact(raw/name)
        counts[name]=len(frame)
        with state.connect() as db:
            for i,row in enumerate(frame.to_dict('records'),2):
                record_id='release_'+digest([artifact['artifact_hash'],i])[:24]
                status='source_reference_only'
                if name=='measurements_model_ready.csv':
                    matched=reviewed.loc[reviewed.measurement_id.eq(row['measurement_id'])]
                    status=matched.iloc[0]['audit_status'] if len(matched) else 'quarantined'
                elif 'quarantine' in name:
                    status='quarantined_no_training'
                elif name=='measurements_auxiliary.csv':
                    status='auxiliary_endpoint_isolated_no_ATP_label'
                stratum=encode({k:row.get(k,'unknown') for k in ['assay_id','endpoint','organism','strain','doi','unit']})
                db.execute('INSERT OR IGNORE INTO knowledge_record VALUES (?,?,?,?,?,?,?)',
                           (record_id,release_id+'/'+name,status,stratum,artifact['artifact_hash'],encode(row),
                            encode({'internal_candidate_experimental_label':False,'source_claim_independently_audited':False})))
    assay_stats=eligible.groupby(['assay_id','organism','doi']).agg(n=('measurement_id','size'),
                 unique_structures=('compound_key','nunique'),scaffolds=('scaffold','nunique')).reset_index()
    assay_stats.to_csv(dest/'assay_training_scale.csv',index=False)
    summary={'release_id':release_id,'source':str(source),'manifest_integrity':integrity,'partition_counts':counts,
             'supplied_model_ready_rows':len(measurements),'independent_pilot_eligible_rows':len(eligible),
             'eligible_unique_structures':eligible.compound_key.nunique(),'eligible_assays':eligible.assay_id.nunique(),
             'structural_QC_failures':int(entities.independent_structural_qc.ne('pass').sum()),
             'measurement_QC_failures':int(reviewed.audit_status.eq('quarantined').sum()),
             'raw_source_preserved':True,'mixed_endpoint_training':False,'internal_labels_added':0,
             'training_scope':'Separate assay-specific pilots only; release source-verification is not a substitute for row-wise re-extraction.'}
    write_json(dest/'independent_audit.json',summary)
    return dest,summary


def register_existing(project,release):
    """Restore the shared registry from an already versioned release, no file rewrite."""
    project,release=Path(project),Path(release)
    manifest=pd.read_csv(release/'supplied/release_manifest.csv')
    for row in manifest.to_dict('records'):
        path=(release/'supplied'/row['file']).resolve()
        if not path.is_relative_to((release/'supplied').resolve()) or file_hash(path)!=row['sha256']:
            raise ValueError('Archived release integrity mismatch')
    reviewed=pd.read_csv(release/'measurement_independent_audit.csv',dtype=str,keep_default_na=False).set_index('measurement_id')
    state=State(project)
    registered=0
    for path in (release/'supplied').glob('*.csv'):
        if not path.name.startswith('measurements_') and path.name not in {'chemical_space_bridge_quarantine.csv','structure_references.csv'}:
            continue
        frame=pd.read_csv(path,dtype=str,keep_default_na=False)
        artifact=state.artifact(path)
        with state.connect() as db:
            for i,row in enumerate(frame.to_dict('records'),2):
                status='source_reference_only'
                if path.name=='measurements_model_ready.csv':
                    status=reviewed.loc[row['measurement_id'],'audit_status']
                elif 'quarantine' in path.name:
                    status='quarantined_no_training'
                elif path.name=='measurements_auxiliary.csv':
                    status='auxiliary_endpoint_isolated_no_ATP_label'
                stratum=encode({k:row.get(k,'unknown') for k in ['assay_id','endpoint','organism','strain','doi','unit']})
                db.execute('INSERT OR IGNORE INTO knowledge_record VALUES (?,?,?,?,?,?,?)',
                           ('release_'+digest([artifact['artifact_hash'],i])[:24],release.name+'/'+path.name,status,
                            stratum,artifact['artifact_hash'],encode(row),encode({'internal_candidate_experimental_label':False})))
                registered+=1
    return {'registry_records_checked':registered,'training_performed':False,'files_modified':False}


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--project-root',type=Path,default=Path(__file__).resolve().parents[1])
    parser.add_argument('--source',type=Path)
    parser.add_argument('--register-existing',type=Path)
    args=parser.parse_args()
    if args.register_existing:
        print(json.dumps(register_existing(args.project_root,args.register_existing),ensure_ascii=False,indent=2))
    elif args.source:
        folder,result=audit(args.project_root,args.source)
        print(json.dumps({'output':str(folder),**{k:v for k,v in result.items() if k!='manifest_integrity'}},ensure_ascii=False,indent=2))
    else:
        parser.error('--source or --register-existing is required')
