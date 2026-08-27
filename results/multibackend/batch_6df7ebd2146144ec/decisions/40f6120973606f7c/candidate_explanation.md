# ATP-Navigator Candidate Recommendation Report

版本：ATP-Navigator_Phase10_Explanation_v1.0

研究模式：`atp_mechanism_focused`

输入来源：`candidate_view.csv`

> 本报告用于决定下一批实验资源的优先顺序。它不证明候选具有ATP抑制或抗菌活性。

## Ranking overview

| Rank | Candidate | Model tool | Final score | Mean robust rank | P(Top 3) | Risk | Recommendation |
|---:|---|---|---:|---:|---:|---|---|
| unknown | ATP-REF-IN2 | Model_v2-A_structure_only_fallback | unknown | unknown | unknown | unknown | Insufficient computational evidence; do not prioritize automatically |
| unknown | ATP-SMI-874C2DE25FE4 | Model_v2-A_structure_only_fallback | unknown | unknown | unknown | unknown | Insufficient computational evidence; do not prioritize automatically |
| unknown | ATP-SMI-96FD6257D8BA | Model_v2-A_structure_only_fallback | unknown | unknown | unknown | unknown | Insufficient computational evidence; do not prioritize automatically |
| unknown | ATP-SMI-9DA3213A09E8 | Model_v2-A_structure_only_fallback | unknown | unknown | unknown | unknown | Insufficient computational evidence; do not prioritize automatically |
| unknown | ATP-SMI-C93E6EC67CDB | Model_v2-A_structure_only_fallback | unknown | unknown | unknown | unknown | Insufficient computational evidence; do not prioritize automatically |

## Candidate-level explanations

### ATP-REF-IN2

- Rank: unknown
- Recommendation: Insufficient computational evidence; do not prioritize automatically
- Final score: unknown
- Decision confidence: insufficient_computational_data
- Predicted risk band: unknown

Reasons:

1. Antibacterial external-model prior: batch-relative component score 50.00.
2. ATP-related computational evidence: batch-relative component score 30.00.
3. Model tool: Model_v2-A_structure_only_fallback; its score predicts the preserved static-MM/GBSA computational task, not biological activity.

Limitations:

- Experimental ATP inhibition: unknown
- MIC: unknown
- Experimental toxicity: unknown
- External ATP and antibacterial priors are cross-domain model outputs, not measurements on this candidate.
- Final and component scores are relative to the submitted candidate batch and are not success probabilities.
- Missing computational fields recorded by the processor: ["docking_score", "mmgbsa_score", "admet_features", "complete_quickprop_features"]

### ATP-SMI-874C2DE25FE4

- Rank: unknown
- Recommendation: Insufficient computational evidence; do not prioritize automatically
- Final score: unknown
- Decision confidence: insufficient_computational_data
- Predicted risk band: unknown

Reasons:

1. ATP-related computational evidence: batch-relative component score 35.00.
2. Antibacterial external-model prior: batch-relative component score 0.00.
3. Model tool: Model_v2-A_structure_only_fallback; its score predicts the preserved static-MM/GBSA computational task, not biological activity.

Limitations:

- Experimental ATP inhibition: unknown
- MIC: unknown
- Experimental toxicity: unknown
- External ATP and antibacterial priors are cross-domain model outputs, not measurements on this candidate.
- Final and component scores are relative to the submitted candidate batch and are not success probabilities.
- Missing computational fields recorded by the processor: ["docking_score", "mmgbsa_score", "admet_features", "complete_quickprop_features"]

### ATP-SMI-96FD6257D8BA

- Rank: unknown
- Recommendation: Insufficient computational evidence; do not prioritize automatically
- Final score: unknown
- Decision confidence: insufficient_computational_data
- Predicted risk band: unknown

Reasons:

1. ATP-related computational evidence: batch-relative component score 83.75.
2. Antibacterial external-model prior: batch-relative component score 25.00.
3. Model tool: Model_v2-A_structure_only_fallback; its score predicts the preserved static-MM/GBSA computational task, not biological activity.

Limitations:

- Experimental ATP inhibition: unknown
- MIC: unknown
- Experimental toxicity: unknown
- External ATP and antibacterial priors are cross-domain model outputs, not measurements on this candidate.
- Final and component scores are relative to the submitted candidate batch and are not success probabilities.
- Missing computational fields recorded by the processor: ["docking_score", "mmgbsa_score", "admet_features", "complete_quickprop_features"]

### ATP-SMI-9DA3213A09E8

- Rank: unknown
- Recommendation: Insufficient computational evidence; do not prioritize automatically
- Final score: unknown
- Decision confidence: insufficient_computational_data
- Predicted risk band: unknown

Reasons:

1. Antibacterial external-model prior: batch-relative component score 75.00.
2. ATP-related computational evidence: batch-relative component score 67.50.
3. Model tool: Model_v2-A_structure_only_fallback; its score predicts the preserved static-MM/GBSA computational task, not biological activity.

Limitations:

- Experimental ATP inhibition: unknown
- MIC: unknown
- Experimental toxicity: unknown
- External ATP and antibacterial priors are cross-domain model outputs, not measurements on this candidate.
- Final and component scores are relative to the submitted candidate batch and are not success probabilities.
- Missing computational fields recorded by the processor: ["docking_score", "mmgbsa_score", "admet_features", "complete_quickprop_features"]

### ATP-SMI-C93E6EC67CDB

- Rank: unknown
- Recommendation: Insufficient computational evidence; do not prioritize automatically
- Final score: unknown
- Decision confidence: insufficient_computational_data
- Predicted risk band: unknown

Reasons:

1. Antibacterial external-model prior: batch-relative component score 100.00.
2. ATP-related computational evidence: batch-relative component score 33.75.
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
