# DFSS Deep Sleep Demo

A demo of the **Depth-First Sparse Scheduling** pattern with checkpoint-and-exit.

The scheduler is itself a FlatMachine. Between batches it checkpoints and exits —
zero processes while idle. Signals wake it when work is ready.

This demo runs the **task runner machine** on sample seed tasks, showing how
tasks produce children and the tree fans out up to `max_depth`. No LLM calls —
all work is done in hooks.

## Key Concepts

- **Task Machine** — runs a single task via hook actions, outputs result + children
- **Scheduler Machine** — orchestrates batches with `wait_for` / checkpoint-and-exit
- **DeepSleepHooks** — implements `pick_batch`, `process_results`, `run_task`, `signal_ready`

## Prerequisites

1. **Python & `uv`**: Ensure you have Python 3.10+ and the `uv` package manager installed.

## Quick Start (with `run.sh`)

```bash
# Make the script executable (if you haven't already)
chmod +x run.sh

# Run the demo
./run.sh

# Or use local SDK sources
./run.sh --local
```

## Manual Setup

```bash
cd examples/dfss_deepsleep/python

uv venv
uv pip install -e .

uv run python -m flatagent_dfss_deepsleep.main
```

## Running Tests

```bash
cd examples/dfss_deepsleep
python -m pytest python/tests/unit/ -v
```
