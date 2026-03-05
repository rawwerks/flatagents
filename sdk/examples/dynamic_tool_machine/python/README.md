# Dynamic Tool Machine

Single-machine / single-agent example of **machine-level tool calls** with self-launch.

Tool surface (2 tools):
- `discover_machines` — list registered machines and their running instances
- `launch_machine` — launch a new instance of a machine by name; no-op if one is already running

## How it works

Machines register themselves in an in-memory `MachineRegistry` (keyed by
machine name) on first tool call. An `InstanceTracker` records which
execution IDs are running per machine name.

When `launch_machine` targets a machine name, it resolves the config from
the registry, checks the tracker for existing instances, and either launches
a new one or reports that one is already running. The launched instance is a
peer — it sees the original the same way the original sees it, both tracked
as instances of the same machine name.

## Run

```bash
cd sdk/examples/dynamic_tool_machine/python
./run.sh --local
```

Single task:

```bash
./run.sh --local -p "Discover machines and launch if needed"
```
