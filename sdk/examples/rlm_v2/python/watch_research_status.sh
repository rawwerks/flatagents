#!/usr/bin/env bash
# Monitor running research_qa jobs and latest trace progress.
#
# Examples:
#   ./watch_research_status.sh
#   watch -n 2 ./watch_research_status.sh
#   ./watch_research_status.sh --watch --interval 2

set -euo pipefail

TRACE_DIR="./traces"
INTERVAL="2"
WATCH_MODE=false
ONCE=false

print_help() {
  cat <<'EOF'
watch_research_status.sh

Usage:
  ./watch_research_status.sh [options]

Options:
  --trace-dir <dir>   Trace directory (default: ./traces)
  --watch             Launch watch mode (same as: watch -n <interval> ...)
  --interval <sec>    Refresh interval for --watch (default: 2)
  --once              Internal flag used by --watch
  -h, --help          Show help

Examples:
  ./watch_research_status.sh
  watch -n 2 ./watch_research_status.sh
  ./watch_research_status.sh --watch --interval 1
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --trace-dir)
      TRACE_DIR="$2"
      shift 2
      ;;
    --watch)
      WATCH_MODE=true
      shift
      ;;
    --interval)
      INTERVAL="$2"
      shift 2
      ;;
    --once)
      ONCE=true
      shift
      ;;
    -h|--help)
      print_help
      exit 0
      ;;
    *)
      echo "Unknown arg: $1" >&2
      print_help
      exit 1
      ;;
  esac
done

if [[ "$WATCH_MODE" == true && "$ONCE" == false ]]; then
  if ! command -v watch >/dev/null 2>&1; then
    echo "Error: 'watch' command not found. Use manual loop or install watch." >&2
    exit 1
  fi
  printf -v CMD '%q --once --trace-dir %q' "$0" "$TRACE_DIR"
  exec watch -n "$INTERVAL" "$CMD"
fi

if [[ -x ".venv/bin/python" ]]; then
  PYTHON_BIN=".venv/bin/python"
else
  PYTHON_BIN="$(command -v python3 || command -v python)"
fi

echo "=== research_qa status | $(date '+%Y-%m-%d %H:%M:%S') ==="
echo "cwd: $(pwd)"
echo "trace_dir: $TRACE_DIR"
echo

echo "[Processes]"
PIDS_RAW="$(pgrep -f "rlm_v2.research_qa ask|research.sh ask|research.sh basic|research.sh fast|research.sh compare" || true)"
if [[ -z "$PIDS_RAW" ]]; then
  echo "none"
else
  PIDS_CSV="$(echo "$PIDS_RAW" | paste -sd, -)"
  ps -o pid,ppid,etime,%cpu,%mem,state,command -p "$PIDS_CSV"
fi

ASK_PID="$(pgrep -f ".venv/bin/python -m rlm_v2.research_qa ask" | head -n 1 || true)"
if [[ -n "$ASK_PID" ]]; then
  ASK_STATS="$(ps -p "$ASK_PID" -o etime=,%cpu=,%mem=,state= | awk '{print "elapsed=" $1 " cpu=" $2 " mem=" $3 " state=" $4}')"
  echo "primary_ask_pid: $ASK_PID | $ASK_STATS"
fi

echo

echo "[Latest trace]"
LATEST_TRACE="$(ls -td "$TRACE_DIR"/* 2>/dev/null | head -n 1 || true)"
if [[ -z "$LATEST_TRACE" ]]; then
  echo "none"
  exit 0
fi

echo "path: $LATEST_TRACE"
MANIFEST_PATH="$LATEST_TRACE/manifest.json"
EVENTS_PATH="$LATEST_TRACE/events.jsonl"

"$PYTHON_BIN" - "$MANIFEST_PATH" "$EVENTS_PATH" <<'PY'
import json
import os
import sys
import time
from collections import Counter, defaultdict

manifest_path = sys.argv[1]
events_path = sys.argv[2]
max_depth_allowed = None
max_iterations_allowed = None

