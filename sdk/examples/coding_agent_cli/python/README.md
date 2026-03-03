# Tool Use CLI Example

A coding agent with 4 tools — **read**, **write**, **bash**, **edit** — the same defaults as pi-mono. Includes human-in-the-loop review after each agent run.

## Recent Features

- **Bare prompt with readline** — Clean REPL interface with double ^C/^D to exit
- **Tool call visibility** — See agent thinking, tool calls, tokens used, and cost in real-time
- **Quiet by default** — Logs silenced via `LOG_LEVEL` env var for cleaner output
- **Human-in-the-loop review** — Approve or provide feedback on agent actions
- **Multiple execution modes** — REPL, single-shot, and standalone modes

## Tools

| Tool | Description |
|------|-------------|
| `read` | Read file contents with offset/limit, truncation at 2000 lines / 50KB |
| `bash` | Execute shell commands with timeout, tail-truncated output |
| `write` | Write/create files with automatic parent directory creation |
| `edit` | Surgical find-and-replace (exact match, single occurrence) |

## Quick Start (Play-by-Play)

### Step 1: Navigate to the project
```bash
cd sdk/examples/tool-use-cli/python
```

### Step 2: Run in interactive mode
```bash
./run.sh --local
```

### Step 3: Give the agent a task
```
> list all Python files in this repo
```

### Step 4: Watch the agent work
- Agent thinks about the task
- Agent calls tools (read, bash, write, edit)
- You see each tool call in real-time
- Output shows tokens used and cost

### Step 5: Review and approve
- Agent pauses after completing the task
- You see the results
- Type `approve` to accept, or give feedback to refine
- If feedback given, agent loops back to Step 3

### Step 6: Repeat or exit
- Type a new task to continue
- Press `^C` twice or `^D` to exit

## Usage Modes

```bash
cd sdk/examples/tool-use-cli/python

# Interactive REPL (default) — best for exploration
./run.sh --local

# Single-shot mode — run one task and exit
./run.sh --local -p "list all Python files in this repo"

# Standalone mode — no human review, runs to completion
./run.sh --local --standalone "what files are in the current directory?"

# Custom working directory
./run.sh --local -w /tmp/project -p "create a hello world Python script"
```

## Modes

### REPL (default)

Interactive loop. Type a task, agent executes with tool loop, pauses for human review. Approve or give feedback. Repeat.

### Single-shot (`-p "task"`)

Run one task, human review, exit. Useful for pipes.

### Standalone (`--standalone "task"`)

Uses `ToolLoopAgent` directly. No machine, no human review. Runs to completion and exits.

## Flow (machine mode)

```
┌─────────────────┐
│      start      │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│      work       │◄──────────┐
│  (tool loop)    │           │
└────────┬────────┘           │
         │                    │ feedback
         ▼                    │
┌─────────────────┐           │
│  human_review   │───────────┘
└────────┬────────┘
         │ approved
         ▼
┌─────────────────┐
│      done       │
└─────────────────┘
```

## Architecture

```
config/
  agent.yml       — Agent config with tool definitions + feedback handling
  machine.yml     — Machine with work → human_review → done loop
  profiles.yml    — Model profiles

python/src/tool_use_cli/
  tools.py        — Tool implementations (CLIToolProvider)
  hooks.py        — CLIToolHooks (tool provider, file tracking, human review action)
  main.py         — Entry point (REPL, -p single-shot, or --standalone)
```
