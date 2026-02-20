from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class RootState:
    root_id: str
    admitted: bool = False
    in_flight: int = 0
    pending: int = 0
    completed: int = 0
    has_pending_expensive: bool = False

    @property
    def is_done(self) -> bool:
        return self.pending <= 0 and self.in_flight <= 0


@dataclass
class ResourcePool:
    name: str
    capacity: int
    in_flight: int = 0
    gate_open: bool = True

    @property
    def available(self) -> int:
        if not self.gate_open:
            return 0
        return max(0, self.capacity - self.in_flight)


def score(item: Dict[str, Any], root: RootState, is_active: bool) -> float:
    s = 0.0
    s += 100.0 if is_active else 0.0
    s += 8.0 * float(item.get("depth", 0))
    s += 45.0 if item.get("resource_class") == "slow" else 0.0
    s += 28.0 if item.get("has_expensive_descendant") else 0.0

    distance = item.get("distance_to_nearest_slow_descendant")
    if distance is not None:
        try:
            d = float(distance)
            if d < 10_000:
                s += max(0.0, 20.0 - (4.0 * d))
        except (TypeError, ValueError):
            pass

    if root.has_pending_expensive:
        s += 10.0

    s -= 0.1 * float(max(root.pending, 0))
    return s


def pick_next(
    candidates: List[Dict[str, Any]],
    roots: Dict[str, RootState],
    resources: Dict[str, ResourcePool],
    max_active_roots: int,
) -> Optional[Dict[str, Any]]:
    active_root_ids = {
        r.root_id for r in roots.values() if r.admitted and not r.is_done
    }

    runnable: List[Dict[str, Any]] = []
    for item in candidates:
        pool = resources.get(item.get("resource_class"))
        if pool is None:
            continue
        if pool.available > 0:
            runnable.append(item)

    if not runnable:
        return None

    active = [c for c in runnable if c.get("root_id") in active_root_ids]
    new = [c for c in runnable if c.get("root_id") not in active_root_ids]

    if active:
        pool = active
    elif len(active_root_ids) < max_active_roots:
        pool = new
    else:
        return None

    return max(
        pool,
        key=lambda c: score(c, roots[c["root_id"]], c.get("root_id") in active_root_ids),
    )


async def run(
    candidates: List[Dict[str, Any]],
    roots: Dict[str, RootState],
    resources: Dict[str, ResourcePool],
    dispatch,
    max_workers: int,
    max_active_roots: int,
) -> None:
    active_tasks: set[asyncio.Task] = set()

    while True:
        while len(active_tasks) < max_workers:
            item = pick_next(candidates, roots, resources, max_active_roots)
            if item is None:
                break

            candidates.remove(item)
            root = roots[item["root_id"]]
            root.admitted = True
            root.in_flight += 1
            resources[item["resource_class"]].in_flight += 1

            t = asyncio.create_task(dispatch(item))
            setattr(t, "_dfss_item", item)
            active_tasks.add(t)

        if not active_tasks:
            if not candidates:
                return
            await asyncio.sleep(0.05)
            continue

        done, _ = await asyncio.wait(active_tasks, return_when=asyncio.FIRST_COMPLETED)
        for t in done:
            active_tasks.discard(t)
            item = getattr(t, "_dfss_item")
            roots[item["root_id"]].in_flight -= 1
            resources[item["resource_class"]].in_flight -= 1
