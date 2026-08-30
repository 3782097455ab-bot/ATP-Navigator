# ATP-Navigator Competition Release Candidate

## Release boundary

ATP-Navigator remains an AI-assisted candidate-priority decision system positioned after virtual screening and before experimental selection. It integrates registered computational evidence; it does not claim biological activity or experimental success probability.

## Member data

- Member 1: 39 literature rows, 8 unique valid structures, 0 exact training-eligible ATP-synthase records.
- Member 2: 310 MIC rows, 19 unique structures, all 19 structures already overlap External Dataset v2; the new value is strain/resistance assay context.
- Member 3 Part 1: 93712 BindingDB rows / 96195 endpoint measurements; 0 direct ATP-synthase records in this supplied file.
- Member 3 Part 2: 26 benchmark catalog entries; catalog only, not executed results.

## Shadow promotion gate

- Task-A baseline RMSE: 0.7923; member-context shadow RMSE: 0.8044.
- Task-A baseline Spearman: 0.7628; shadow Spearman: 0.7536.
- Bootstrap 95% interval for RMSE(new-old): [0.00046907437439047683, 0.024020308690672065].
- Promotion gate: **not passed**. Model v3 remains the official candidate ranker. The MIC shadow is a different task and did not improve its own fixed scaffold benchmark.

## Phase17.1 evidence integration

- 30 candidates have real Open MM/GBSA results; 60 evidence records are registered.
- 24 candidates have exact three-protocol comparisons.
- The Release Candidate Decision Run is a new shadow evidence run and does not overwrite historical Decision outputs.
- Top-5 pre/post overlap: 4/5; median absolute rank change: 3.0.
- Largest change: ATP-HTVS-66618B00A972.

## Frozen assets

- Official supervised model: Model v3.
- Protected model hashes: 24/24 unchanged.
- Release manifest: `results/release_candidate/competition_rc_manifest.json`.
