# Phase 17.1 Final Report

## Scope and integrity

This recovery patch reuses the 30/30 cached successful results under frozen protocol `open_mmgbsa_7p3w_v2` (`cb28279704aa51f7530e0e61fc592450d43823fe1e23aad5975a638b82407aab`). It did not run a candidate, start the optional 60-candidate extension, train a model, modify Registry Evidence, or overwrite the frozen Decision Engine.

## NaN audit and repair

The prior failure was technical: IEEE NaN values remained after a pandas metrics table was converted to JSON records, while the atomic writer correctly enforced strict JSON. The candidate plan also failed to carry Glide scores forward. Exact candidate-ID joins to the existing Phase14 export recovered 24 historical HTVS Glide results. Five generated candidates and IN-2 have no exact comparable HTVS Glide record and therefore remain scientifically unavailable; they were not imputed. CSV files retain NaN, while JSON uses `null` plus explicit status/reason fields. Unresolved technical joins: 0.

The source audit also records one unavailable Phase15 acquisition score (IN-2), six unavailable historical protocol-disagreement values, one empty frozen-plan scaffold, and 30 not-applicable failure-stage/reason cells because every pilot job succeeded. Derived three-protocol and shadow fields remain unavailable for the same six candidates rather than being filled.

## Three-protocol comparison

Three-protocol exact matched subset: 24/30. Normalization is within-protocol finite-cohort percentile rank with lower raw value treated as better. Raw Glide, Vina and open MM/GBSA values are not interpreted as the same absolute energy.

- glide vs vina: n=24, Spearman=-0.2617391304347826, Kendall=-0.21014492753623187
- glide vs open_mmgbsa: n=24, Spearman=-0.3478260869565217, Kendall=-0.2318840579710145
- vina vs open_mmgbsa: n=30, Spearman=0.421579532814238, Kendall=0.296551724137931

Largest three-protocol disagreement: `ATP-HTVS-66618B00A972` (0.853073).

## Evidence impact and shadow decision

Open MM/GBSA raises the available protocol evidence count for all 30 candidates. Rank-change analysis is restricted to the 24 exact three-protocol candidates. Largest absolute shadow rank change: `ATP-HTVS-66618B00A972` (-8 positions; positive means promotion). The new output is an updated-evidence shadow run only; the frozen Decision Engine remains unchanged. There was no exact candidate-ID overlap with its internal17 output, so direct frozen-rank comparison is not applicable.

## Phase15 acquisition validation

All five intended information categories are represented: {"protocol_disagreement": 6, "strong_candidates": 6, "boundary_uncertainty": 3, "scaffold_diversity": 4, "historical_bridge": 4}. The strategy is therefore supported as an information-coverage allocation, not as proof of biological hit enrichment. The panel contains 23 non-empty scaffolds and 25 non-empty chemical clusters.

## Remaining limitations

- Missing Glide values for six candidates are explained by identity/domain availability, not silently filled.
- Correlations and top-k overlap are descriptive for their finite matched subsets.
- The short restrained aqueous open-MM/GBSA approximation is not equivalent to historical Prime/MMGBSA or a membrane simulation.
- Experimental ATP inhibition, MIC, cytotoxicity and pharmacology remain unknown unless separately measured.
