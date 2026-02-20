"""
Distributed backends for FlatAgents worker orchestration.

This module provides backends for worker lifecycle management (registration,
heartbeats, status) across ephemeral machines.

Work pool backends (WorkPool, WorkBackend, etc.) have moved to work.py
and are re-exported here for backward compatibility.

Backends:
- RegistrationBackend: Worker lifecycle (register, heartbeat, status)
- WorkBackend: Work distribution via named pools with atomic claiming (see work.py)

Implementations:
- SQLite: Single-file database, suitable for local/container deployments
- Memory: In-memory storage, suitable for testing and single-process scenarios
"""

import asyncio
import json
import logging
import sqlite3
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

# Re-export work pool classes for backward compatibility
from .work import (
    WorkItem,
    WorkPool,
    WorkBackend,
    MemoryWorkPool,
    MemoryWorkBackend,
    SQLiteWorkPool,
    SQLiteWorkBackend,
    create_work_backend,
)

logger = logging.getLogger(__name__)


# =============================================================================
# Types
# =============================================================================

@dataclass
class WorkerRegistration:
    """Information for registering a new worker."""
    worker_id: str
    host: Optional[str] = None
    pid: Optional[int] = None
    capabilities: Optional[List[str]] = None
    started_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass  
class WorkerRecord:
    """Complete worker record including status and heartbeat."""
    worker_id: str
    status: str  # "active", "terminating", "terminated", "lost"
    last_heartbeat: str
    host: Optional[str] = None
    pid: Optional[int] = None
    capabilities: Optional[List[str]] = None
    started_at: Optional[str] = None
    current_task_id: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WorkerRecord":
        return cls(**data)


@dataclass
class WorkerFilter:
    """Filter criteria for listing workers."""
    status: Optional[str] = None
    capability: Optional[str] = None
    stale_threshold_seconds: Optional[int] = None


# =============================================================================
# Registration Backend Protocol & Implementations
# =============================================================================

