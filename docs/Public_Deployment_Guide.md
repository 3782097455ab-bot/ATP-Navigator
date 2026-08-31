# ATP-Navigator public deployment

## Public release

- Public URL: <https://jlu-atp-navigator.streamlit.app/>
- Visibility: public link access enabled
- Deployment branch: `main`
- Deployment commit: `4ded64115935da1bd3682315514d873ad5686b34`
- Public acceptance: anonymous HTTP session reached the app with status 200; the AI Research Console, Candidate Explorer, External Benchmark Registry, Protocol Comparison, Decision Workspace, 3D Structural Workspace, Team Review Board, Activity Timeline and Presentation Mode were opened without application or browser-console errors.

## Runtime

- Hosting target: Streamlit Community Cloud
- Python: 3.11
- Streamlit: 1.62.0
- RDKit: 2026.03.5
- Dependency source: repository-root `requirements.txt`
- Entrypoint: `streamlit_cloud_app.py` (executes the reviewed `app.py` as `__main__`)

The dependency set was resolved and import-tested in an isolated Python 3.11 environment, including `Chem`, `Draw` and `rdMolDraw2D`.

## Deployment mode

Hosted clones automatically enter `cloud_viewer`. The mode is fail-closed:

- registered and cached evidence can be queried;
- the AI console can form and explain plans;
- local WSL, Schrödinger, Vina, MM/GBSA, shell and long-running workers cannot execute;
- missing calculation capability is reported as `Execution backend unavailable in cloud_viewer`;
- no scientific value is simulated.

Local installations with the shared workspace Registry remain `local_full`, unless `ATP_NAVIGATOR_DEPLOYMENT_MODE` explicitly selects another mode.

## Public 3D asset

The hosted viewer contains one committed real demonstration case: 7P3W subunits e/g plus the registered rank-1 `vina_7p3w_v1` pose for `ATP-HTVS-18A7589C7FB7`. Pose and receptor hashes are recorded in `data/cloud_demo/pose_manifest.json`. The browser viewer supports rotation, zoom, reset and a 5 Å nearby-residue style. It remains a docking pose, not an experimental pose or MM/GBSA trajectory frame.
