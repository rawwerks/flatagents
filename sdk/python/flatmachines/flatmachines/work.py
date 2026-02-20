"""
Work pool backends for durable task storage with atomic claiming.

This module provides the WorkPool abstraction — an unordered collection of
work items with atomic push/claim/complete/fail semantics. The pool provides
storage and atomic withdrawal; the scheduler imposes ordering.

Backends:
- MemoryWorkPool/MemoryWorkBackend: In-memory, for testing and single-process
- SQLiteWorkPool/SQLiteWorkBackend: SQLite-backed, for durable local storage

These are general-purpose storage primitives, not distributed-only.
For distributed worker orchestration (RegistrationBackend, heartbeats, etc.),
see distributed.py.
"""

import asyncio
import json
import logging
import sqlite3
import uuid
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

logger = logging.getLogger(__name__)


# =============================================================================
# Types
# =============================================================================

@dataclass
class WorkItem:
    """A claimed work item from a pool."""
    id: str
    data: Any
    claimed_by: Optional[str] = None
    attempts: int = 0
    max_retries: int = 3
    status: str = "pending"  # "pending", "claimed", "completed", "failed", "poisoned"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    claimed_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# =============================================================================
# Protocols
# =============================================================================

@runtime_checkable
class WorkPool(Protocol):
    """
    Protocol for a named work pool with atomic claiming.

    Workers claim items atomically, process them, and mark complete or failed.
    The pool is an unordered collection — the scheduler decides what to claim.
    """

    async def push(self, item: Any, options: Optional[Dict[str, Any]] = None) -> str:
        """Add work item to pool.

        Args:
            item: Work item data (must be JSON-serializable)
            options: Optional settings like max_retries

        Returns:
            Generated item ID
        """
        ...

    async def claim(self, worker_id: str) -> Optional[WorkItem]:
        """Atomically claim next available item.

        Args:
            worker_id: ID of the claiming worker

        Returns:
            Claimed work item or None if pool is empty
        """
        ...

    async def complete(self, item_id: str, result: Optional[Any] = None) -> None:
        """Mark item as completed and remove from pool.

        Args:
            item_id: ID of the work item
            result: Optional result data
        """
        ...

    async def fail(self, item_id: str, error: Optional[str] = None) -> None:
        """Mark item as failed. Returns to pool for retry or marks as poisoned.

        Args:
            item_id: ID of the work item
            error: Optional error message
        """
        ...

    async def size(self) -> int:
        """Get number of unclaimed items in pool."""
        ...

    async def release_by_worker(self, worker_id: str) -> int:
        """Release all items claimed by a worker (for stale worker cleanup).

        Args:
            worker_id: ID of the worker whose items to release

        Returns:
            Number of items released
        """
        ...


@runtime_checkable
class WorkBackend(Protocol):
    """Protocol for work distribution across named pools."""

    def pool(self, name: str) -> WorkPool:
        """Get a named work pool.

        Args:
            name: Pool name (e.g., "paper_analysis", "image_processing")

        Returns:
            WorkPool instance for the named pool
        """
        ...


# =============================================================================
# Memory implementations
# =============================================================================

class MemoryWorkPool:
    """In-memory work pool implementation."""

    def __init__(self, name: str):
        self.name = name
        self._items: Dict[str, WorkItem] = {}
        self._lock = asyncio.Lock()

    async def push(self, item: Any, options: Optional[Dict[str, Any]] = None) -> str:
        async with self._lock:
            item_id = str(uuid.uuid4())
            max_retries = (options or {}).get("max_retries", 3)
            work_item = WorkItem(
                id=item_id,
                data=item,
                max_retries=max_retries,
            )
            self._items[item_id] = work_item
            logger.debug(f"WorkPool[{self.name}]: pushed item {item_id}")
            return item_id

    async def claim(self, worker_id: str) -> Optional[WorkItem]:
        async with self._lock:
            for item in self._items.values():
                if item.status == "pending":
                    item.status = "claimed"
                    item.claimed_by = worker_id
                    item.claimed_at = datetime.now(timezone.utc).isoformat()
                    item.attempts += 1
                    logger.debug(f"WorkPool[{self.name}]: {worker_id} claimed {item.id}")
                    return item
            return None

    async def complete(self, item_id: str, result: Optional[Any] = None) -> None:
        async with self._lock:
            if item_id not in self._items:
                raise KeyError(f"Work item {item_id} not found")
            del self._items[item_id]
            logger.debug(f"WorkPool[{self.name}]: completed {item_id}")

    async def fail(self, item_id: str, error: Optional[str] = None) -> None:
        async with self._lock:
            if item_id not in self._items:
                raise KeyError(f"Work item {item_id} not found")
            item = self._items[item_id]

            if item.attempts >= item.max_retries:
                item.status = "poisoned"
                logger.warning(
                    f"WorkPool[{self.name}]: {item_id} poisoned after {item.attempts} attempts"
                )
            else:
                item.status = "pending"
                item.claimed_by = None
                item.claimed_at = None
                logger.debug(
                    f"WorkPool[{self.name}]: {item_id} failed, returning to pool "
                    f"(attempt {item.attempts}/{item.max_retries})"
                )

    async def size(self) -> int:
        return sum(1 for item in self._items.values() if item.status == "pending")

    async def release_by_worker(self, worker_id: str) -> int:
        async with self._lock:
            released = 0
            for item in self._items.values():
                if item.claimed_by == worker_id and item.status == "claimed":
                    item.status = "pending"
                    item.claimed_by = None
                    item.claimed_at = None
                    released += 1
            logger.debug(f"WorkPool[{self.name}]: released {released} items from {worker_id}")
            return released


