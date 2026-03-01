# Tool Use CLI Example

A coding agent with 4 tools — **read**, **write**, **bash**, **edit** — the same defaults as pi-mono. Includes human-in-the-loop review after each agent run. Demonstrates both FlatMachine (orchestrated) and standalone ToolLoopAgent modes.

## Tools

| Tool | Description |
|------|-------------|
| `read` | Read file contents with offset/limit, truncation at 2000 lines / 50KB |
| `bash` | Execute shell commands with timeout, tail-truncated output |
| `write` | Write/create files with automatic parent directory creation |
| `edit` | Surgical find-and-replace (exact match, single occurrence) |

## Flow

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

## Usage

```bash
cd sdk/examples/tool-use-cli/python

# Via run.sh (sets up venv, installs deps)
./run.sh --local "list all Python files in this repo"

# Or directly (if deps are installed)
python -m tool_use_cli.main "read README.md and summarize it"

# Standalone mode (ToolLoopAgent, no machine, no human review)
python -m tool_use_cli.main --standalone "what files are in the current directory?"

# Custom working directory
python -m tool_use_cli.main --working-dir /tmp/project "create a hello world Python script"
```

## Modes

### Machine Mode (default)

Uses `FlatMachine` with a `tool_loop` state + human review loop. Gets you:
- Per-tool-call hooks (`on_tool_calls`, `on_tool_result`)
- Checkpointing after every tool call
- Human-in-the-loop approval after each agent run
- Feedback loop — reject with feedback and the agent tries again
- File modification tracking via hooks

### Standalone Mode (`--standalone`)

Uses `ToolLoopAgent` directly. No machine, no human review. Gets you:
- Guardrails (turns, cost, timeout)
- Same tool implementations
- No hooks, checkpointing, or review loop

## Architecture

```
config/
  agent.yml       — Agent config with tool definitions + feedback handling
  machine.yml     — Machine with work → human_review → done loop
  profiles.yml    — Model profiles

python/src/tool_use_cli/
  tools.py        — Tool implementations (CLIToolProvider)
  hooks.py        — CLIToolHooks (tool provider, file tracking, human review action)
  main.py         — Entry point (machine or standalone mode)
```
