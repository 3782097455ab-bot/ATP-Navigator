"""Data semantic consistency, target annotation, endpoint segregation and provenance QC.

Source grades supplied by an external CSV are assertions, not independent verification.
This importer NEVER promotes data to model training or internal experimental evidence.
"""
import csv
import json
import re
from pathlib import Path
from rdkit import Chem
from .state import digest, encode, file_hash, write_json

DATASETS=['ATP_target_expansion.csv','negative_SAR_examples.csv','ATP_structure_reference.csv','chemical_space_bridge.csv']


def classify(dataset,row):
    issues=[]
    status='source_review_pending'
    canonical='unknown'
    if 'SMILES' in row:
        mol=Chem.MolFromSmiles(row['SMILES']) if row['SMILES'].strip() else None
        if mol is None:
            issues.append('invalid_or_missing_structure')
            status='quarantined'
        else:
            canonical=Chem.MolToSmiles(mol)
    reference=row.get('reference','')
    target=row.get('target','')
    comparator='unknown'
    numeric=None
    activity=row.get('activity_value','').strip()
    match=re.fullmatch(r'\s*([<>≤≥=~]?)\s*(\d+(?:\.\d*)?(?:[eE][+-]?\d+)?)\s*',activity)
    if match:
        comparator=match[1] or '='
        numeric=float(match[2])
    elif activity:
        issues.append('non_scalar_activity_preserved_no_point_label')
    if dataset=='ATP_target_expansion.csv':
        if re.search(r'pilus biogenesis|\bPapD\b',reference,re.I):
            status='quarantined'
            issues.append('target_annotation_conflict_pilus_PapD_reference_not_ATP_synthase')
            issues.append('reference_check_https://pmc.ncbi.nlm.nih.gov/articles/PMC3665338/')
        if row.get('activity_type') in {'Activity','Inhibition'}:
            issues.append('endpoint_or_assay_concentration_requires_review')
        if row.get('organism') in {'Homo sapiens','Saccharomyces cerevisiae'}:
            issues.append('organism_specific_reference_not_bacterial_target_label')
        issues.append('source_level_is_supplied_assertion_not_verified_identity')
    elif dataset=='negative_SAR_examples.csv':
        issues.append('supplied_sar_class_not_reused_as_cross_endpoint_label')
        if comparator!='=':
            issues.append('censoring_preserved_not_exact_regression_label')
        if 'ChemMedChem' in row.get('series','') and 'acsomega' in row.get('DOI',''):
            issues.append('series_journal_reference_conflict')
    elif dataset=='ATP_structure_reference.csv':
        status='structure_reference_review_pending'
        if not re.fullmatch(r'[0-9][a-zA-Z0-9]{3}',row.get('pdb_id','')):
            status='quarantined'
            issues.append('invalid_PDB_identifier')
        if 'apo' in row.get('ligand_or_inhibitor','').lower() and any(x in row.get('pdb_ligand_codes','') for x in ['ATP','ADP']):
            issues.append('apo_vs_bound_nucleotide_description_requires_review')
    elif dataset=='chemical_space_bridge.csv':
        # Even valid structures/similarities are retrieval candidates only.
        status='unverified_retrieval_pool' if status!='quarantined' else status
        issues.append('similarity_or_NCI60_results_are_not_ATP_or_antibacterial_activity_labels')
    stratum=encode({k:row.get(k,'unknown') for k in ['target','organism','strain','activity_type','unit','assay_method']})
    return {'status':status,'canonical_smiles':canonical,'comparator':comparator,'parsed_activity_bound':numeric,
            'endpoint_stratum':stratum,'issues':issues,'training_allowed':False,'internal_evidence_allowed':False}


def import_knowledge(state,source_dir,output_dir):
    source_dir,output_dir=Path(source_dir),Path(output_dir)
    output_dir.mkdir(parents=True,exist_ok=True)
    summary={}
    for name in DATASETS:
        path=source_dir/name
        if not path.is_file():
            summary[name]={'status':'empty_missing_source','rows':0}
            continue
        archived=state.artifact(path)
        with path.open(encoding='utf-8-sig',newline='') as stream:
            original=list(csv.DictReader(stream))
        reviewed=[]
        with state.connect() as db:
            for index,row in enumerate(original,2):
                qc=classify(name,row)
                token='knowledge_'+digest([archived['artifact_hash'],index])[:24]
                db.execute('INSERT OR IGNORE INTO knowledge_record VALUES (?,?,?,?,?,?,?)',
                           (token,name,qc['status'],qc['endpoint_stratum'],archived['artifact_hash'],encode(row),encode(qc)))
                reviewed.append({'record_id':token,'source_row':index,**row,**qc,'source_hash':archived['artifact_hash']})
        keys=list(dict.fromkeys(k for r in reviewed for k in r))
        with (output_dir/name).open('x',encoding='utf-8',newline='') as stream:
            writer=csv.DictWriter(stream,fieldnames=keys)
            writer.writeheader()
            writer.writerows({k:encode(v) if isinstance(v,(list,dict)) else v for k,v in r.items()} for r in reviewed)
        counts={status:sum(r['status']==status for r in reviewed) for status in sorted({r['status'] for r in reviewed})}
        summary[name]={'rows':len(original),'status_counts':counts,'source_hash':archived['artifact_hash'],
                       'source_path':str(path),'registered_in':'knowledge_record','training_allowed':False}
    write_json(output_dir/'qc_summary.json',summary)
    return summary
