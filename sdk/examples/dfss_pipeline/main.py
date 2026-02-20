#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import inspect
import sqlite3
from pathlib import Path
from typing import Any, Dict, List

from hooks import TaskHooks
from scheduler import ResourcePool, RootState, run
from workflow_plan import build_workflow_plan


def _connect(db_path: str) -> sqlite3.Connection:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), check_same_thread=False, timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute("PRAGMA busy_timeout = 10000")
    return conn


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS tasks (
            task_id TEXT PRIMARY KEY,
            root_id TEXT NOT NULL,
            parent_id TEXT,
            depth INTEGER NOT NULL,
            resource_class TEXT NOT NULL,
            has_expensive_descendant INTEGER NOT NULL DEFAULT 0,
            distance_to_nearest_slow_descendant INTEGER NOT NULL DEFAULT 10000,
            status TEXT NOT NULL,
            attempts INTEGER NOT NULL DEFAULT 0,
            result TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
        CREATE INDEX IF NOT EXISTS idx_tasks_root_status ON tasks(root_id, status);

        CREATE TABLE IF NOT EXISTS run_meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        """
    )
    conn.commit()


def _seed_plan(conn: sqlite3.Connection, roots: int, max_depth: int, seed: int) -> None:
    plan = build_workflow_plan(roots=roots, max_depth=max_depth, seed=seed)

    conn.execute("DELETE FROM tasks")
    conn.execute("DELETE FROM run_meta")

    for task_id, node in plan["nodes"].items():
        parent_id = node.get("parent_id")
        status = "ready" if not parent_id else "blocked"
        conn.execute(
            """
            INSERT INTO tasks (
                task_id, root_id, parent_id, depth, resource_class,
                has_expensive_descendant, distance_to_nearest_slow_descendant,
                status, attempts, result
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, NULL)
            """,
            (
                task_id,
                node["root_id"],
                parent_id,
                int(node["depth"]),
                node["resource_class"],
                1 if node.get("has_expensive_descendant") else 0,
                int(node.get("distance_to_nearest_slow_descendant", 10000)),
                status,
            ),
        )

    conn.execute("INSERT INTO run_meta(key, value) VALUES('seed', ?)", (str(seed),))
    conn.execute("INSERT INTO run_meta(key, value) VALUES('roots', ?)", (str(roots),))
    conn.commit()


def _release_stale_running(conn: sqlite3.Connection) -> int:
    cur = conn.execute("UPDATE tasks SET status='ready' WHERE status='running'")
    conn.commit()
    return int(cur.rowcount or 0)


def _task_row_to_item(row: sqlite3.Row) -> Dict[str, Any]:
    return {
        "task_id": row["task_id"],
        "root_id": row["root_id"],
        "depth": int(row["depth"]),
        "resource_class": row["resource_class"],
        "has_expensive_descendant": bool(row["has_expensive_descendant"]),
        "distance_to_nearest_slow_descendant": int(row["distance_to_nearest_slow_descendant"]),
        "attempts": int(row["attempts"]),
    }


def _load_ready_candidates(conn: sqlite3.Connection) -> List[Dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT task_id, root_id, depth, resource_class,
               has_expensive_descendant, distance_to_nearest_slow_descendant, attempts
        FROM tasks
        WHERE status = 'ready'
        ORDER BY depth DESC, task_id ASC
        """
    ).fetchall()
    return [_task_row_to_item(r) for r in rows]


def _build_roots(conn: sqlite3.Connection) -> Dict[str, RootState]:
    rows = conn.execute(
        """
        SELECT
            root_id,
            SUM(CASE WHEN status NOT IN ('done','failed_terminal') THEN 1 ELSE 0 END) AS pending,
            SUM(CASE WHEN status = 'running' THEN 1 ELSE 0 END) AS in_flight,
            SUM(CASE WHEN status NOT IN ('done','failed_terminal') AND resource_class = 'slow' THEN 1 ELSE 0 END) AS slow_pending
        FROM tasks
        GROUP BY root_id
        """
    ).fetchall()

    roots: Dict[str, RootState] = {}
    for r in rows:
        roots[r["root_id"]] = RootState(
            root_id=r["root_id"],
            admitted=False,
            in_flight=int(r["in_flight"] or 0),
            pending=int(r["pending"] or 0),
            has_pending_expensive=bool(r["slow_pending"] or 0),
        )
    return roots


