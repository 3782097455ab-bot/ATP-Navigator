# ATP-Navigator Candidate Recommendation Report

版本：ATP-Navigator_Phase10_Explanation_v1.0

研究模式：`atp_mechanism_focused`

输入来源：`candidate_input.csv`

> 本报告用于决定下一批实验资源的优先顺序。它不证明候选具有ATP抑制或抗菌活性。

## Ranking overview

| Rank | Candidate | Model tool | Final score | Mean robust rank | P(Top 3) | Risk | Recommendation |
|---:|---|---|---:|---:|---:|---|---|
| 1 | ATP-SMI-96FD6257D8BA | Model_v3_full_frozen | 67.90 | 2.12 | 0.847 | moderate_predicted_risk | High priority for experimental evaluation (computational decision only) |
| 2 | ATP-SMI-5D3E7B6B6796 | Model_v3_full_frozen | 67.04 | 3.02 | 0.707 | moderate_predicted_risk | High priority for experimental evaluation (computational decision only) |
| 3 | ATP-SMI-CDED936B42F4 | Model_v3_full_frozen | 66.06 | 3.75 | 0.475 | moderate_predicted_risk | High priority for experimental evaluation (computational decision only) |
| 4 | ATP-SMI-5B36D3E11A3B | Model_v3_full_frozen | 65.84 | 3.79 | 0.424 | moderate_predicted_risk | High priority for experimental evaluation (computational decision only) |
| 5 | ATP-SMI-9DA3213A09E8 | Model_v3_full_frozen | 65.81 | 3.90 | 0.493 | moderate_predicted_risk | Intermediate priority or diversity/uncertainty comparison candidate |
| 6 | ATP-SMI-E9798004BA11 | Model_v3_full_frozen | 64.88 | 5.21 | 0.001 | lower_predicted_risk | Intermediate priority or diversity/uncertainty comparison candidate |
| 7 | ATP-SMI-91E7552C2382 | Model_v3_full_frozen | 60.35 | 7.17 | 0.017 | moderate_predicted_risk | Intermediate priority or diversity/uncertainty comparison candidate |
| 8 | ATP-SMI-C93E6EC67CDB | Model_v3_full_frozen | 57.32 | 8.10 | 0.036 | moderate_predicted_risk | Intermediate priority or diversity/uncertainty comparison candidate |
| 9 | ATP-SMI-775D33706F04 | Model_v3_full_frozen | 56.02 | 8.84 | 0.001 | moderate_predicted_risk | Intermediate priority or diversity/uncertainty comparison candidate |
| 10 | ATP-SMI-4417138BF81D | Model_v3_full_frozen | 55.12 | 9.61 | 0.000 | moderate_predicted_risk | Intermediate priority or diversity/uncertainty comparison candidate |
| 11 | ATP-SMI-CFA68A98711F | Model_v3_full_frozen | 51.73 | 11.23 | 0.000 | moderate_predicted_risk | Intermediate priority or diversity/uncertainty comparison candidate |
| 12 | ATP-SMI-C3308BEE03AC | Model_v3_full_frozen | 47.54 | 12.21 | 0.000 | moderate_predicted_risk | Lower current priority; retain as a comparator, not a presumed inactive |
| 13 | ATP-SMI-874C2DE25FE4 | Model_v3_full_frozen | 46.94 | 12.89 | 0.000 | lower_predicted_risk | Lower current priority; retain as a comparator, not a presumed inactive |
| 14 | ATP-SMI-BF69AB71C1A4 | Model_v3_full_frozen | 45.65 | 13.79 | 0.000 | moderate_predicted_risk | Lower current priority; retain as a comparator, not a presumed inactive |
| 15 | ATP-SMI-FCA9CDF3313B | Model_v3_full_frozen | 45.06 | 14.42 | 0.000 | moderate_predicted_risk | Lower current priority; retain as a comparator, not a presumed inactive |
| 16 | ATP-SMI-94F73967C042 | Model_v3_full_frozen | 39.81 | 16.36 | 0.000 | moderate_predicted_risk | Lower current priority; retain as a comparator, not a presumed inactive |
| 17 | ATP-SMI-15737353FB69 | Model_v3_full_frozen | 39.57 | 16.57 | 0.000 | lower_predicted_risk | Lower current priority; retain as a comparator, not a presumed inactive |

