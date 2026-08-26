"""Budget allocation: transparent strata, not a prediction of experimental success."""
from dataclasses import asdict
import math
import re
from .planner import parse_intent,acquire

DEFAULT_ALLOCATION={'exploitation':.625,'uncertainty':.25,'diversity':.125}


def topological_nodes(graph):
    if any(dep not in graph for deps in graph.values() for dep in deps): raise ValueError('Unknown DAG dependency')
    pending={k:set(v) for k,v in graph.items()};ordered=[]
    while pending:
        ready=[k for k,v in pending.items() if not v]
        if not ready: raise ValueError('Cyclic workflow DAG')
        for key in ready:
            ordered.append(key);pending.pop(key)
            for deps in pending.values(): deps.discard(key)
    return ordered


def intent(text):
    result=asdict(parse_intent(text));result['docking_budget']=200
    patterns={'mmgbsa_budget':r'MM\s*/?\s*GBSA(?:预算)?(?:最多|不超过|至多|计算|个|\s|=)*(\d+)',
              'docking_budget':r'(?:Docking|对接)(?:预算)?(?:最多|计算|\s|=)*(\d+)',
              'final_experiment_budget':r'(?:最后|最终)(?:实验验证|实验预算|给我|验证|\s)*(\d+)'}
    for key,pattern in patterns.items():
        found=re.findall(pattern,text,re.I)
        if len(set(found))>1: raise ValueError('Conflicting '+key)
        if found: result[key]=int(found[0])
    for k,v in result.items():
        if k.endswith('_budget') and not 0<=v<=100000: raise ValueError('Invalid budget')
    result['allocation']=DEFAULT_ALLOCATION.copy()
    return result


def allocate(rows,budget,ratios=None,diverse=True,max_cost=None):
    ratios=ratios or DEFAULT_ALLOCATION
    if set(ratios)!=set(DEFAULT_ALLOCATION) or any(v<0 or not math.isfinite(v) for v in ratios.values()) or abs(sum(ratios.values())-1)>1e-8:
        raise ValueError('Allocation fractions must be finite and sum to one')
    if type(budget)!=int or budget<0: raise ValueError('Budget invalid')
    budget=min(budget,len(rows));remaining={r['compound_id']:dict(r) for r in rows};chosen=[];seen=set();spent=0
    if len(remaining)!=len(rows): raise ValueError('Duplicate identity')
    counts={k:int(budget*v) for k,v in ratios.items()};counts['exploitation']+=budget-sum(counts.values())
    for category,count in counts.items():
        for _ in range(count):
            options=[r for r in remaining.values() if max_cost is None or spent+float(r.get('relative_cost',1))<=max_cost]
            if category=='uncertainty':
                options=[r for r in options if r.get('uncertainty') not in (None,'unknown') or r.get('model_disagreement') not in (None,'unknown')]
            if category=='diversity' and diverse: options=[r for r in options if r.get('scaffold') and r['scaffold'] not in seen]
            if not options: break
            if category=='uncertainty':
                def observed(r): return sum(float(r[k]) if r.get(k) not in (None,'unknown') else 0 for k in ['uncertainty','model_disagreement'])
                options.sort(key=lambda r:(-observed(r),r['compound_id']))
                row=options[0]
            else: row=acquire(options,1,diverse,max_cost-spent if max_cost is not None else None)[0]
            cost=float(row.get('relative_cost',1))
            if cost<=0 or not math.isfinite(cost): raise ValueError('Invalid cost')
            row={**row,'allocation_stratum':category,'reason':f"{category}; rank={row.get('current_rank','unknown')}; uncertainty={row.get('uncertainty','unknown')}; disagreement={row.get('model_disagreement','unknown')}; completeness={row.get('evidence_completeness','unknown')}; cost={cost}"}
            chosen.append(row);remaining.pop(row['compound_id']);seen.add(row.get('scaffold'));spent+=cost
    # Do not fabricate uncertainty to fill that quota. Explicitly label fallback.
    for row in acquire(list(remaining.values()),budget-len(chosen),diverse,max_cost-spent if max_cost is not None else None):
        chosen.append({**row,'allocation_stratum':'fallback_no_eligible_stratum'})
    return chosen
