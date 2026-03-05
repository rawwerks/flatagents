# Clone Machine (No LLM)

This example demonstrates deterministic snapshot cloning via a single machine action.

## Behavior

- Machine has one action state: `clone_machine`
- No `agent`, no `tool_loop`, no model calls
- The action loads the **pre-action checkpoint** (latest event must be `execute`)
- It clones that snapshot to a new execution ID via `flatmachines.clone_snapshot(...)`

## Files

- Machine config: `../config/machine.yml`
- Hook action implementation: `src/dynamic_tool_machine/hooks.py` (`CloneMachineHooks`)
- Entry point: `src/dynamic_tool_machine/main.py`

## Run

```bash
cd sdk/examples/clone_machine/python
./run.sh --local
```

Output includes source execution ID/event and cloned execution ID.
