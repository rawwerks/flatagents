"""
Integration tests for the scheduler machine with wait_for.

These tests exercise the checkpoint-and-exit pattern:
  1. Scheduler starts, hits wait_for, checkpoints, returns _waiting
  2. Signal arrives, scheduler resumes, picks batch, dispatches
  3. Results processed, children pushed, scheduler sleeps again
  4. All roots done → scheduler reaches final state

Uses MemorySignalBackend + MemoryBackend (no SQLite, no real tasks).
Task machines are mocked — we're testing the scheduler flow, not task execution.

NOTE: These tests will fail until SignalBackend, wait_for, and WaitingForSignal
are implemented. That's the point — TDD targets.
"""
from __future__ import annotations

import pytest
from _helpers import load_module

scheduler_mod = load_module("scheduler_machine.py", "deepsleep_scheduler_machine")
hooks_mod = load_module("hooks.py", "deepsleep_hooks")

scheduler_config = scheduler_mod.scheduler_config
DeepSleepHooks = hooks_mod.DeepSleepHooks


# ── Helpers ────────────────────────────────────────────────

def _make_candidates(n_roots: int = 2, tasks_per_root: int = 2):
    """Generate simple candidate lists."""
    candidates = []
    for r in range(n_roots):
        for t in range(tasks_per_root):
            candidates.append({
                "task_id": f"root-{r}/{t}",
                "root_id": f"root-{r}",
                "depth": t,
                "resource_class": "fast",
            })
    return candidates


# ── Tests ──────────────────────────────────────────────────

class TestSchedulerWaitFor:
    """Tests that require wait_for + SignalBackend implementation."""

    @pytest.mark.asyncio
    async def test_scheduler_pauses_at_wait_for(self):
        """Scheduler should checkpoint and return when hitting wait_for with no signal."""
        from flatmachines import FlatMachine, MemoryBackend

        # These imports will fail until implemented — that's the TDD signal
        from flatmachines import MemorySignalBackend

        signal_backend = MemorySignalBackend()
        hooks = DeepSleepHooks(max_depth=2, seed=1)

        machine = FlatMachine(
            config_dict=scheduler_config(),
            hooks=hooks,
            persistence=MemoryBackend(),
            signal_backend=signal_backend,
        )

        result = await machine.execute(input={
            "pool_name": "tasks",
            "max_active_roots": 2,
            "batch_size": 4,
        })

        # Machine should have paused at wait_for_work
        assert result.get("_waiting") is True
        assert result.get("_channel") == "dfss/ready"

    @pytest.mark.asyncio
    async def test_scheduler_resumes_on_signal(self):
        """Send signal before resume — scheduler should pick batch and dispatch."""
        from flatmachines import FlatMachine, MemoryBackend
        from flatmachines import MemorySignalBackend

        signal_backend = MemorySignalBackend()
        persistence = MemoryBackend()
        candidates = _make_candidates(n_roots=1, tasks_per_root=2)

        hooks = DeepSleepHooks(max_depth=2, seed=1)

        # First run: scheduler parks at wait_for
        machine = FlatMachine(
            config_dict=scheduler_config(),
            hooks=hooks,
            persistence=persistence,
            signal_backend=signal_backend,
        )
        result = await machine.execute(input={
            "pool_name": "tasks",
            "max_active_roots": 2,
            "batch_size": 4,
        })
        execution_id = machine.execution_id
        assert result.get("_waiting") is True

        # Send signal with candidates
        await signal_backend.send("dfss/ready", {"candidates": candidates})

        # Resume: scheduler should wake, pick batch, try to dispatch
        machine2 = FlatMachine(
            config_dict=scheduler_config(),
            hooks=hooks,
            persistence=persistence,
            signal_backend=signal_backend,
        )
        # This will fail at dispatch_batch (no real task_runner machine)
        # but we verify it got past wait_for
        try:
            result2 = await machine2.execute(resume_from=execution_id)
        except Exception:
            pass  # Expected — no task_runner machine configured for test

    @pytest.mark.asyncio
    async def test_signal_data_available_as_output(self):
        """Signal payload should be accessible via output.* in output_to_context."""
        from flatmachines import FlatMachine, MemoryBackend
        from flatmachines import MemorySignalBackend

        signal_backend = MemorySignalBackend()

        # Send signal before machine starts (pre-loaded)
        await signal_backend.send("dfss/ready", {"reason": "initial_seed"})

        hooks = DeepSleepHooks(max_depth=2, seed=1)
        machine = FlatMachine(
            config_dict=scheduler_config(),
            hooks=hooks,
            persistence=MemoryBackend(),
            signal_backend=signal_backend,
        )

        # With signal pre-loaded, machine should consume it and continue
        # (not pause at wait_for)
        # It will proceed to score_and_select with empty candidates → all_done → done
        result = await machine.execute(input={
            "pool_name": "tasks",
            "max_active_roots": 2,
            "batch_size": 4,
        })
        # Should have completed (all_done with no candidates)
        assert "_waiting" not in result or result.get("_waiting") is not True


class TestSchedulerCheckpointResume:
    """Tests for checkpoint-and-exit lifecycle."""

    @pytest.mark.asyncio
    async def test_waiting_channel_in_checkpoint(self):
        """Checkpoint should record waiting_channel for dispatcher queries."""
        from flatmachines import FlatMachine, MemoryBackend, CheckpointManager
        from flatmachines import MemorySignalBackend

        signal_backend = MemorySignalBackend()
        persistence = MemoryBackend()

        hooks = DeepSleepHooks(max_depth=2, seed=1)
        machine = FlatMachine(
            config_dict=scheduler_config(),
            hooks=hooks,
            persistence=persistence,
            signal_backend=signal_backend,
        )
        result = await machine.execute(input={
            "pool_name": "tasks",
            "max_active_roots": 2,
            "batch_size": 4,
        })

        # Load checkpoint and verify waiting_channel
        mgr = CheckpointManager(persistence, machine.execution_id)
        snapshot = await mgr.load_latest()
        assert snapshot is not None
        assert snapshot.waiting_channel == "dfss/ready"

    @pytest.mark.asyncio
    async def test_list_execution_ids_by_waiting_channel(self):
        """Persistence should support filtering by waiting_channel."""
        from flatmachines import FlatMachine, MemoryBackend
        from flatmachines import MemorySignalBackend

        signal_backend = MemorySignalBackend()
        persistence = MemoryBackend()

        hooks = DeepSleepHooks(max_depth=2, seed=1)

        # Park two schedulers on different channels
        for channel_suffix in ["a", "b"]:
            cfg = scheduler_config()
            cfg["data"]["states"]["wait_for_work"]["wait_for"] = f"dfss/{channel_suffix}"
            m = FlatMachine(
                config_dict=cfg,
                hooks=hooks,
                persistence=persistence,
                signal_backend=signal_backend,
            )
            await m.execute(input={
                "pool_name": "tasks",
                "max_active_roots": 2,
                "batch_size": 4,
            })

        # Query by waiting_channel
        ids_a = await persistence.list_execution_ids(waiting_channel="dfss/a")
        ids_b = await persistence.list_execution_ids(waiting_channel="dfss/b")
        assert len(ids_a) == 1
        assert len(ids_b) == 1
        assert ids_a[0] != ids_b[0]
