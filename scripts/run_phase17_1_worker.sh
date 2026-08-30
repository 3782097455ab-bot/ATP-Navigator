#!/usr/bin/env bash
set -euo pipefail

project="/mnt/d/tiaozhansai/ATP-Navigator"
python_bin="/home/lenovojlu/.local/share/atpnav/envs/atpnav-openmm/bin/python"
runtime="$project/workspace_local/phase17_1"
log="$runtime/background_worker.log"
pid_file="$runtime/background_worker.pid"
pattern="$python_bin -m src.phase17_1.engine run --project $project"

mkdir -p "$runtime"

if pgrep -f "$pattern" >/dev/null 2>&1; then
  echo "duplicate_worker_blocked"
  pgrep -af "$pattern"
  exit 3
fi

cd "$project"
nohup "$python_bin" -m src.phase17_1.engine run --project "$project" \
  >>"$log" 2>&1 </dev/null &
worker_pid=$!
printf '%s\n' "$worker_pid" >"$pid_file"
echo "started_pid=$worker_pid"
echo "log=$log"