def _refresh_root_flags(conn: sqlite3.Connection, root: RootState) -> None:
    row = conn.execute(
        """
        SELECT
            SUM(CASE WHEN status NOT IN ('done','failed_terminal') THEN 1 ELSE 0 END) AS pending,
            SUM(CASE WHEN status NOT IN ('done','failed_terminal') AND resource_class='slow' THEN 1 ELSE 0 END) AS slow_pending
        FROM tasks
        WHERE root_id = ?
        """,
        (root.root_id,),
    ).fetchone()
    root.pending = int((row["pending"] if row else 0) or 0)
    root.has_pending_expensive = bool((row["slow_pending"] if row else 0) or 0)


def _mark_running(conn: sqlite3.Connection, task_id: str) -> int:
    conn.execute(
        "UPDATE tasks SET status='running', attempts=attempts+1 WHERE task_id=?",
        (task_id,),
    )
    row = conn.execute("SELECT attempts FROM tasks WHERE task_id=?", (task_id,)).fetchone()
    conn.commit()
    return int(row["attempts"] if row else 1)


def _mark_ready(conn: sqlite3.Connection, task_id: str) -> None:
    conn.execute("UPDATE tasks SET status='ready' WHERE task_id=?", (task_id,))
    conn.commit()


def _mark_done(conn: sqlite3.Connection, task_id: str, result: str) -> None:
    conn.execute("UPDATE tasks SET status='done', result=? WHERE task_id=?", (result, task_id))
    conn.commit()


def _mark_failed(conn: sqlite3.Connection, task_id: str, error: str) -> None:
    conn.execute(
        "UPDATE tasks SET status='failed_terminal', result=? WHERE task_id=?",
        (error[:500], task_id),
    )
    conn.commit()


def _unlock_children(conn: sqlite3.Connection, parent_id: str) -> List[Dict[str, Any]]:
    conn.execute(
        "UPDATE tasks SET status='ready' WHERE parent_id=? AND status='blocked'",
        (parent_id,),
    )
    rows = conn.execute(
        """
        SELECT task_id, root_id, depth, resource_class,
               has_expensive_descendant, distance_to_nearest_slow_descendant, attempts
        FROM tasks
        WHERE parent_id=? AND status='ready'
        ORDER BY task_id ASC
        """,
        (parent_id,),
    ).fetchall()
    conn.commit()
    return [_task_row_to_item(r) for r in rows]


def _root_complete(conn: sqlite3.Connection, root_id: str) -> bool:
    row = conn.execute(
        "SELECT COUNT(*) AS c FROM tasks WHERE root_id=? AND status NOT IN ('done','failed_terminal')",
        (root_id,),
    ).fetchone()
    return int(row["c"] if row else 0) == 0


def _pending_total(conn: sqlite3.Connection) -> int:
    row = conn.execute(
        "SELECT COUNT(*) AS c FROM tasks WHERE status NOT IN ('done','failed_terminal')"
    ).fetchone()
    return int(row["c"] if row else 0)


async def _toggle_slow_gate(resources: Dict[str, ResourcePool], stop: asyncio.Event, interval: float = 0.8) -> None:
    print("  ⚡ slow gate -> OPEN", flush=True)
    while not stop.is_set():
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval)
            break
        except asyncio.TimeoutError:
            pass

        slow = resources["slow"]
        slow.gate_open = not slow.gate_open
        state = "OPEN" if slow.gate_open else "CLOSED"
        print(f"  ⚡ slow gate -> {state}", flush=True)


