# Member data integration audit

## Scope

This integration is additive and does not train or modify Model v3. Source workbooks remain unchanged under `data/external/curated/`. The audit concerns chemical identity, endpoint segregation, target/organism annotation and provenance QC; it is not a biosafety assessment.

## Member 2 — Gram-negative antibacterial MIC

- Source: `data/external/curated/Member2_GN_antibacterial_week1.xlsx`
- Raw rows: 310
- RDKit-valid structure rows: 310
- Unique InChIKey structures: 19
- Exact duplicate rows within the member source: 37 across 17 duplicate groups
- Unique structures already present in External Dataset v2: 19
- Truly new structures: 0
- Semantic assay overlaps with External Dataset v2: 20 rows
- Strict source-aware assay overlaps: 0 rows
- New species/strain context strings relative to External Dataset v2: 64

The apparent increment is therefore primarily assay-condition and resistance-context detail, not chemical-space expansion. A strict key includes structure, organism/context, endpoint, operator, value, unit and reference. A semantic key omits the reference so independently imported records can still be recognized as equivalent measurements. The 273 non-duplicate rows absent under the strict key remain candidate increments pending endpoint and provenance review; they are not automatically promoted to training labels.

Raw SMILES, organism, activity, unit, reference and source-level fields are preserved in `data/external/integrated/member2_gn_mic_audit.csv`. RDKit-derived canonical SMILES and InChIKey are added in separate fields. Submitted chemical structures were not manually edited.

## Member 3 Part 2 — benchmark catalog

- Source: `data/external/curated/Member3_Part2_AI_Benchmark_26_audited.xlsx`
- Registry entries: 26
- Registry type: `benchmark_metadata_catalog`
- Benchmarks executed: 0
- Training records added: 0
- Part1 experimental benchmark records: `pending`

The catalog is exposed in the GUI as **External Benchmark Registry**. It is a resource map containing dataset, task, size, input, output, split, metric, source, reference, relevance and verification fields. It does not claim that any of the 26 benchmarks has been run.

## Generated assets

- `data/external/integrated/member2_gn_mic_audit.csv`
- `data/external/integrated/member2_gn_mic_increment.csv`
- `data/external/integrated/benchmark_registry_v1.csv`
- `data/external/integrated/benchmark_registry_status.json`
- `results/data_integration/member_data_integration_summary.json`

## Scientific use boundary

MIC records remain endpoint-specific antibacterial evidence. They are not mixed with IC50, binding affinity, docking, Vina or MM/GBSA as one label. Benchmark metadata stays outside training. No model performance claim was produced in this integration.