## Candidate-level explanations

### ATP-SMI-96FD6257D8BA

- Rank: 1
- Recommendation: High priority for experimental evaluation (computational decision only)
- Final score: 67.90
- Decision confidence: medium_computational_only
- Predicted risk band: moderate_predicted_risk

Reasons:

1. Drug-likeness and predicted ADMET evidence: batch-relative component score 85.19.
2. Binding evidence: batch-relative component score 71.25.
3. ATP-related computational evidence: batch-relative component score 66.88.
4. Model tool: Model_v3_full_frozen; its score predicts the preserved static-MM/GBSA computational task, not biological activity.

Limitations:

- Experimental ATP inhibition: unknown
- MIC: unknown
- Experimental toxicity: unknown
- External ATP and antibacterial priors are cross-domain model outputs, not measurements on this candidate.
- Final and component scores are relative to the submitted candidate batch and are not success probabilities.

### ATP-SMI-5D3E7B6B6796

- Rank: 2
- Recommendation: High priority for experimental evaluation (computational decision only)
- Final score: 67.04
- Decision confidence: medium_computational_only
- Predicted risk band: moderate_predicted_risk

Reasons:

1. Drug-likeness and predicted ADMET evidence: batch-relative component score 85.19.
2. ATP-related computational evidence: batch-relative component score 67.03.
3. Binding evidence: batch-relative component score 65.00.
4. Model tool: Model_v3_full_frozen; its score predicts the preserved static-MM/GBSA computational task, not biological activity.

Limitations:

- Experimental ATP inhibition: unknown
- MIC: unknown
- Experimental toxicity: unknown
- External ATP and antibacterial priors are cross-domain model outputs, not measurements on this candidate.
- Final and component scores are relative to the submitted candidate batch and are not success probabilities.

### ATP-SMI-CDED936B42F4

- Rank: 3
- Recommendation: High priority for experimental evaluation (computational decision only)
- Final score: 66.06
- Decision confidence: medium_computational_only
- Predicted risk band: moderate_predicted_risk

Reasons:

1. Drug-likeness and predicted ADMET evidence: batch-relative component score 87.04.
2. ATP-related computational evidence: batch-relative component score 81.88.
3. Binding evidence: batch-relative component score 35.00.
4. Model tool: Model_v3_full_frozen; its score predicts the preserved static-MM/GBSA computational task, not biological activity.

Limitations:

- Experimental ATP inhibition: unknown
- MIC: unknown
- Experimental toxicity: unknown
- External ATP and antibacterial priors are cross-domain model outputs, not measurements on this candidate.
- Final and component scores are relative to the submitted candidate batch and are not success probabilities.

### ATP-SMI-5B36D3E11A3B

- Rank: 4
- Recommendation: High priority for experimental evaluation (computational decision only)
- Final score: 65.84
- Decision confidence: medium_computational_only
- Predicted risk band: moderate_predicted_risk

Reasons:

1. Drug-likeness and predicted ADMET evidence: batch-relative component score 87.04.
2. Antibacterial external-model prior: batch-relative component score 81.25.
3. ATP-related computational evidence: batch-relative component score 80.94.
4. Model tool: Model_v3_full_frozen; its score predicts the preserved static-MM/GBSA computational task, not biological activity.

Limitations:

- Experimental ATP inhibition: unknown
- MIC: unknown
- Experimental toxicity: unknown
- External ATP and antibacterial priors are cross-domain model outputs, not measurements on this candidate.
- Final and component scores are relative to the submitted candidate batch and are not success probabilities.

### ATP-SMI-9DA3213A09E8

