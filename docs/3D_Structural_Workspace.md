# 3D Structural Workspace

## What is displayed

The browser viewer uses 3Dmol.js to display:

- the registered 7P3W receptor used by the frozen `vina_7p3w_v1` protocol;
- a registered rank-1 ligand pose;
- receptor cartoon, ligand sticks/spheres and residues within 5 Å;
- candidate, protocol, affinity, pose-QC and provenance metadata.

## Pose provenance

`src/agent/structure_viewer.py` resolves pose files through `PoseRegistry`. It verifies the registered artifact hash before rendering. Supported sources are Phase 14 HTVS Vina poses, Phase 16 generated-candidate Vina poses and compatible registered internal poses.

If no registered pose is available, the UI displays a missing state. It never creates a pose merely to fill the viewer.

## Scientific boundary

- A Vina pose is not an Open-MM/GBSA trajectory pose.
- The 7P3W Vina receptor scope (subunits e/g) is not automatically asserted to be a complete membrane simulation system.
- Visual proximity is not an experimentally confirmed interaction.
- Protocol-specific poses are not merged as if equivalent.

The viewer is an audit and interpretation aid, not a new scoring model.