@runtime_checkable
class RegistrationBackend(Protocol):
    """
    Protocol for worker lifecycle management.
    
    Workers register themselves, send periodic heartbeats, and update status.
    The backend tracks worker liveness for stale detection.
    """
    
    async def register(self, worker: WorkerRegistration) -> WorkerRecord:
        """Register a new worker.
        
        Args:
            worker: Worker registration information
            
        Returns:
            Complete worker record with initial status
        """
        ...
    
    async def heartbeat(
        self, 
        worker_id: str, 
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """Update worker's last heartbeat timestamp.
        
        Args:
            worker_id: ID of the worker
            metadata: Optional metadata to update
        """
        ...
    
    async def update_status(self, worker_id: str, status: str) -> None:
        """Update worker status.
        
        Args:
            worker_id: ID of the worker
            status: New status (active, terminating, terminated, lost)
        """
        ...
    
    async def get(self, worker_id: str) -> Optional[WorkerRecord]:
        """Get worker by ID.
        
        Args:
            worker_id: ID of the worker
            
        Returns:
            Worker record or None if not found
        """
        ...
    
    async def list(self, filter: Optional[WorkerFilter] = None) -> List[WorkerRecord]:
        """List workers matching filter.
        
        Args:
            filter: Optional filter criteria
            
        Returns:
            List of matching worker records
        """
        ...


class MemoryRegistrationBackend:
    """In-memory registration backend for testing and single-process scenarios."""
    
    def __init__(self):
        self._workers: Dict[str, WorkerRecord] = {}
        self._lock = asyncio.Lock()
    
    async def register(self, worker: WorkerRegistration) -> WorkerRecord:
        async with self._lock:
            now = datetime.now(timezone.utc).isoformat()
            record = WorkerRecord(
                worker_id=worker.worker_id,
                status="active",
                last_heartbeat=now,
                host=worker.host,
                pid=worker.pid,
                capabilities=worker.capabilities,
                started_at=worker.started_at,
            )
            self._workers[worker.worker_id] = record
            logger.debug(f"RegistrationBackend: registered worker {worker.worker_id}")
            return record
    
    async def heartbeat(
        self, 
        worker_id: str, 
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        async with self._lock:
            if worker_id not in self._workers:
                raise KeyError(f"Worker {worker_id} not found")
            record = self._workers[worker_id]
            record.last_heartbeat = datetime.now(timezone.utc).isoformat()
            if metadata:
                record.metadata = {**(record.metadata or {}), **metadata}
            logger.debug(f"RegistrationBackend: heartbeat for {worker_id}")
    
    async def update_status(self, worker_id: str, status: str) -> None:
        async with self._lock:
            if worker_id not in self._workers:
                raise KeyError(f"Worker {worker_id} not found")
            self._workers[worker_id].status = status
            logger.debug(f"RegistrationBackend: {worker_id} status -> {status}")
    
    async def get(self, worker_id: str) -> Optional[WorkerRecord]:
        return self._workers.get(worker_id)
    
    async def list(self, filter: Optional[WorkerFilter] = None) -> List[WorkerRecord]:
        workers = list(self._workers.values())
        
        if filter:
            if filter.status:
                workers = [w for w in workers if w.status == filter.status]
            if filter.capability:
                workers = [
                    w for w in workers 
                    if w.capabilities and filter.capability in w.capabilities
                ]
            if filter.stale_threshold_seconds:
                cutoff = datetime.now(timezone.utc) - timedelta(
                    seconds=filter.stale_threshold_seconds
                )
                workers = [
                    w for w in workers
                    if datetime.fromisoformat(w.last_heartbeat.replace('Z', '+00:00')) < cutoff
                ]
        
        return workers


class SQLiteRegistrationBackend:
    """SQLite-based registration backend for local/container deployments."""
    
    SCHEMA = """
    CREATE TABLE IF NOT EXISTS worker_registry (
        worker_id TEXT PRIMARY KEY,
        status TEXT NOT NULL DEFAULT 'active',
        last_heartbeat TEXT NOT NULL,
        host TEXT,
        pid INTEGER,
        capabilities TEXT,  -- JSON array
        started_at TEXT,
        current_task_id TEXT,
        metadata TEXT  -- JSON object
    );
    
    CREATE INDEX IF NOT EXISTS idx_worker_status ON worker_registry(status);
    CREATE INDEX IF NOT EXISTS idx_worker_heartbeat ON worker_registry(last_heartbeat);
    """
    
    def __init__(self, db_path: str = "workers.sqlite"):
        self.db_path = Path(db_path)
        self._lock = asyncio.Lock()
        self._init_db()
    
    def _init_db(self) -> None:
        """Initialize database schema."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript(self.SCHEMA)
    
    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn
    
    def _row_to_record(self, row: sqlite3.Row) -> WorkerRecord:
        capabilities = json.loads(row["capabilities"]) if row["capabilities"] else None
        metadata = json.loads(row["metadata"]) if row["metadata"] else None
        return WorkerRecord(
            worker_id=row["worker_id"],
            status=row["status"],
            last_heartbeat=row["last_heartbeat"],
            host=row["host"],
            pid=row["pid"],
            capabilities=capabilities,
            started_at=row["started_at"],
            current_task_id=row["current_task_id"],
            metadata=metadata,
        )
    
    async def register(self, worker: WorkerRegistration) -> WorkerRecord:
        async with self._lock:
            now = datetime.now(timezone.utc).isoformat()
            capabilities_json = json.dumps(worker.capabilities) if worker.capabilities else None
            
            with self._get_conn() as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO worker_registry 
                    (worker_id, status, last_heartbeat, host, pid, capabilities, started_at)
                    VALUES (?, 'active', ?, ?, ?, ?, ?)
                    """,
                    (worker.worker_id, now, worker.host, worker.pid, 
                     capabilities_json, worker.started_at)
                )
            
            logger.debug(f"RegistrationBackend: registered worker {worker.worker_id}")
            return WorkerRecord(
                worker_id=worker.worker_id,
                status="active",
                last_heartbeat=now,
                host=worker.host,
                pid=worker.pid,
                capabilities=worker.capabilities,
                started_at=worker.started_at,
            )
    
    async def heartbeat(
        self, 
        worker_id: str, 
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        async with self._lock:
            now = datetime.now(timezone.utc).isoformat()
            with self._get_conn() as conn:
                if metadata:
                    # Merge metadata
                    cursor = conn.execute(
                        "SELECT metadata FROM worker_registry WHERE worker_id = ?",
                        (worker_id,)
                    )
                    row = cursor.fetchone()
                    if not row:
                        raise KeyError(f"Worker {worker_id} not found")
                    existing = json.loads(row["metadata"]) if row["metadata"] else {}
                    merged = {**existing, **metadata}
                    conn.execute(
                        """
                        UPDATE worker_registry 
                        SET last_heartbeat = ?, metadata = ?
                        WHERE worker_id = ?
                        """,
                        (now, json.dumps(merged), worker_id)
                    )
                else:
                    result = conn.execute(
                        "UPDATE worker_registry SET last_heartbeat = ? WHERE worker_id = ?",
                        (now, worker_id)
                    )
                    if result.rowcount == 0:
                        raise KeyError(f"Worker {worker_id} not found")
            
            logger.debug(f"RegistrationBackend: heartbeat for {worker_id}")
    
    async def update_status(self, worker_id: str, status: str) -> None:
        async with self._lock:
            with self._get_conn() as conn:
                result = conn.execute(
                    "UPDATE worker_registry SET status = ? WHERE worker_id = ?",
                    (status, worker_id)
                )
                if result.rowcount == 0:
                    raise KeyError(f"Worker {worker_id} not found")
            
            logger.debug(f"RegistrationBackend: {worker_id} status -> {status}")
    
    async def get(self, worker_id: str) -> Optional[WorkerRecord]:
        with self._get_conn() as conn:
            cursor = conn.execute(
                "SELECT * FROM worker_registry WHERE worker_id = ?",
                (worker_id,)
            )
            row = cursor.fetchone()
            return self._row_to_record(row) if row else None
    
    async def list(self, filter: Optional[WorkerFilter] = None) -> List[WorkerRecord]:
        query = "SELECT * FROM worker_registry WHERE 1=1"
        params: List[Any] = []
        
        if filter:
            if filter.status:
                query += " AND status = ?"
                params.append(filter.status)
            if filter.capability:
                # JSON contains check
                query += " AND capabilities LIKE ?"
                params.append(f'%"{filter.capability}"%')
            if filter.stale_threshold_seconds:
                cutoff = (
                    datetime.now(timezone.utc) - 
                    timedelta(seconds=filter.stale_threshold_seconds)
                ).isoformat()
                query += " AND last_heartbeat < ?"
                params.append(cutoff)
        
        with self._get_conn() as conn:
            cursor = conn.execute(query, params)
            return [self._row_to_record(row) for row in cursor.fetchall()]





# =============================================================================
# Factory Functions
# =============================================================================

def create_registration_backend(
    backend_type: str = "memory",
    **kwargs: Any
) -> RegistrationBackend:
    """Create a registration backend by type.
    
    Args:
        backend_type: "memory" or "sqlite"
        **kwargs: Backend-specific options (e.g., db_path for sqlite)
        
    Returns:
        RegistrationBackend instance
    """
    if backend_type == "memory":
        return MemoryRegistrationBackend()
    elif backend_type == "sqlite":
        db_path = kwargs.get("db_path", "workers.sqlite")
        return SQLiteRegistrationBackend(db_path=db_path)
    else:
        raise ValueError(f"Unknown registration backend type: {backend_type}")


__all__ = [
    # Registration (native to this module)
    "WorkerRegistration",
    "WorkerRecord",
    "WorkerFilter",
    "RegistrationBackend",
    "MemoryRegistrationBackend",
    "SQLiteRegistrationBackend",
    "create_registration_backend",
    # Re-exported from work.py for backward compatibility
    "WorkItem",
    "WorkPool",
    "WorkBackend",
    "MemoryWorkPool",
    "MemoryWorkBackend",
    "SQLiteWorkPool",
    "SQLiteWorkBackend",
    "create_work_backend",
]
