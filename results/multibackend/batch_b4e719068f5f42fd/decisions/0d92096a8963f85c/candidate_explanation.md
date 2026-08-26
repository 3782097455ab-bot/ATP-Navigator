# ATP-Navigator Candidate Recommendation Report

版本：ATP-Navigator_Phase10_Explanation_v1.0

研究模式：`atp_mechanism_focused`

输入来源：`candidate_view.csv`

> 本报告用于决定下一批实验资源的优先顺序。它不证明候选具有ATP抑制或抗菌活性。

## Ranking overview

| Rank | Candidate | Model tool | Final score | Mean robust rank | P(Top 3) | Risk | Recommendation |
|---:|---|---|---:|---:|---:|---|---|
| unknown | ATP-SMI-15737353FB69 | Model_v2-A_structure_only_fallback | unknown | unknown | unknown | unknown | Insufficient computational evidence; do not prioritize automatically |
| unknown | ATP-SMI-4417138BF81D | Model_v2-A_structure_only_fallback | unknown | unknown | unknown | unknown | Insufficient computational evidence; do not prioritize automatically |
| unknown | ATP-SMI-5B36D3E11A3B | Model_v2-A_structure_only_fallback | unknown | unknown | unknown | unknown | Insufficient computational evidence; do not prioritize automatically |

## Candidate-level explanations

### ATP-SMI-15737353FB69

- Rank: unknown
- Recommendation: Insufficient computational evidence; do not prioritize automatically
- Final score: unknown
- Decision confidence: insufficient_computational_data
- Predicted risk band: unknown

Reasons:

1. ATP-related computational evidence: batch-relative component score 17.50.
2. Antibacterial external-model prior: batch-relative component score 0.00.
3. Model tool: Model_v2-A_structure_only_fallback; its score predicts the preserved static-MM/GBSA computational task, not biological activity.

Limitations:

- Experimental ATP inhibition: unknown
- MIC: unknown
- Experimental toxicity: unknown
- External ATP and antibacterial priors are cross-domain model outputs, not measurements on this candidate.
- Final and component scores are relative to the submitted candidate batch and are not success probabilities.
- Missing computational fields recorded by the processor: ["docking_score", "mmgbsa_score", "admet_features", "complete_quickprop_features"]

### ATP-SMI-4417138BF81D

- Rank: unknown
- Recommendation: Insufficient computational evidence; do not prioritize automatically
- Final score: unknown
- Decision confidence: insufficient_computational_data
- Predicted risk band: unknown

Reasons:

1. Antibacterial external-model prior: batch-relative component score 50.00.
2. ATP-related computational evidence: batch-relative component score 47.50.
3. Model tool: Model_v2-A_structure_only_fallback; its score predicts the preserved static-MM/GBSA computational task, not biological activity.

Limitations:

- Experimental ATP inhibition: unknown
- MIC: unknown
- Experimental toxicity: unknown
- External ATP and antibacterial priors are cross-domain model outputs, not measurements on this candidate.
- Final and component scores are relative to the submitted candidate batch and are not success probabilities.
- Missing computational fields recorded by the processor: ["docking_score", "mmgbsa_score", "admet_features", "complete_quickprop_features"]

### ATP-SMI-5B36D3E11A3B

- Rank: unknown
- Recommendation: Insufficient computational evidence; do not prioritize automatically
- Final score: unknown
- Decision confidence: insufficient_computational_data
- Predicted risk band: unknown

Reasons:

1. Antibacterial external-model prior: batch-relative component score 100.00.
2. ATP-related computational evidence: batch-relative component score 85.00.
3. Model tool: Model_v2-A_structure_only_fallback; its score predicts the preserved static-MM/GBSA computational task, not biological activity.

Limitations:

- Experimental ATP inhibition: unknown
- MIC: unknown
- Experimental toxicity: unknown
- External ATP and antibacterial priors are cross-domain model outputs, not measurements on this candidate.
- Final and component scores are relative to the submitted candidate batch and are not success probabilities.
- Missing computational fields recorded by the processor: ["docking_score", "mmgbsa_score", "admet_features", "complete_quickprop_features"]

## Interpretation boundary

- `P(Top 3)` is the frequency of entering the top three under the declared weight distribution, not biological activity probability.
- `risk` summarizes predicted ADMET endpoints and descriptor rules; it is not experimental safety.
- A lower-priority molecule is retained as a comparator and is not labeled inactive.
- Experimental results remain `unknown` until a traceable assay result is imported.
