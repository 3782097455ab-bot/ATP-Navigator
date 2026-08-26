"""Read-only scientific invariants and a real persistent-session knowledge query."""
import json
import sys
from pathlib import Path
import pandas as pd

PROJECT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PROJECT/'src'))
from workspace.state import file_hash,write_json
from research_workspace import ResearchWorkspace
from release_v1_audit import register_existing


def main():
    output=PROJECT/'results/release_v1_final_checks'
    output.mkdir(parents=True,exist_ok=False)
    release=PROJECT/'data/external/releases/release_v1_624c8b2309f4'
    registration=register_existing(PROJECT,release)
    summary=json.loads((PROJECT/'results/phase12/internal_17_run2/execution_summary.json').read_text(encoding='utf-8'))
    workspace=ResearchWorkspace(PROJECT)
    retrieved=workspace.chat(summary['session_id'],'查资料 WSA280')
    write_json(output/'research_session_knowledge_query.json',retrieved)
    entries=retrieved.get('release_evidence',[])
    oldhashes=summary['model_hashes']
    audit=json.loads((release/'independent_audit.json').read_text())
    acquisition=json.loads((PROJECT/'results/release_v1_acquisition/acquisition_summary.json').read_text())
    papers=list((PROJECT/'data/literature/papers/atp_release_v1').glob('*.xml'))
    checks={'frozen_24_models_unchanged':len(oldhashes)==24 and all(file_hash(PROJECT/p)==h for p,h in oldhashes.items()),
            'release_49_assay_specific_records':audit['independent_pilot_eligible_rows']==49,
            'no_new_internal_experiment_labels':audit['internal_labels_added']==0,
            'five_primary_papers_archived':len(papers)==5,
            'five_primary_paper_texts_nonempty':all(p.with_suffix('.txt').stat().st_size>0 for p in papers),
            'session_can_retrieve_new_release':any(e['compound']=='WSA280' for e in entries),
            'retrieved_data_are_external':all('not an internal' in e['use_boundary'] for e in entries),
            'calculation_queue_within_budget':acquisition['proposed']<=40,
            'no_commercial_jobs_submitted':acquisition['computations_submitted']==0,
            'no_decision_change':not acquisition['decision_engine_changed']}
    result={'checks':checks,'all_passed':all(checks.values()),'registry_restoration':registration,
            'note':'This is an integrity/functionality check, not evidence of biological efficacy.'}
    write_json(output/'checks.json',result)
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return 0 if result['all_passed'] else 1


if __name__=='__main__':
    raise SystemExit(main())
