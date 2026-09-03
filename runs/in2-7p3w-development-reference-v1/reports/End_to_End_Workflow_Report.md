# IN-2 / 7P3W End-to-End Workflow Report

Target + IN-2 → reconstructed reproducible derivative library → open physicochemical/structural filtering → AutoDock Vina → evidence acquisition → Open MM/GBSA → Evidence Registry → computational pre-experimental candidate panel.

| Stage | Status | Input | Output | Protocol | Runtime (s) |
|---|---:|---:|---:|---|---:|
| Target + IN-2 | completed_cached_prepared_assets | 1 | 1 | 7P3W_prepared_assets + confirmed_IN2 | 0.008789199986495078 |
| Library Generation | completed_cache_hit | 1 | 1000 | in2_reconstructed_library_v1 | 0.04771489999257028 |
| Filtering | completed_cache_hit | 1000 | 62 | open_physchem_structural_filter_v1 | 0.0039607999788131565 |
| Docking | completed | 62 | 62 | vina_7p3w_v1 | 1.535029199993005 |
| Refinement | completed_selection_only | 62 | 2 | acquisition_refinement_v1 | 0.05357150000054389 |
| Open MM/GBSA | completed | 2 | 2 | open_mmgbsa_7p3w_v2 | 0.0589724000019487 |
| Evidence Integration | completed | 64 | 170 | shared_Evidence_Registry | 0.0 |
| AI / Decision | completed | 2 | 2 | computational_pre_experimental_v1 | 0.31145269999979064 |
| Candidate Panel | completed | 2 | 2 | computational_pre_experimental_v1 | 0.0 |

This run does not claim that the reconstructed library equals the historical 2024 Auto_Enum library. Vina is not Glide; Open MM/GBSA is not Prime MM/GBSA.