async def _run_pipeline(args: argparse.Namespace) -> int:
    conn = _connect(args.db_path)
    _ensure_schema(conn)

    if args.resume:
        released = _release_stale_running(conn)
        print(f"Resuming run from {args.db_path} (released {released} stale running tasks)", flush=True)
    else:
        _seed_plan(conn, roots=args.roots, max_depth=args.max_depth, seed=args.seed)
        print(
            f"Seeded upfront workflow plan: roots={args.roots}, max_depth={args.max_depth}, seed={args.seed}",
            flush=True,
        )

    candidates = _load_ready_candidates(conn)
    roots = _build_roots(conn)

    resources = {
        "fast": ResourcePool("fast", capacity=4, in_flight=0, gate_open=True),
        "slow": ResourcePool("slow", capacity=2, in_flight=0, gate_open=True),
    }

    hooks = TaskHooks(max_depth=args.max_depth, fail_rate=args.fail_rate, seed=args.seed)
    completed_roots: set[str] = set()

    async def dispatch(item: Dict[str, Any]) -> None:
        task_id = item["task_id"]
        root_id = item["root_id"]
        attempts = _mark_running(conn, task_id)

        # Simulated work duration.
        if item["resource_class"] == "slow":
            await asyncio.sleep(0.80)
        else:
            await asyncio.sleep(0.35)

        context = dict(item)
        try:
            result = hooks.on_action("run_task", context)
            if inspect.isawaitable(result):
                result = await result
        except Exception as exc:
            if attempts < 3:
                _mark_ready(conn, task_id)
                row = conn.execute(
                    "SELECT task_id, root_id, depth, resource_class, has_expensive_descendant, distance_to_nearest_slow_descendant, attempts FROM tasks WHERE task_id=?",
                    (task_id,),
                ).fetchone()
                if row is not None:
                    candidates.append(_task_row_to_item(row))
                print(f"  ⟳ {task_id:20s} retry attempt {attempts}", flush=True)
            else:
                _mark_failed(conn, task_id, str(exc))
                _refresh_root_flags(conn, roots[root_id])
                print(f"  ✗ {task_id:20s} terminal: {exc}", flush=True)
            return

        _mark_done(conn, task_id, str(result.get("result", "ok")))
        unlocked = _unlock_children(conn, task_id)
        candidates.extend(unlocked)
        _refresh_root_flags(conn, roots[root_id])

        suffix = f"→ {len(unlocked)} children" if unlocked else "→ leaf"
        print(
            f"  ✓ {task_id:20s} (d={item['depth']} {item['resource_class']}) {suffix}",
            flush=True,
        )

        if _root_complete(conn, root_id) and root_id not in completed_roots:
            completed_roots.add(root_id)
            print(f"  🏁 {root_id} COMPLETE", flush=True)

    gate_stop = asyncio.Event()
    gate_task = asyncio.create_task(_toggle_slow_gate(resources, gate_stop))

    try:
        await run(
            candidates=candidates,
            roots=roots,
            resources=resources,
            dispatch=dispatch,
            max_workers=args.max_workers,
            max_active_roots=3,
        )
    except KeyboardInterrupt:
        pending = _pending_total(conn)
        print(f"Interrupted. Pending tasks: {pending}. Resume with --resume", flush=True)
    finally:
        gate_stop.set()
        gate_task.cancel()
        try:
            await gate_task
        except asyncio.CancelledError:
            pass
        except Exception:
            pass

    pending = _pending_total(conn)
    if pending == 0:
        print("✅ All roots complete.", flush=True)
    else:
        print(f"Run paused with {pending} tasks remaining. Use --resume.", flush=True)

    return 0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="DFSS pipeline demo (upfront workflow shape)")
    parser.add_argument("--roots", type=int, default=8)
    parser.add_argument("--max-depth", type=int, default=3)
    parser.add_argument("--max-workers", type=int, default=4)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--fail-rate", type=float, default=0.15)
    parser.add_argument("--db-path", type=str, default="data/dfss.sqlite")
    parser.add_argument("--resume", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    code = asyncio.run(_run_pipeline(args))
    raise SystemExit(code)


if __name__ == "__main__":
    main()
