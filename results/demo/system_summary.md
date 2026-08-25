# ATP-Navigator Phase 10 Demo Summary

运行模式：`atp_mechanism_focused`  
候选数量：17  
完整决策数量：17  
工作流自评：pass（10/10 checks passed）  
确定性复跑一致：true

## End-to-end workflow

```text
Candidate input
  → RDKit structure validation and canonicalization
  → Morgan1024 + molecular descriptors
  → preserved Model v3 / declared Model v2-A fallback
  → ATP-reference similarity + external knowledge priors
  → transparent four-component decision score
  → profile-conditioned robustness ranking
  → candidate explanation and workflow self-audit
```

## Current top experimental priorities

| Rank | Alias | Compound ID | Final score | Mean robust rank | P(Top 3) | Predicted risk band |
|---:|---|---|---:|---:|---:|---|
| 1 | Hit5 | `ATP-SMI-96FD6257D8BA` | 67.90 | 2.12 | 0.847 | moderate_predicted_risk |
| 2 | Hit4 | `ATP-SMI-5D3E7B6B6796` | 67.04 | 3.02 | 0.707 | moderate_predicted_risk |
| 3 | Hit11 | `ATP-SMI-CDED936B42F4` | 66.06 | 3.75 | 0.475 | moderate_predicted_risk |
| 4 | Hit13 | `ATP-SMI-5B36D3E11A3B` | 65.84 | 3.79 | 0.424 | moderate_predicted_risk |
| 5 | Hit1 | `ATP-SMI-9DA3213A09E8` | 65.81 | 3.90 | 0.493 | moderate_predicted_risk |
| 6 | Hit6 | `ATP-SMI-E9798004BA11` | 64.88 | 5.21 | 0.001 | lower_predicted_risk |

`P(Top 3)` is conditional rank acceptability under the declared weight distribution, not biological activity probability.

## Scientific status

- Model training performed in Phase 10: no;
- Historical models modified: no;
- Experimental ATP inhibition: unknown;
- MIC: unknown;
- Experimental toxicity: unknown;
- Biological hit-rate improvement evaluated: no;
- Demonstrated capability: an auditable workflow from post-screening candidates to a frozen experimental-priority panel.