- Rank: 5
- Recommendation: Intermediate priority or diversity/uncertainty comparison candidate
- Final score: 65.81
- Decision confidence: medium_computational_only
- Predicted risk band: moderate_predicted_risk

Reasons:

1. Drug-likeness and predicted ADMET evidence: batch-relative component score 85.19.
2. Binding evidence: batch-relative component score 82.50.
3. Antibacterial external-model prior: batch-relative component score 56.25.
4. Model tool: Model_v3_full_frozen; its score predicts the preserved static-MM/GBSA computational task, not biological activity.

Limitations:

- Experimental ATP inhibition: unknown
- MIC: unknown
- Experimental toxicity: unknown
- External ATP and antibacterial priors are cross-domain model outputs, not measurements on this candidate.
- Final and component scores are relative to the submitted candidate batch and are not success probabilities.

### ATP-SMI-E9798004BA11

- Rank: 6
- Recommendation: Intermediate priority or diversity/uncertainty comparison candidate
- Final score: 64.88
- Decision confidence: medium_computational_only
- Predicted risk band: lower_predicted_risk

Reasons:

1. Drug-likeness and predicted ADMET evidence: batch-relative component score 80.56.
2. ATP-related computational evidence: batch-relative component score 65.47.
3. Binding evidence: batch-relative component score 63.75.
4. Model tool: Model_v3_full_frozen; its score predicts the preserved static-MM/GBSA computational task, not biological activity.

Limitations:

- Experimental ATP inhibition: unknown
- MIC: unknown
- Experimental toxicity: unknown
- External ATP and antibacterial priors are cross-domain model outputs, not measurements on this candidate.
- Final and component scores are relative to the submitted candidate batch and are not success probabilities.

### ATP-SMI-91E7552C2382

- Rank: 7
- Recommendation: Intermediate priority or diversity/uncertainty comparison candidate
- Final score: 60.35
- Decision confidence: medium_computational_only
- Predicted risk band: moderate_predicted_risk

Reasons:

1. Drug-likeness and predicted ADMET evidence: batch-relative component score 87.04.
2. ATP-related computational evidence: batch-relative component score 76.09.
3. Antibacterial external-model prior: batch-relative component score 50.00.
4. Model tool: Model_v3_full_frozen; its score predicts the preserved static-MM/GBSA computational task, not biological activity.

Limitations:

- Experimental ATP inhibition: unknown
- MIC: unknown
- Experimental toxicity: unknown
- External ATP and antibacterial priors are cross-domain model outputs, not measurements on this candidate.
- Final and component scores are relative to the submitted candidate batch and are not success probabilities.

### ATP-SMI-C93E6EC67CDB

- Rank: 8
- Recommendation: Intermediate priority or diversity/uncertainty comparison candidate
- Final score: 57.32
- Decision confidence: medium_computational_only
- Predicted risk band: moderate_predicted_risk

Reasons:

1. Antibacterial external-model prior: batch-relative component score 93.75.
2. Binding evidence: batch-relative component score 90.00.
3. Drug-likeness and predicted ADMET evidence: batch-relative component score 87.04.
4. Model tool: Model_v3_full_frozen; its score predicts the preserved static-MM/GBSA computational task, not biological activity.

Limitations:

- Experimental ATP inhibition: unknown
- MIC: unknown
- Experimental toxicity: unknown
- External ATP and antibacterial priors are cross-domain model outputs, not measurements on this candidate.
- Final and component scores are relative to the submitted candidate batch and are not success probabilities.

### ATP-SMI-775D33706F04

- Rank: 9
- Recommendation: Intermediate priority or diversity/uncertainty comparison candidate
- Final score: 56.02
- Decision confidence: medium_computational_only
- Predicted risk band: moderate_predicted_risk

Reasons:

1. Antibacterial external-model prior: batch-relative component score 87.50.
2. Drug-likeness and predicted ADMET evidence: batch-relative component score 87.04.
3. ATP-related computational evidence: batch-relative component score 58.44.
4. Model tool: Model_v3_full_frozen; its score predicts the preserved static-MM/GBSA computational task, not biological activity.

