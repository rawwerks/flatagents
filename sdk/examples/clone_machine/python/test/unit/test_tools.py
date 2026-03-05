"""Unit tests for clone_machine action-hook snapshot cloning."""
from __future__ import annotations

from pathlib import Path

import pytest

from flatmachines import CheckpointManager, FlatMachine

from dynamic_tool_machine.hooks import CloneMachineHooks


def _config_path() -> str:
    return str(Path(__file__).resolve().parents[3] / "config" / "machine.yml")


@pytest.mark.asyncio
async def test_clone_action_requires_bound_machine():
    hooks = CloneMachineHooks()

    with pytest.raises(RuntimeError, match="bound"):
        await hooks.on_action("clone_machine", {})


@pytest.mark.asyncio
async def test_unknown_action_is_noop():
    hooks = CloneMachineHooks()

    machine = FlatMachine(config_file=_config_path(), hooks=hooks)
    hooks.bind_machine(machine)

    context = {"a": 1}
    out = await hooks.on_action("something_else", context)

    assert out == context


@pytest.mark.asyncio
async def test_machine_clones_pre_action_execute_snapshot():
    hooks = CloneMachineHooks()

    machine = FlatMachine(config_file=_config_path(), hooks=hooks)
    hooks.bind_machine(machine)

    result = await machine.execute(input={})

    assert result["status"] == "cloned"
    assert result["source_execution_id"] == machine.execution_id
    assert result["source_state"] == "clone"
    assert result["source_event"] == "execute"

    cloned_execution_id = result["cloned_execution_id"]
    assert cloned_execution_id.startswith(f"{machine.execution_id}:clone:")
    assert result["cloned_parent_execution_id"] == machine.execution_id


@pytest.mark.asyncio
async def test_cloned_snapshot_persisted_under_new_execution_id():
    hooks = CloneMachineHooks()

    machine = FlatMachine(config_file=_config_path(), hooks=hooks)
    hooks.bind_machine(machine)

    result = await machine.execute(input={})
    cloned_execution_id = result["cloned_execution_id"]

    manager = CheckpointManager(machine.persistence, cloned_execution_id)
    cloned = await manager.load_latest()

    assert cloned is not None
    assert cloned.execution_id == cloned_execution_id
    assert cloned.parent_execution_id == machine.execution_id
    assert cloned.event == "execute"
    assert cloned.current_state == "clone"


@pytest.mark.asyncio
async def test_clone_id_is_unique_per_run():
    hooks = CloneMachineHooks()

    machine = FlatMachine(config_file=_config_path(), hooks=hooks)
    hooks.bind_machine(machine)

    r1 = await machine.execute(input={})
    r2 = await machine.execute(input={})

    assert r1["cloned_execution_id"] != r2["cloned_execution_id"]
    # sanity: suffix looks like random hex chunk
    assert len(r1["cloned_execution_id"].split(":")[-1]) == 8