class MemoryWorkBackend:
    """In-memory work backend with named pools."""

    def __init__(self):
        self._pools: Dict[str, MemoryWorkPool] = {}

    def pool(self, name: str) -> MemoryWorkPool:
        if name not in self._pools:
            self._pools[name] = MemoryWorkPool(name)
        return self._pools[name]


# =============================================================================
# SQLite implementations
# =============================================================================

class SQLiteWorkPool:
    """SQLite-based work pool implementation."""

    def __init__(self, name: str, db_path: Path, lock: asyncio.Lock):
        self.name = name
        self.db_path = db_path
        self._lock = lock

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _row_to_item(self, row: sqlite3.Row) -> WorkItem:
        return WorkItem(
            id=row["item_id"],
            data=json.loads(row["data"]),
            claimed_by=row["claimed_by"],
            attempts=row["attempts"],
            max_retries=row["max_retries"],
            status=row["status"],
            created_at=row["created_at"],
            claimed_at=row["claimed_at"],
        )

    async def push(self, item: Any, options: Optional[Dict[str, Any]] = None) -> str:
        async with self._lock:
            item_id = str(uuid.uuid4())
            max_retries = (options or {}).get("max_retries", 3)
            now = datetime.now(timezone.utc).isoformat()

            with self._get_conn() as conn:
                conn.execute(
                    """
                    INSERT INTO work_pool
                    (item_id, pool_name, data, status, attempts, max_retries, created_at)
                    VALUES (?, ?, ?, 'pending', 0, ?, ?)
                    """,
                    (item_id, self.name, json.dumps(item), max_retries, now)
                )

            logger.debug(f"WorkPool[{self.name}]: pushed item {item_id}")
            return item_id

    async def claim(self, worker_id: str) -> Optional[WorkItem]:
        async with self._lock:
            now = datetime.now(timezone.utc).isoformat()

            with self._get_conn() as conn:
                cursor = conn.execute(
                    """
                    SELECT item_id FROM work_pool
                    WHERE pool_name = ? AND status = 'pending'
                    ORDER BY created_at ASC
                    LIMIT 1
                    """,
                    (self.name,)
                )
                row = cursor.fetchone()
                if not row:
                    return None

                item_id = row["item_id"]
                conn.execute(
                    """
                    UPDATE work_pool
                    SET status = 'claimed', claimed_by = ?, claimed_at = ?,
                        attempts = attempts + 1
                    WHERE item_id = ?
                    """,
                    (worker_id, now, item_id)
                )

                cursor = conn.execute(
                    "SELECT * FROM work_pool WHERE item_id = ?",
                    (item_id,)
                )
                row = cursor.fetchone()

            logger.debug(f"WorkPool[{self.name}]: {worker_id} claimed {item_id}")
            return self._row_to_item(row) if row else None

    async def complete(self, item_id: str, result: Optional[Any] = None) -> None:
        async with self._lock:
            with self._get_conn() as conn:
                result = conn.execute(
                    "DELETE FROM work_pool WHERE item_id = ?",
                    (item_id,)
                )
                if result.rowcount == 0:
                    raise KeyError(f"Work item {item_id} not found")

            logger.debug(f"WorkPool[{self.name}]: completed {item_id}")

    async def fail(self, item_id: str, error: Optional[str] = None) -> None:
        async with self._lock:
            with self._get_conn() as conn:
                cursor = conn.execute(
                    "SELECT attempts, max_retries FROM work_pool WHERE item_id = ?",
                    (item_id,)
                )
                row = cursor.fetchone()
                if not row:
                    raise KeyError(f"Work item {item_id} not found")

                attempts = row["attempts"]
                max_retries = row["max_retries"]

                if attempts >= max_retries:
                    conn.execute(
                        "UPDATE work_pool SET status = 'poisoned' WHERE item_id = ?",
                        (item_id,)
                    )
                    logger.warning(
                        f"WorkPool[{self.name}]: {item_id} poisoned after {attempts} attempts"
                    )
                else:
                    conn.execute(
                        """
                        UPDATE work_pool
                        SET status = 'pending', claimed_by = NULL, claimed_at = NULL
                        WHERE item_id = ?
                        """,
                        (item_id,)
                    )
                    logger.debug(
                        f"WorkPool[{self.name}]: {item_id} failed, returning to pool "
                        f"(attempt {attempts}/{max_retries})"
                    )

    async def size(self) -> int:
        with self._get_conn() as conn:
            cursor = conn.execute(
                "SELECT COUNT(*) as cnt FROM work_pool WHERE pool_name = ? AND status = 'pending'",
                (self.name,)
            )
            return cursor.fetchone()["cnt"]

    async def release_by_worker(self, worker_id: str) -> int:
        async with self._lock:
            with self._get_conn() as conn:
                result = conn.execute(
                    """
                    UPDATE work_pool
                    SET status = 'pending', claimed_by = NULL, claimed_at = NULL
                    WHERE pool_name = ? AND claimed_by = ? AND status = 'claimed'
                    """,
                    (self.name, worker_id)
                )
                released = result.rowcount

            logger.debug(f"WorkPool[{self.name}]: released {released} items from {worker_id}")
            return released


