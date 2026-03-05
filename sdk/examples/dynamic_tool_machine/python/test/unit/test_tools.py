"""Unit tests for MachineRegistry, InstanceTracker, and DynamicMachineToolProvider."""
from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from dynamic_tool_machine.tools import (
    DynamicMachineToolProvider,
    InstanceTracker,
    MachineRegistry,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

MACHINE_NAME = "dynamic-tool-machine"

MINIMAL_CONFIG = {
    "spec": "flatmachine",
    "spec_version": "2.0.0",
    "data": {
        "name": MACHINE_NAME,
        "context": {"task": "{{ input.task }}"},
        "agents": {},
        "states": {
            "start": {"type": "initial", "transitions": [{"to": "done"}]},
            "done": {"type": "final", "output": {}},
        },
    },
}


def _fake_machine(execution_id: str = "exec-aaa", name: str = MACHINE_NAME):
    """Return an object that quacks enough like FlatMachine for the provider."""
    return SimpleNamespace(
        execution_id=execution_id,
        machine_name=name,
        config=MINIMAL_CONFIG,
        _config_dir="/tmp/fake",
        _profiles_dict=None,
        _profiles_file=None,
    )


# ---------------------------------------------------------------------------
# MachineRegistry
# ---------------------------------------------------------------------------

class TestMachineRegistry:

    def test_register_and_list(self):
        reg = MachineRegistry()
        reg.register("m1", {"spec": "flatmachine"}, "/d1")
        reg.register("m2", {"spec": "flatmachine"}, "/d2")
        assert reg.list_machines() == ["m1", "m2"]

    def test_get_returns_config(self):
        reg = MachineRegistry()
        cfg = {"spec": "flatmachine", "data": {}}
        reg.register("m1", cfg, "/d1")
        assert reg.get("m1") is cfg

    def test_get_unknown_returns_none(self):
        reg = MachineRegistry()
        assert reg.get("nope") is None

    def test_profiles_round_trip(self):
        reg = MachineRegistry()
        reg.register("m1", {}, "/d", profiles_dict={"fast": {}}, profiles_file="/p.yml")
        d, f = reg.get_profiles("m1")
        assert d == {"fast": {}}
        assert f == "/p.yml"

    def test_profiles_default(self):
        reg = MachineRegistry()
        d, f = reg.get_profiles("missing")
        assert d is None and f is None


# ---------------------------------------------------------------------------
# InstanceTracker
# ---------------------------------------------------------------------------

class TestInstanceTracker:

    @pytest.mark.asyncio
    async def test_add_and_count(self):
        t = InstanceTracker()
        await t.add("m1", "a")
        await t.add("m1", "b")
        assert await t.count("m1") == 2

    @pytest.mark.asyncio
    async def test_remove(self):
        t = InstanceTracker()
        await t.add("m1", "a")
        await t.add("m1", "b")
        await t.remove("m1", "a")
        assert await t.get_instances("m1") == ["b"]

    @pytest.mark.asyncio
    async def test_remove_last_cleans_up(self):
        t = InstanceTracker()
        await t.add("m1", "a")
        await t.remove("m1", "a")
        assert await t.count("m1") == 0
        assert await t.get_instances("m1") == []

    @pytest.mark.asyncio
    async def test_remove_nonexistent_is_safe(self):
        t = InstanceTracker()
        await t.remove("m1", "ghost")  # no error

    @pytest.mark.asyncio
    async def test_get_instances_sorted(self):
        t = InstanceTracker()
        await t.add("m1", "ccc")
        await t.add("m1", "aaa")
        await t.add("m1", "bbb")
        assert await t.get_instances("m1") == ["aaa", "bbb", "ccc"]


# ---------------------------------------------------------------------------
# DynamicMachineToolProvider — discover_machines
# ---------------------------------------------------------------------------

class TestDiscoverMachines:

    @pytest.mark.asyncio
    async def test_discover_returns_self(self):
        reg = MachineRegistry()
        tracker = InstanceTracker()
        provider = DynamicMachineToolProvider(registry=reg, tracker=tracker)
        provider.bind_machine(_fake_machine("exec-111"))

        result = await provider.execute_tool("discover_machines", "tc1", {})

        data = json.loads(result.content)
        assert data["self_name"] == MACHINE_NAME
        assert data["self_id"] == "exec-111"[:12]
        # Machine should be registered in the registry now
        assert MACHINE_NAME in data["machines"]

    @pytest.mark.asyncio
    async def test_discover_shows_all_instances(self):
        reg = MachineRegistry()
        tracker = InstanceTracker()

        p1 = DynamicMachineToolProvider(registry=reg, tracker=tracker)
        p1.bind_machine(_fake_machine("exec-aaa"))
        await p1.execute_tool("discover_machines", "tc1", {})

        # Manually add a second instance to the tracker
        await tracker.add(MACHINE_NAME, "exec-bbb")

        result = await p1.execute_tool("discover_machines", "tc2", {})
        data = json.loads(result.content)
        assert data["machines"][MACHINE_NAME]["running"] == 2

    @pytest.mark.asyncio
    async def test_not_bound_returns_error(self):
        reg = MachineRegistry()
        tracker = InstanceTracker()
        provider = DynamicMachineToolProvider(registry=reg, tracker=tracker)
        # Never called bind_machine

        result = await provider.execute_tool("discover_machines", "tc1", {})
        assert result.is_error is True

    @pytest.mark.asyncio
    async def test_unknown_tool_returns_error(self):
        reg = MachineRegistry()
        tracker = InstanceTracker()
        provider = DynamicMachineToolProvider(registry=reg, tracker=tracker)
        provider.bind_machine(_fake_machine())

        result = await provider.execute_tool("nonexistent", "tc1", {})
        assert result.is_error is True
        assert "Unknown tool" in result.content


# ---------------------------------------------------------------------------
# DynamicMachineToolProvider — launch_machine
# ---------------------------------------------------------------------------

class TestLaunchMachine:

    @pytest.mark.asyncio
    async def test_launch_missing_target_returns_error(self):
        reg = MachineRegistry()
        tracker = InstanceTracker()
        provider = DynamicMachineToolProvider(registry=reg, tracker=tracker)
        provider.bind_machine(_fake_machine())

        result = await provider.execute_tool("launch_machine", "tc1", {})
        assert result.is_error is True
        assert "target" in result.content.lower()

    @pytest.mark.asyncio
    async def test_launch_unknown_target_returns_error(self):
        reg = MachineRegistry()
        tracker = InstanceTracker()
        provider = DynamicMachineToolProvider(registry=reg, tracker=tracker)
        provider.bind_machine(_fake_machine())

        # ensure_registered so discover works
        await provider.execute_tool("discover_machines", "tc0", {})

        result = await provider.execute_tool("launch_machine", "tc1", {"target": "no-such-machine"})
        assert result.is_error is True
        assert "Unknown machine" in result.content

    @pytest.mark.asyncio
    async def test_launch_self_when_no_other_instance(self):
        """Launching self when no other instance exists should return 'launched'."""
        reg = MachineRegistry()
        tracker = InstanceTracker()
        provider = DynamicMachineToolProvider(registry=reg, tracker=tracker)
        provider.bind_machine(_fake_machine("exec-original"))

        # Register via discover
        await provider.execute_tool("discover_machines", "tc0", {})

        # Patch FlatMachine so we don't actually run a real machine
        with patch("dynamic_tool_machine.tools.FlatMachine") as MockFM:
            mock_instance = MockFM.return_value
            mock_instance.machine_name = MACHINE_NAME
            mock_instance.execution_id = "exec-launched"
            mock_instance.config = MINIMAL_CONFIG
            mock_instance._config_dir = "/tmp/fake"
            mock_instance._profiles_dict = None
            mock_instance._profiles_file = None

            import asyncio
            mock_instance.execute = lambda **kw: asyncio.coroutine(lambda: {"result": "ok"})()

            result = await provider.execute_tool(
                "launch_machine", "tc1", {"target": MACHINE_NAME}
            )

        data = json.loads(result.content)
        assert data["status"] == "launched"
        assert data["target"] == MACHINE_NAME
        assert data["total_running"] == 2  # original + launched

    @pytest.mark.asyncio
    async def test_launch_self_when_other_instance_exists(self):
        """Launching self when another instance already runs returns 'already_running'."""
        reg = MachineRegistry()
        tracker = InstanceTracker()
        provider = DynamicMachineToolProvider(registry=reg, tracker=tracker)
        provider.bind_machine(_fake_machine("exec-original"))

        # Register via discover
        await provider.execute_tool("discover_machines", "tc0", {})

        # Simulate another instance already in the tracker
        await tracker.add(MACHINE_NAME, "exec-other")

        result = await provider.execute_tool(
            "launch_machine", "tc1", {"target": MACHINE_NAME}
        )

        data = json.loads(result.content)
        assert data["status"] == "already_running"
        assert data["target"] == MACHINE_NAME


# ---------------------------------------------------------------------------
# Symmetry: both instances see the same machine name
# ---------------------------------------------------------------------------

class TestSymmetry:

    @pytest.mark.asyncio
    async def test_both_instances_see_same_machine_name(self):
        """After launch, both the original and the launched instance
        discover themselves under the same machine name."""
        reg = MachineRegistry()
        tracker = InstanceTracker()

        # Original
        p1 = DynamicMachineToolProvider(registry=reg, tracker=tracker)
        p1.bind_machine(_fake_machine("exec-original"))
        await p1.execute_tool("discover_machines", "tc0", {})

        # Simulate the launched instance (same registry/tracker, different execution_id)
        p2 = DynamicMachineToolProvider(registry=reg, tracker=tracker)
        p2.bind_machine(_fake_machine("exec-launched"))
        await p2.execute_tool("discover_machines", "tc0", {})

        # Both should see 2 instances under the same machine name
        r1 = await p1.execute_tool("discover_machines", "tc1", {})
        r2 = await p2.execute_tool("discover_machines", "tc2", {})

        d1 = json.loads(r1.content)
        d2 = json.loads(r2.content)

        # Same machine name in both
        assert d1["self_name"] == MACHINE_NAME
        assert d2["self_name"] == MACHINE_NAME

        # Both see 2 running instances
        assert d1["machines"][MACHINE_NAME]["running"] == 2
        assert d2["machines"][MACHINE_NAME]["running"] == 2

        # Each sees the other's ID in the instance list
        ids_1 = set(d1["machines"][MACHINE_NAME]["instance_ids"])
        ids_2 = set(d2["machines"][MACHINE_NAME]["instance_ids"])
        assert ids_1 == ids_2
        assert "exec-original"[:12] in ids_1
        assert "exec-launched"[:12] in ids_1

    @pytest.mark.asyncio
    async def test_launched_instance_also_blocked_from_launching(self):
        """The launched instance also gets 'already_running' if it tries
        to launch, since the original is still tracked."""
        reg = MachineRegistry()
        tracker = InstanceTracker()

        # Original registers
        p1 = DynamicMachineToolProvider(registry=reg, tracker=tracker)
        p1.bind_machine(_fake_machine("exec-original"))
        await p1.execute_tool("discover_machines", "tc0", {})

        # Launched instance registers
        p2 = DynamicMachineToolProvider(registry=reg, tracker=tracker)
        p2.bind_machine(_fake_machine("exec-launched"))
        await p2.execute_tool("discover_machines", "tc0", {})

        # Launched tries to launch another — should be blocked
        result = await p2.execute_tool(
            "launch_machine", "tc1", {"target": MACHINE_NAME}
        )
        data = json.loads(result.content)
        assert data["status"] == "already_running"

    @pytest.mark.asyncio
    async def test_after_deregister_launch_allowed_again(self):
        """Once an instance deregisters, the remaining one can launch again."""
        reg = MachineRegistry()
        tracker = InstanceTracker()

        p1 = DynamicMachineToolProvider(registry=reg, tracker=tracker)
        p1.bind_machine(_fake_machine("exec-original"))
        await p1.execute_tool("discover_machines", "tc0", {})

        p2 = DynamicMachineToolProvider(registry=reg, tracker=tracker)
        p2.bind_machine(_fake_machine("exec-launched"))
        await p2.execute_tool("discover_machines", "tc0", {})

        # Launched deregisters (simulating completion)
        await p2._deregister()

        assert await tracker.count(MACHINE_NAME) == 1

        # Original can now launch again
        with patch("dynamic_tool_machine.tools.FlatMachine") as MockFM:
            mock_instance = MockFM.return_value
            mock_instance.machine_name = MACHINE_NAME
            mock_instance.execution_id = "exec-new"
            mock_instance.config = MINIMAL_CONFIG
            mock_instance._config_dir = "/tmp/fake"
            mock_instance._profiles_dict = None
            mock_instance._profiles_file = None

            import asyncio
            mock_instance.execute = lambda **kw: asyncio.coroutine(lambda: {"result": "ok"})()

            result = await p1.execute_tool(
                "launch_machine", "tc1", {"target": MACHINE_NAME}
            )

        data = json.loads(result.content)
        assert data["status"] == "launched"
