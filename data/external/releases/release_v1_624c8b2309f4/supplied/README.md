# ATP-Navigator Data Release v1

Release date: 2026-08-26

## What is safe to feed into a model

Use `measurements_model_ready.csv` joined to `compounds.csv` by `compound_key`. For ordinary regression, filter `use_for_default_regression == true` and use `p_activity` as the label. Keep organism and `assay_id` as task/provenance fields. Split by scaffold and DOI, not by random rows.

Never concatenate MIC, ETC, cytotoxicity, percent inhibition and ATP-synthesis IC50 into one label. The release keeps them in separate partitions and endpoints.

## Release partitions

- `measurements_model_ready.csv`: source-verified direct ATP-synthase observations from five primary papers, with corrected structures, normalized units, relation operators and table/figure locators.
- `measurements_auxiliary.csv`: MIC, ETC and cytotoxicity endpoints. Useful for multi-objective ranking, not as ATP labels.
- `measurements_reference_only.csv`: valid-looking reference data that were not source-verified to the same strict standard or come from other species/assays.
- `measurements_quarantine.csv`: wrong-target, unresolved-identity and duplicate-lineage rows. Do not train on these.
- `chemical_space_bridge_quarantine.csv`: the supplied PubChem neighbor table, retained for audit only because it has no measured endpoint and does not reproduce a strong bridge to supplied internal anchors.

## Structural corrections

The WSA pyridine and quinoline series, Ward 2024 series, and the directly used Steed/Fraunfelter identities were reconstructed from primary-paper structure schemes. The release stores the input structures in `compound_aliases.csv` for lineage, but strict training uses the corrected canonical structures. RDKit parsing alone was not accepted as identity verification.

## Censored values

`value_relation` preserves `gt`, `lt`, `approx`, `range`, and `mean_sd`. Do not turn `>64` into an exact 64. The default regression flag excludes censored values; a censored-loss or classification task may use them separately.

## Summary

- Model-ready observations: 49
- Model-ready unique structures: 39
- Model-ready assays: 6
- Model-ready inactive structures: 4
- Source-labeled inactive / weak structures in model-ready set: 2 / 9
- Auxiliary observations: 229
- Quarantined measurement lineage rows: 115
- Quarantined original bridge rows: 120
- PDB references: 28; direct A. baumannii inhibitor-bound entries: 0
- Automated release validation: PASS

## Remaining limitation

This release is suitable for data ingestion and pilot modeling, but the A. baumannii direct-target set remains small and source-clustered. Treat performance estimates as pilot evidence and use prospective wet-lab feedback for the next closed-loop iteration.
