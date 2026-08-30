# Competition Release Candidate Data Integration Report

## Scope

This is an additive, provenance-preserving integration. Source workbooks and the uploaded BindingDB TSV were read-only. MIC, IC50, Ki, Kd and computational energies remain separate endpoints. The audit concerns data semantics, target annotation, endpoint segregation and provenance QC; it is not a biosafety assessment.

## Member 1 — ATP synthase literature table

- Raw/QC rows: 39/39
- RDKit-valid structures: 15 rows; 8 unique structures
- Direct ATP-synthase target annotations: 19
- Training-eligible exact records: 0
- Validation-eligible literature records: 7

The workbook is primarily a literature lead list. Qualitative claims, ranges, placeholder structure descriptions, implied targets and records without exact primary-assay provenance remain reference-only.

## Member 2 — Gram-negative MIC context

- Raw rows: 310; valid structures: 310
- Unique structures: 19; exact structure overlap with External Dataset v2: 19
- Truly new structures: 0
- Training-eligible nonduplicate, non-semantic-overlap assay-context rows: 270
- New strain/resistance context strings: 64

The increment is assay/strain context, not new chemical space. MIC remains whole-cell antibacterial evidence and is not ATP-synthase activity.

## Member 3 Part 1 — BindingDB concrete records

- Raw BindingDB rows: 93712; exploded endpoint measurements: 96195
- Unique valid structures: 47190
- Exact/direct ATP synthase records: 0
- General binding validation records: 95892

The uploaded TSV is byte-identical to the TSV inside the repository archive. It contains concrete records, not catalog metadata. However, its ATP-related target strings are SERCA/Na-K ATPase/other ATPase contexts, not F-type ATP synthase; therefore no BindingDB row is admitted to the ATP-target training stratum. It remains a broad external binding benchmark asset.

## Member 3 Part 2 — benchmark catalog

- Catalog entries: 26
- Executed benchmarks: 0
- Training records: 0

The 26 rows are metadata/catalog entries only.

## Integration decision

- Member 1: ATP-target literature registry and future primary-source verification; no automatic training labels.
- Member 2: Task-A MIC shadow experiment only, with scaffold/compound leakage controls and context preserved.
- Member 3 Part 1: broad binding external-validation registry; no direct ATP-target records in this file.
- Member 3 Part 2: Benchmark Registry only.

No evidence in this integration justifies replacing Model v3 or calling an external affinity/MIC record an internal candidate activity label.
