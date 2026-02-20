"""
Unit tests for "the machine is the job" features:

1. Lock + persistence propagation to peer machines
2. list_execution_ids(event=...) filtering
3. CheckpointManager.load_status() lightweight peek
"""

import json
import os
import shutil
import pytest

from flatmachines import (
    LocalFileBackend,
    MemoryBackend,
    SQLiteCheckpointBackend,
    CheckpointManager,
    MachineSnapshot,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def cleanup():
    for d in [".checkpoints"]:
        if os.path.exists(d):
            shutil.rmtree(d)
    yield
    for d in [".checkpoints"]:
        if os.path.exists(d):
            shutil.rmtree(d)


@pytest.fixture(params=["local", "memory", "sqlite"])
def backend(request, tmp_path):
    if request.param == "local":
        return LocalFileBackend()
    elif request.param == "sqlite":
        return SQLiteCheckpointBackend(db_path=str(tmp_path / "test.sqlite"))
    return MemoryBackend()


async def _save_snapshot(backend, execution_id, event="state_exit", current_state="running", step=1):
    """Save a realistic snapshot through CheckpointManager."""
    manager = CheckpointManager(backend, execution_id)
    snapshot = MachineSnapshot(
        execution_id=execution_id,
        machine_name="test-machine",
        spec_version="1.1.1",
        current_state=current_state,
        context={"some": "data"},
        step=step,
        event=event,
    )
    await manager.save_checkpoint(snapshot)
    return snapshot


# ---------------------------------------------------------------------------
# Part 3a: list_execution_ids with event filtering
# ---------------------------------------------------------------------------

class TestListExecutionIdsFiltered:

    @pytest.mark.asyncio
    async def test_filter_by_event(self, backend):
        """list_execution_ids(event='machine_end') returns only completed."""
        await _save_snapshot(backend, "done-1", event="machine_end", current_state="final")
        await _save_snapshot(backend, "running-1", event="state_exit", current_state="step_2")
        await _save_snapshot(backend, "done-2", event="machine_end", current_state="final")

        completed = await backend.list_execution_ids(event="machine_end")
        assert set(completed) == {"done-1", "done-2"}

    @pytest.mark.asyncio
    async def test_filter_no_match(self, backend):
        """Filter returns empty when no executions match."""
        await _save_snapshot(backend, "running-1", event="state_exit")
        assert await backend.list_execution_ids(event="machine_end") == []

    @pytest.mark.asyncio
    async def test_filter_none_returns_all(self, backend):
        """event=None returns all execution IDs (backward compat)."""
        await _save_snapshot(backend, "a", event="machine_end")
        await _save_snapshot(backend, "b", event="state_exit")
        assert set(await backend.list_execution_ids()) == {"a", "b"}
        assert set(await backend.list_execution_ids(event=None)) == {"a", "b"}

    @pytest.mark.asyncio
    async def test_incomplete_is_set_difference(self, backend):
        """Incomplete = all IDs minus machine_end IDs."""
        await _save_snapshot(backend, "done", event="machine_end")
        await _save_snapshot(backend, "stuck", event="state_exit")
        await _save_snapshot(backend, "new", event="machine_start")

        all_ids = set(await backend.list_execution_ids())
        done_ids = set(await backend.list_execution_ids(event="machine_end"))
        incomplete = all_ids - done_ids
        assert incomplete == {"stuck", "new"}


# ---------------------------------------------------------------------------
# Part 3b: CheckpointManager.load_status()
# ---------------------------------------------------------------------------

class TestLoadStatus:

    @pytest.mark.asyncio
    async def test_returns_event_and_state(self, backend):
        await _save_snapshot(backend, "exec-1", event="state_exit", current_state="step_2")
        manager = CheckpointManager(backend, "exec-1")
        status = await manager.load_status()
        assert status is not None
        event, state = status
        assert event == "state_exit"
        assert state == "step_2"

    @pytest.mark.asyncio
    async def test_returns_none_for_missing(self, backend):
        manager = CheckpointManager(backend, "nonexistent")
        assert await manager.load_status() is None

    @pytest.mark.asyncio
    async def test_completed_execution(self, backend):
        await _save_snapshot(backend, "exec-1", event="machine_end", current_state="done")
        manager = CheckpointManager(backend, "exec-1")
        status = await manager.load_status()
        assert status == ("machine_end", "done")

    @pytest.mark.asyncio
    async def test_reflects_latest_checkpoint(self, backend):
        """load_status returns state from the most recent checkpoint."""
        await _save_snapshot(backend, "exec-1", event="state_exit", current_state="step_1", step=1)
        await _save_snapshot(backend, "exec-1", event="state_exit", current_state="step_3", step=2)
        manager = CheckpointManager(backend, "exec-1")
        status = await manager.load_status()
        assert status == ("state_exit", "step_3")

    @pytest.mark.asyncio
    async def test_cheaper_than_load_latest(self, backend):
        """load_status should work without deserializing full context.

        We verify it returns correct values — the 'cheaper' aspect is
        an implementation detail (SQLite reads indexed columns only).
        """
        await _save_snapshot(backend, "exec-1", event="machine_end", current_state="final")
        manager = CheckpointManager(backend, "exec-1")

        status = await manager.load_status()
        full = await manager.load_latest()

        assert status is not None
        assert full is not None
        assert status == (full.event, full.current_state)


# ---------------------------------------------------------------------------
# Part 3c: Lock + persistence propagation to peer machines
# ---------------------------------------------------------------------------

class TestPeerPropagation:

    @pytest.mark.asyncio
    async def test_launch_and_write_propagates_persistence(self):
        """Peer machine created by _launch_and_write inherits parent's persistence + lock."""
        from flatmachines import FlatMachine
        from unittest.mock import patch, AsyncMock

        child_config = {
            "spec": "flatmachine",
            "spec_version": "1.1.1",
            "data": {
                "name": "child",
                "context": {},
                "states": {
                    "start": {
                        "type": "initial",
                        "transitions": [{"to": "done"}],
                    },
                    "done": {"type": "final"},
                },
            },
        }
        config = {
            "spec": "flatmachine",
            "spec_version": "1.1.1",
            "data": {
                "name": "parent",
                "machines": {"child": child_config},
                "context": {},
                "states": {
                    "start": {
                        "type": "initial",
                        "machine": "child",
                        "transitions": [{"to": "done"}],
                    },
                    "done": {"type": "final"},
                },
            },
        }

        backend = MemoryBackend()
        parent = FlatMachine(config_dict=config, persistence=backend)

        # Capture the peer FlatMachine instance created inside _launch_and_write
        created_peers = []
        original_init = FlatMachine.__init__

        def capturing_init(self, *args, **kwargs):
            original_init(self, *args, **kwargs)
            if self.data.get("name") == "child":
                created_peers.append(self)

        with patch.object(FlatMachine, "__init__", capturing_init):
            try:
                await parent._launch_and_write("child", "child-001", {})
            except Exception:
                pass  # child execution may fail — we only care about construction

        assert len(created_peers) == 1, "Peer machine was not created"
        peer = created_peers[0]
        assert peer.persistence is backend, (
            "_launch_and_write does not propagate persistence to peer"
        )
        assert peer.lock is parent.lock, (
            "_launch_and_write does not propagate lock to peer"
        )
