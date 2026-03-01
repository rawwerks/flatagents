# Tool Use CLI Example

A coding agent with 4 tools — **read**, **write**, **bash**, **edit** — the same defaults as pi-mono. Includes human-in-the-loop review after each agent run.

## Tools

| Tool | Description |
|------|-------------|
| `read` | Read file contents with offset/limit, truncation at 2000 lines / 50KB |
| `bash` | Execute shell commands with timeout, tail-truncated output |
| `write` | Write/create files with automatic parent directory creation |
| `edit` | Surgical find-and-replace (exact match, single occurrence) |

## Usage

```bash
cd sdk/examples/tool-use-cli/python

# Default: interactive REPL
./run.sh --local

# Single-shot mode (-p / --print)
./run.sh --local -p "list all Python files in this repo"

# Standalone mode (ToolLoopAgent, no machine, no human review)
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
