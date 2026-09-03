# Screening Funnel Report

| Stage | Status | Input | Output | Protocol | Runtime (s) |
|---|---:|---:|---:|---|---:|
| Target + IN-2 | completed_cached_prepared_assets | 1 | 1 | 7P3W_prepared_assets + confirmed_IN2 | 0.009864299994660541 |
| Library Generation | completed_cache_hit | 1 | 100 | in2_reconstructed_library_v1 | 0.042698900011600927 |
| Filtering | completed_cache_hit | 100 | 7 | open_physchem_structural_filter_v1 | 0.003227400011382997 |
| Docking | completed | 7 | 7 | vina_7p3w_v1 | 0.2099432999966666 |
| Refinement | completed_selection_only | 7 | 1 | acquisition_refinement_v1 | 0.02992230001837015 |
| Open MM/GBSA | completed | 1 | 1 | open_mmgbsa_7p3w_v2 | 0.03930450000916608 |
| Evidence Integration | completed | 8 | 54 | shared_Evidence_Registry | 0.0 |
| AI / Decision | completed | 1 | 1 | computational_pre_experimental_v1 | 0.2570971999957692 |
| Candidate Panel | completed | 1 | 1 | computational_pre_experimental_v1 | 0.0 |

All hard-filter exclusions are retained in `filtering/filter_rejections.csv` with field, threshold, raw value, rationale and filter hash. No structure is silently removed.
