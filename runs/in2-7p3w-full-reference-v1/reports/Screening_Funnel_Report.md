# Screening Funnel Report

| Stage | Status | Input | Output | Protocol | Runtime (s) |
|---|---:|---:|---:|---|---:|
| Target + IN-2 | completed_cached_prepared_assets | 1 | 1 | 7P3W_prepared_assets + confirmed_IN2 | 0.007727899996098131 |
| Library Generation | completed_cache_hit | 1 | 100000 | in2_reconstructed_library_v1 | 0.15377319999970496 |
| Filtering | completed_cache_hit | 100000 | 7265 | open_physchem_structural_filter_v1 | 0.12549960002070293 |
| Docking | blocked_by_resource_gate | 7265 | 0 | vina_7p3w_v1 | 0.0 |
| Refinement | not_run_upstream_resource_gate | 0 | 0 | acquisition_refinement_v1 | 0.0 |
| Open MM/GBSA | not_run_upstream_resource_gate | 0 | 0 | open_mmgbsa_7p3w_v2 | 0.0 |
| Evidence Integration | not_run_upstream_resource_gate | 0 | 0 | shared_evidence_registry | 0.0 |
| AI / Decision | not_run_upstream_resource_gate | 0 | 0 | computational_pre_experimental_v1 | 0.0 |
| Candidate Panel | not_run_upstream_resource_gate | 0 | 0 | computational_pre_experimental_v1 | 0.0 |

All hard-filter exclusions are retained in `filtering/filter_rejections.csv` with field, threshold, raw value, rationale and filter hash. No structure is silently removed.
