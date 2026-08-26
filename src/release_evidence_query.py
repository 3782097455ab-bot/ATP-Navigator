"""Read the shared knowledge registry. Retrieved measurements remain external evidence."""
import json
import re


def search_release_records(db,query,limit=5):
    if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='knowledge_record'").fetchone():
        return []
    terms=re.findall(r'[a-z0-9_-]+|[\u4e00-\u9fff]+',query.lower())
    scored=[]
    for item in db.execute("SELECT * FROM knowledge_record WHERE dataset LIKE 'release_v1_%'"):
        row=dict(item)
        record=json.loads(row['record'])
        text=json.dumps(record,ensure_ascii=False).lower()
        score=sum(term in text for term in terms)
        if not score:
            continue
        result={'registry_record_id':row['record_id'],'dataset':row['dataset'],'QC_status':row['status'],
                'source_hash':row['source_hash'],'compound':record.get('compound_name',record.get('anchor_compound','unknown')),
                'compound_key':record.get('compound_key','unknown'),'target':record.get('target','unknown'),
                'organism':record.get('organism','unknown'),'strain':record.get('strain','unknown'),
                'endpoint':record.get('endpoint','unknown'),'value':record.get('value','unknown'),
                'relation':record.get('value_relation','unknown'),'unit':record.get('unit','unknown'),
                'assay_id':record.get('assay_id','unknown'),'DOI':record.get('doi','unknown'),
                'source_locator':record.get('source_locator','unknown'),'source_url':record.get('source_url','unknown'),
                'use_boundary':'External source measurement, not an internal candidate experimental result; quarantined/reference records are not training labels.'}
        priority=1 if row['status']=='eligible_for_conditional_pilot' else 0
        scored.append((score,priority,result))
    return [r for _,_,r in sorted(scored,key=lambda x:(-x[0],-x[1],x[2]['registry_record_id']))[:limit]]
