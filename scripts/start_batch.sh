#!/usr/bin/env bash
# usage: scripts/start_batch.sh --years 2025 [other batch.py options]
# Refuses to start if a batch run is already going.
cd "$(dirname "$0")/.." || exit 1
if pgrep -f "batch\.py" >/dev/null; then
  echo "batch.py is already running:"
  pgrep -fl "batch\.py"
  exit 1
fi
mkdir -p logs
log="logs/batch_$(date +%Y%m%d_%H%M).log"
nohup caffeinate -i "$HOME/.venvs/f1-pitwall/bin/python" batch.py "$@" > "$log" 2>&1 &
echo "started pid $!, logging to $log"
