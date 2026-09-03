# Protocol and Tool Report

## Historical evidence route

The project PPT describes QuickProp, Glide HTVS/SP/XP, Prime MM/GBSA and Deep-PK. These records remain historical evidence and are not claimed as reconstructed executions.

## Reconstructed open route

- RDKit open physicochemical/structural filtering (`open_physchem_structural_filter_v1`); not QuickProp.
- AutoDock Vina (`vina_7p3w_v1`); not Glide HTVS/SP/XP.
- Acquisition selection (`acquisition_refinement_v1`); no fabricated second docking protocol.
- OpenMM + gmx_MMPBSA (`open_mmgbsa_7p3w_v2`); not Prime MM/GBSA and not experimental affinity.

`open_mmgbsa_7p3w_v2` uses the audited 7P3W e/g receptor scope, explicit TIP3P solvent, Amber ff14SB/GAFF 2.11, AM1-BCC charges and restrained short sampling. The membrane is omitted because no validated lipid coordinates are available; results are comparative screening-level evidence, not membrane-mechanism validation.
