# Clone Machine (Phase 1)

This example demonstrates:

1. Parent machine generates a **native Python tool implementation** each run.
2. Parent launches a **child machine in a subprocess**.
3. Child reconstructs and executes that generated tool from artifacts.

The generated tool is deterministic in phase 1 (template-based), but a new
artifact directory and run ID are created on every run.

## Layout

- Parent machine config: `../config/machine.yml`
- Child machine config: `../config/child_machine.yml`
- Parent provider: `src/clone_machine/tools.py` (`ParentToolProvider`)
- Child runner: `src/clone_machine/child_runner.py`

## Run

```bash
cd sdk/examples/dynamic_tool_machine/python
./run.sh --local
```

Output includes:
- generated `run_id`
- generated `tool_name`
- child subprocess execution ID
- child machine result using the generated tool

By default, generated artifacts are cleaned up after subprocess launch.
Set `CLONE_MACHINE_KEEP_ARTIFACTS=1` to retain artifacts for inspection.
