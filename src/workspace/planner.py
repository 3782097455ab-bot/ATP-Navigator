"""Deterministic research-intent and acquisition planning, not activity prediction."""
from __future__ import annotations
import math
import re
from dataclasses import asdict, dataclass


@dataclass
class ResearchIntent:
    final_experiment_budget: int = 6
    mmgbsa_budget: int = 40
    xp_budget: int = 100
    sp_budget: int = 200
    md_budget: int = 0
    preserve_scaffold_diversity: bool = True
    research_profile: str = 'atp_mechanism_focused'
    expected_candidates: int | None = None

    def validate(self):
        for key,value in asdict(self).items():
            if key.endswith('_budget') and (type(value) is not int or not 0 <= value <= 100000):
                raise ValueError('Budget must be a nonnegative integer: '+key)
        if self.research_profile not in {'balanced','binding_focused','atp_mechanism_focused','experimental_validation_focused'}:
            raise ValueError('Unknown profile')
        return self


def parse_intent(text):
    result = ResearchIntent()
    patterns = {
        'mmgbsa_budget':r'MM\s*/?\s*GBSA(?:预算)?(?:最多|不超过|至多|=|\s)*\s*(\d+)',
        'xp_budget':r'(?<![A-Z])XP(?:预算)?(?:最多|不超过|至多|=|\s)*\s*(\d+)',
        'sp_budget':r'(?<![A-Z])SP(?:预算)?(?:最多|不超过|至多|=|\s)*\s*(\d+)',
        'md_budget':r'(?<![A-Z])MD(?:预算)?(?:最多|不超过|至多|=|\s)*\s*(\d+)',
        'final_experiment_budget':r'(?:最终实验预算|最终(?:给我)?|最后(?:给我)?|实验预算)\s*(\d+)',
        'expected_candidates':r'候选\s*(\d+)',
    }
    if re.search(r'(?:预算|最多|不超过|MMGBSA|XP|SP)\s*-\d',text,re.I):
        raise ValueError('Negative budget')
    for key,pattern in patterns.items():
        matches = re.findall(pattern,text,re.I)
        if len(set(matches)) > 1:
            raise ValueError('Conflicting constraints for '+key)
        if matches:
            setattr(result,key,int(matches[0]))
    if '结合优先' in text or 'binding_focused' in text:
        result.research_profile = 'binding_focused'
    elif '实验验证优先' in text or 'experimental_validation_focused' in text:
        result.research_profile = 'experimental_validation_focused'
    elif '均衡' in text or 'balanced' in text:
        result.research_profile = 'balanced'
    if '不保留骨架' in text:
        result.preserve_scaffold_diversity = False
    return result.validate()


def acquire(candidates, budget, diverse=True, max_cost=None):
    """Heuristic priority/cost. Unknown uncertainty remains unknown in output.

    Formula: (0.40 rank utility + 0.20 missing-evidence fraction +
    0.15 observed uncertainty + 0.15 observed disagreement +
    0.10 novelty-to-selected-scaffolds) / relative cost.
    Missing uncertainty/disagreement has zero heuristic contribution, NOT zero
    measured uncertainty. Coefficients are transparent, not calibrated EIG.
    """
    if type(budget) is not int or budget < 0:
        raise ValueError('Invalid acquisition budget')
    pending = [dict(c) for c in candidates]
    if len({c['compound_id'] for c in pending}) != len(pending):
        raise ValueError('Duplicate candidate ids')
    selected, seen, spent = [],set(),0.0
    total = max(len(pending),1)
    def bounded(value,default):
        if value is None or value == 'unknown':
            return default
        value=float(value)
        return min(1,max(0,value)) if math.isfinite(value) else default
    while pending and len(selected)<budget:
        scored=[]
        for row in pending:
            cost=float(row.get('relative_cost',1))
            if not math.isfinite(cost) or cost<=0:
                raise ValueError('Positive finite calculation cost required')
            if max_cost is not None and spent+cost>max_cost:
                continue
            rank=row.get('current_rank')
            utility=max(0,1-(float(rank)-1)/total) if rank not in (None,'unknown') else 0
            missing=1-bounded(row.get('evidence_completeness'),0)
            uncertainty=bounded(row.get('uncertainty'),0)
            disagreement=bounded(row.get('model_disagreement'),0)
            scaffold=row.get('scaffold','')
            novelty=float(bool(diverse and scaffold and scaffold not in seen))
            score=(.40*utility+.20*missing+.15*uncertainty+.15*disagreement+.10*novelty)/cost
            scored.append((score,row['compound_id'],row,novelty,cost))
        if not scored:
            break
        score,_,row,novelty,cost=sorted(scored,key=lambda x:(-x[0],x[1]))[0]
        pending.remove(row)
        selected.append({**row,'acquisition_rank':len(selected)+1,'acquisition_score':score,
                         'reason':f"rank={row.get('current_rank','unknown')}; completeness={row.get('evidence_completeness','unknown')}; uncertainty={row.get('uncertainty','unknown')}; disagreement={row.get('model_disagreement','unknown')}; new_scaffold={bool(novelty)}; relative_cost={cost}",
                         'interpretation':'heuristic_priority_not_activity_probability_or_validated_information_gain'})
        seen.add(row.get('scaffold',''))
        spent+=cost
    return selected


PREDECESSOR = {'HTVS':'structure_qc','SP':'HTVS','XP':'SP','MMGBSA':'XP','MD':'MMGBSA','QikProp':'structure_qc'}


def gate(candidates, stage, evidence_stages, top_k, percentile=1.0, diverse=True, uncertainty_min=None, max_cost=None):
    if stage not in PREDECESSOR or not 0<=percentile<=1:
        raise ValueError('Invalid stage or percentile')
    eligible=[r for r in candidates if PREDECESSOR[stage] in evidence_stages.get(r['compound_id'],set())]
    eligible.sort(key=lambda r:(r.get('current_rank') if r.get('current_rank') not in (None,'unknown') else math.inf,r['compound_id']))
    eligible=eligible[:math.ceil(len(eligible)*percentile)]
    if uncertainty_min is not None:
        eligible=[r for r in eligible if r.get('uncertainty') not in (None,'unknown') and float(r['uncertainty'])>=uncertainty_min]
    return acquire(eligible,top_k,diverse,max_cost)
