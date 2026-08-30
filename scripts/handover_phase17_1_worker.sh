#!/usr/bin/env bash
set -euo pipefail

project="/mnt/d/tiaozhansai/ATP-Navigator"
python_bin="/home/lenovojlu/.local/share/atpnav/envs/atpnav-openmm/bin/python"
runtime="$project/workspace_local/phase17_1"
log="$runtime/background_worker.log"

mkdir -p "$runtime"
old_engine_pid="$(pgrep -o -f '[p]ython -m src.phase17_1.engine run --project /mnt/d/tiaozhansai/ATP-Navigator' || true)"
if [[ -z "$old_engine_pid" ]]; then
  echo "handover_blocked:no_existing_engine" >>"$log"
  exit 4
fi
printf '%s\n' "$old_engine_pid" >"$runtime/handover.old_engine_pid"
kill -TERM "$old_engine_pid"

# Preserve the calculation already in flight.  The old engine is terminated by
# this handover supervisor; only the active per-candidate worker is allowed to
# finish before the patched checkpointed engine is resumed.
while pgrep -f '[p]ython -m src.phase17_1.worker' >/dev/null 2>&1; do
  sleep 30
done

cd "$project"
exec "$python_bin" -m src.phase17_1.engine run --project "$project" >>"$log" 2>&1