if os.path.exists(manifest_path):
    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)
    inp = manifest.get("input", {})
    limits = manifest.get("limits", {})
    task = inp.get("task", "")
    question = ""
    marker = "Question:"
    i = task.rfind(marker)
    if i != -1:
        question = task[i + len(marker):].strip()

    max_depth_allowed = limits.get("max_depth")
    max_iterations_allowed = limits.get("max_iterations")

    print(f"created_at: {manifest.get('created_at')}")
    print(f"context_length: {inp.get('long_context_length')}")
    print(f"limits: max_iterations={max_iterations_allowed} | max_depth={max_depth_allowed}")
    if question:
        print(f"question: {question}")
else:
    print("manifest: missing")

if not os.path.exists(events_path):
    print("events: missing")
    sys.exit(0)

rows = []
with open(events_path, "r", encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if line:
            rows.append(json.loads(line))

print(f"events_count: {len(rows)}")
if not rows:
    sys.exit(0)

last = rows[-1]
print(f"last_event: {last.get('event')} | depth={last.get('depth')} | iter={last.get('iteration')}")

# elapsed + staleness
first_ts = rows[0].get("ts")
last_ts = rows[-1].get("ts")
if isinstance(first_ts, (int, float)) and isinstance(last_ts, (int, float)):
    print(f"trace_elapsed_sec: {last_ts - first_ts:.1f}")
    print(f"seconds_since_last_event: {time.time() - last_ts:.1f}")

# depth / iteration progress
depths = [r.get("depth") for r in rows if isinstance(r.get("depth"), int)]
max_depth_seen = max(depths) if depths else None
root_iters = [r.get("iteration") for r in rows if r.get("event") == "iteration_start" and r.get("depth") == 0 and isinstance(r.get("iteration"), int)]
root_iter_max = max(root_iters) if root_iters else 0

iter_by_depth = defaultdict(int)
for r in rows:
    if r.get("event") == "iteration_start" and isinstance(r.get("depth"), int) and isinstance(r.get("iteration"), int):
        d = r["depth"]
        iter_by_depth[d] = max(iter_by_depth[d], r["iteration"])

print(
    "progress: "
    f"max_depth_seen={max_depth_seen}"
    + (f"/{max_depth_allowed}" if max_depth_allowed is not None else "")
    + " | "
    f"root_iter={root_iter_max}"
    + (f"/{max_iterations_allowed}" if max_iterations_allowed is not None else "")
)
if iter_by_depth:
    depth_parts = [f"d{d}={iter_by_depth[d]}" for d in sorted(iter_by_depth)]
    print("iters_by_depth: " + ", ".join(depth_parts))

counts = Counter(r.get("event") for r in rows)
focus = ["run_start", "iteration_start", "subcall_start", "subcall_end", "final_detected", "run_end", "error"]
parts = [f"{k}={counts.get(k, 0)}" for k in focus if counts.get(k, 0) > 0]
if parts:
    print("event_summary: " + ", ".join(parts))

sub_ends = [r for r in rows if r.get("event") == "subcall_end"]
status_counts = Counter(r.get("status") for r in sub_ends)
inflight = counts.get("subcall_start", 0) - counts.get("subcall_end", 0)
if sub_ends or counts.get("subcall_start", 0):
    status_bits = ", ".join(f"{k}={v}" for k, v in sorted(status_counts.items()) if k)
    print(f"subcalls: started={counts.get('subcall_start', 0)} ended={counts.get('subcall_end', 0)} inflight={inflight}" + (f" | {status_bits}" if status_bits else ""))

print("tail:")
for r in rows[-5:]:
    ev = r.get("event")
    depth = r.get("depth")
    it = r.get("iteration")
    extra = ""
    if ev == "subcall_end":
        extra = f" status={r.get('status')}"
    elif ev == "run_end":
        extra = f" reason={r.get('reason')}"
    elif ev == "llm_response":
        extra = f" resp_len={r.get('response_length')}"
    print(f"  - {ev} depth={depth} iter={it}{extra}")
PY
