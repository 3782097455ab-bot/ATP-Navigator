#!/usr/bin/env bash
set -euo pipefail

project="/mnt/d/tiaozhansai/ATP-Navigator"
python_bin="/home/lenovojlu/.local/share/atpnav/envs/atpnav-openmm/bin/python"
runtime="$project/workspace_local/phase17_1"
log="$runtime/background_worker.log"

mkdir -p "$runtime"
cd "$project"
exec "$python_bin" -m src.phase17_1.engine run --project "$project" >>"$log" 2>&1