class SQLiteWorkBackend:
    """SQLite-based work backend with named pools."""

    SCHEMA = """
    CREATE TABLE IF NOT EXISTS work_pool (
        item_id TEXT PRIMARY KEY,
        pool_name TEXT NOT NULL,
        data TEXT NOT NULL,  -- JSON
        status TEXT NOT NULL DEFAULT 'pending',
        claimed_by TEXT,
        claimed_at TEXT,
        attempts INTEGER NOT NULL DEFAULT 0,
        max_retries INTEGER NOT NULL DEFAULT 3,
        created_at TEXT NOT NULL,
        error TEXT
    );

    CREATE INDEX IF NOT EXISTS idx_work_pool_name ON work_pool(pool_name);
    CREATE INDEX IF NOT EXISTS idx_work_status ON work_pool(status);
    CREATE INDEX IF NOT EXISTS idx_work_claimed_by ON work_pool(claimed_by);
    """

    def __init__(self, db_path: str = "workers.sqlite"):
        self.db_path = Path(db_path)
        self._pools: Dict[str, SQLiteWorkPool] = {}
        self._lock = asyncio.Lock()
        self._init_db()

    def _init_db(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript(self.SCHEMA)

    def pool(self, name: str) -> SQLiteWorkPool:
        if name not in self._pools:
            self._pools[name] = SQLiteWorkPool(name, self.db_path, self._lock)
        return self._pools[name]


# =============================================================================
# Factory
# =============================================================================

def create_work_backend(
    backend_type: str = "memory",
    **kwargs: Any,
) -> WorkBackend:
    """Create a work backend by type.

    Args:
        backend_type: "memory" or "sqlite"
        **kwargs: Backend-specific options (e.g., db_path for sqlite)

    Returns:
        WorkBackend instance
    """
    if backend_type == "memory":
        return MemoryWorkBackend()
    elif backend_type == "sqlite":
        db_path = kwargs.get("db_path", "workers.sqlite")
        return SQLiteWorkBackend(db_path=db_path)
    else:
        raise ValueError(f"Unknown work backend type: {backend_type}")


__all__ = [
    "WorkItem",
    "WorkPool",
    "WorkBackend",
    "MemoryWorkPool",
    "MemoryWorkBackend",
    "SQLiteWorkPool",
    "SQLiteWorkBackend",
    "create_work_backend",
]
