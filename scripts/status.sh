#!/usr/bin/env bash
# One-screen status of the ingestion: what is running, how far it got, what is queued.
cd "$(dirname "$0")/.." || exit 1

echo "== RUNNING =="
if pgrep -f 'batch\.py|start_batch' >/dev/null; then
  ps -axo pid,etime,command | grep -E 'batch\.py|start_batch' | grep -v grep | cut -c1-170
else
  echo "(nothing running)"
fi

echo
echo "== LATEST LOG =="
log="$(ls -t logs/batch_2*.log 2>/dev/null | head -1)"
echo "$log"
grep -E '^plan' "$log" | tail -n 1
grep -E '^progress' "$log" | tail -n 1
grep -E '^20[0-9]{2} .*: (OK|PARTIAL|FAILED)' "$log" | tail -n 1
grep -E 'rate limited; waiting' "$log" | tail -n 1
grep -E 'this run' "$log" | tail -n 1

echo
echo "== QUEUE =="
if [ -s logs/queue.log ]; then tail -n 3 logs/queue.log; else echo "(logs/queue.log is empty: the queue is still waiting, or was never started)"; fi

echo
echo "== DATA IN THE LAKE =="
"$HOME/.venvs/f1-pitwall/bin/python" report.py 2>/dev/null | awk '/^PROBLEMS/{exit} {print}'
df -h . | tail -n 1