Limitations:

- Experimental ATP inhibition: unknown
- MIC: unknown
- Experimental toxicity: unknown
- External ATP and antibacterial priors are cross-domain model outputs, not measurements on this candidate.
- Final and component scores are relative to the submitted candidate batch and are not success probabilities.

### ATP-SMI-4417138BF81D

- Rank: 10
- Recommendation: Intermediate priority or diversity/uncertainty comparison candidate
- Final score: 55.12
- Decision confidence: medium_computational_only
- Predicted risk band: moderate_predicted_risk

Reasons:

1. Drug-likeness and predicted ADMET evidence: batch-relative component score 85.19.
2. ATP-related computational evidence: batch-relative component score 67.19.
3. Antibacterial external-model prior: batch-relative component score 62.50.
4. Model tool: Model_v3_full_frozen; its score predicts the preserved static-MM/GBSA computational task, not biological activity.

Limitations:

- Experimental ATP inhibition: unknown
- MIC: unknown
- Experimental toxicity: unknown
- External ATP and antibacterial priors are cross-domain model outputs, not measurements on this candidate.
- Final and component scores are relative to the submitted candidate batch and are not success probabilities.

### ATP-SMI-CFA68A98711F

- Rank: 11
- Recommendation: Intermediate priority or diversity/uncertainty comparison candidate
- Final score: 51.73
- Decision confidence: medium_computational_only
- Predicted risk band: moderate_predicted_risk

Reasons:

1. Drug-likeness and predicted ADMET evidence: batch-relative component score 83.33.
2. ATP-related computational evidence: batch-relative component score 56.09.
3. Antibacterial external-model prior: batch-relative component score 43.75.
4. Model tool: Model_v3_full_frozen; its score predicts the preserved static-MM/GBSA computational task, not biological activity.

Limitations:

- Experimental ATP inhibition: unknown
- MIC: unknown
- Experimental toxicity: unknown
- External ATP and antibacterial priors are cross-domain model outputs, not measurements on this candidate.
- Final and component scores are relative to the submitted candidate batch and are not success probabilities.

### ATP-SMI-C3308BEE03AC

- Rank: 12
- Recommendation: Lower current priority; retain as a comparator, not a presumed inactive
- Final score: 47.54
- Decision confidence: medium_computational_only
- Predicted risk band: moderate_predicted_risk

Reasons:

1. Antibacterial external-model prior: batch-relative component score 100.00.
2. Drug-likeness and predicted ADMET evidence: batch-relative component score 87.04.
3. Binding evidence: batch-relative component score 47.50.
4. Model tool: Model_v3_full_frozen; its score predicts the preserved static-MM/GBSA computational task, not biological activity.

Limitations:

- Experimental ATP inhibition: unknown
- MIC: unknown
- Experimental toxicity: unknown
- External ATP and antibacterial priors are cross-domain model outputs, not measurements on this candidate.
- Final and component scores are relative to the submitted candidate batch and are not success probabilities.

### ATP-SMI-874C2DE25FE4

- Rank: 13
- Recommendation: Lower current priority; retain as a comparator, not a presumed inactive
- Final score: 46.94
- Decision confidence: medium_computational_only
- Predicted risk band: lower_predicted_risk

Reasons:

1. Drug-likeness and predicted ADMET evidence: batch-relative component score 90.74.
2. Binding evidence: batch-relative component score 83.75.
3. ATP-related computational evidence: batch-relative component score 16.41.
4. Model tool: Model_v3_full_frozen; its score predicts the preserved static-MM/GBSA computational task, not biological activity.

Limitations:

- Experimental ATP inhibition: unknown
- MIC: unknown
- Experimental toxicity: unknown
- External ATP and antibacterial priors are cross-domain model outputs, not measurements on this candidate.
- Final and component scores are relative to the submitted candidate batch and are not success probabilities.

