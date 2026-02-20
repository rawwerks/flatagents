"""
Unit tests for WorkPool after relocation from distributed.py to work.py.

Verifies that:
1. WorkPool, WorkItem, WorkBackend import from the new module
2. Memory and SQLite implementations work through the new path
3. Backward-compat re-exports from distributed.py still work
"""

import pytest
import tempfile
import os

# --- New import path (red until work.py exists) ---
from flatmachines.work import (
    WorkPool,
    WorkItem,
    WorkBackend,
    MemoryWorkPool,
    MemoryWorkBackend,
    SQLiteWorkPool,
    SQLiteWorkBackend,
    create_work_backend,
)


@pytest.fixture
def memory_backend():
    return MemoryWorkBackend()


@pytest.fixture
def sqlite_backend(tmp_path):
    return SQLiteWorkBackend(db_path=str(tmp_path / "test_work.sqlite"))


@pytest.fixture(params=["memory", "sqlite"])
def pool(request, tmp_path):
    if request.param == "memory":
        backend = MemoryWorkBackend()
    else:
        backend = SQLiteWorkBackend(db_path=str(tmp_path / "test_work.sqlite"))
    return backend.pool("test-pool")


# ---------------------------------------------------------------------------
# Basic pool operations (parametrized over both backends)
# ---------------------------------------------------------------------------

class TestPoolOperations:

    @pytest.mark.asyncio
    async def test_push_returns_id(self, pool):
        item_id = await pool.push({"task": "hello"})
        assert isinstance(item_id, str)
        assert len(item_id) > 0

    @pytest.mark.asyncio
    async def test_push_and_claim(self, pool):
        await pool.push({"task": "hello"})
        claimed = await pool.claim("worker-1")
        assert claimed is not None
        assert claimed.data == {"task": "hello"}

    @pytest.mark.asyncio
    async def test_claim_empty_returns_none(self, pool):
        assert await pool.claim("worker-1") is None

    @pytest.mark.asyncio
    async def test_complete_removes_item(self, pool):
        item_id = await pool.push({"task": "hello"})
        claimed = await pool.claim("worker-1")
        await pool.complete(claimed.id)
        assert await pool.size() == 0

    @pytest.mark.asyncio
    async def test_fail_returns_to_pending(self, pool):
        await pool.push({"task": "hello"}, {"max_retries": 3})
        claimed = await pool.claim("worker-1")
        await pool.fail(claimed.id, "oops")
        # Should be back in pool
        assert await pool.size() == 1

    @pytest.mark.asyncio
    async def test_fail_poisons_after_max_retries(self, pool):
        await pool.push({"task": "hello"}, {"max_retries": 1})
        # Claim 1 → fail → retry
        claimed = await pool.claim("worker-1")
        await pool.fail(claimed.id, "oops")
        # Claim 2 → fail → poisoned (attempts >= max_retries)
        claimed2 = await pool.claim("worker-1")
        if claimed2:
            await pool.fail(claimed2.id, "oops again")
        # Pool should have no pending items
        assert await pool.size() == 0

    @pytest.mark.asyncio
    async def test_size_counts_pending_only(self, pool):
        await pool.push({"a": 1})
        await pool.push({"b": 2})
        assert await pool.size() == 2
        await pool.claim("worker-1")
        assert await pool.size() == 1

    @pytest.mark.asyncio
    async def test_release_by_worker(self, pool):
        await pool.push({"a": 1})
        await pool.push({"b": 2})
        await pool.claim("worker-1")
        await pool.claim("worker-1")
        assert await pool.size() == 0
        released = await pool.release_by_worker("worker-1")
        assert released == 2
        assert await pool.size() == 2


# ---------------------------------------------------------------------------
# Named pools
# ---------------------------------------------------------------------------

class TestNamedPools:

    @pytest.mark.asyncio
    async def test_separate_pools(self, memory_backend):
        pool_a = memory_backend.pool("alpha")
        pool_b = memory_backend.pool("beta")
        await pool_a.push({"in": "alpha"})
        assert await pool_a.size() == 1
        assert await pool_b.size() == 0


# ---------------------------------------------------------------------------
# Factory function
# ---------------------------------------------------------------------------

class TestFactory:

    def test_create_memory(self):
        backend = create_work_backend("memory")
        assert backend is not None

    def test_create_sqlite(self, tmp_path):
        backend = create_work_backend("sqlite", db_path=str(tmp_path / "test.sqlite"))
        assert backend is not None


# ---------------------------------------------------------------------------
# Backward compatibility: old import path still works
# ---------------------------------------------------------------------------

class TestBackwardCompat:

    def test_distributed_reexports_work_pool(self):
        from flatmachines.distributed import WorkPool as DP_WorkPool
        from flatmachines.work import WorkPool as W_WorkPool
        assert DP_WorkPool is W_WorkPool

    def test_distributed_reexports_work_backend(self):
        from flatmachines.distributed import WorkBackend as DP_WB
        from flatmachines.work import WorkBackend as W_WB
        assert DP_WB is W_WB

    def test_distributed_reexports_work_item(self):
        from flatmachines.distributed import WorkItem as DP_WI
        from flatmachines.work import WorkItem as W_WI
        assert DP_WI is W_WI

    def test_distributed_reexports_memory_work_backend(self):
        from flatmachines.distributed import MemoryWorkBackend as DP_MWB
        from flatmachines.work import MemoryWorkBackend as W_MWB
        assert DP_MWB is W_MWB

    def test_distributed_reexports_sqlite_work_backend(self):
        from flatmachines.distributed import SQLiteWorkBackend as DP_SWB
        from flatmachines.work import SQLiteWorkBackend as W_SWB
        assert DP_SWB is W_SWB

    def test_init_reexports(self):
        """Top-level flatmachines imports still work."""
        from flatmachines import WorkPool, WorkItem, WorkBackend
        from flatmachines.work import WorkPool as W_WP
        assert WorkPool is W_WP