### ATP-SMI-BF69AB71C1A4

- Rank: 14
- Recommendation: Lower current priority; retain as a comparator, not a presumed inactive
- Final score: 45.65
- Decision confidence: medium_computational_only
- Predicted risk band: moderate_predicted_risk

Reasons:

1. Drug-likeness and predicted ADMET evidence: batch-relative component score 87.04.
2. Antibacterial external-model prior: batch-relative component score 75.00.
3. Binding evidence: batch-relative component score 48.75.
4. Model tool: Model_v3_full_frozen; its score predicts the preserved static-MM/GBSA computational task, not biological activity.

Limitations:

- Experimental ATP inhibition: unknown
- MIC: unknown
- Experimental toxicity: unknown
- External ATP and antibacterial priors are cross-domain model outputs, not measurements on this candidate.
- Final and component scores are relative to the submitted candidate batch and are not success probabilities.

### ATP-SMI-FCA9CDF3313B

- Rank: 15
- Recommendation: Lower current priority; retain as a comparator, not a presumed inactive
- Final score: 45.06
- Decision confidence: medium_computational_only
- Predicted risk band: moderate_predicted_risk

Reasons:

1. Drug-likeness and predicted ADMET evidence: batch-relative component score 87.04.
2. Binding evidence: batch-relative component score 46.25.
3. Antibacterial external-model prior: batch-relative component score 37.50.
4. Model tool: Model_v3_full_frozen; its score predicts the preserved static-MM/GBSA computational task, not biological activity.

Limitations:

- Experimental ATP inhibition: unknown
- MIC: unknown
- Experimental toxicity: unknown
- External ATP and antibacterial priors are cross-domain model outputs, not measurements on this candidate.
- Final and component scores are relative to the submitted candidate batch and are not success probabilities.

### ATP-SMI-94F73967C042

- Rank: 16
- Recommendation: Lower current priority; retain as a comparator, not a presumed inactive
- Final score: 39.81
- Decision confidence: medium_computational_only
- Predicted risk band: moderate_predicted_risk

Reasons:

1. Drug-likeness and predicted ADMET evidence: batch-relative component score 87.04.
2. Antibacterial external-model prior: batch-relative component score 68.75.
3. Binding evidence: batch-relative component score 35.00.
4. Model tool: Model_v3_full_frozen; its score predicts the preserved static-MM/GBSA computational task, not biological activity.

Limitations:

- Experimental ATP inhibition: unknown
- MIC: unknown
- Experimental toxicity: unknown
- External ATP and antibacterial priors are cross-domain model outputs, not measurements on this candidate.
- Final and component scores are relative to the submitted candidate batch and are not success probabilities.

### ATP-SMI-15737353FB69

- Rank: 17
- Recommendation: Lower current priority; retain as a comparator, not a presumed inactive
- Final score: 39.57
- Decision confidence: medium_computational_only
- Predicted risk band: lower_predicted_risk

Reasons:

1. Drug-likeness and predicted ADMET evidence: batch-relative component score 88.89.
2. Binding evidence: batch-relative component score 51.25.
3. ATP-related computational evidence: batch-relative component score 20.47.
4. Model tool: Model_v3_full_frozen; its score predicts the preserved static-MM/GBSA computational task, not biological activity.

Limitations:

- Experimental ATP inhibition: unknown
- MIC: unknown
- Experimental toxicity: unknown
- External ATP and antibacterial priors are cross-domain model outputs, not measurements on this candidate.
- Final and component scores are relative to the submitted candidate batch and are not success probabilities.

## Interpretation boundary

- `P(Top 3)` is the frequency of entering the top three under the declared weight distribution, not biological activity probability.
- `risk` summarizes predicted ADMET endpoints and descriptor rules; it is not experimental safety.
- A lower-priority molecule is retained as a comparator and is not labeled inactive.
- Experimental results remain `unknown` until a traceable assay result is imported.
