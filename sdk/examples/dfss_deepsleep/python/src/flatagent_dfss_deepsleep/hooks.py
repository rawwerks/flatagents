"""
Hooks for DFSS Deep Sleep.

Two roles:
  - Scheduler actions: pick_batch, process_results
  - Task actions: run_task, signal_ready

In a real deployment these would be separate hook classes.
Combined here for simplicity.
"""
from __future__ import annotations

import random
from typing import Any, Dict, List, Optional

from flatmachines import MachineHooks


class DeepSleepHooks(MachineHooks):

    def __init__(
        self,
        max_depth: int = 3,
        fail_rate: float = 0.0,
        seed: int = 7,
        # Injected at runtime for signal/work integration
        work_backend=None,
        signal_backend=None,
        pool_name: str = "tasks",
    ):
        self.max_depth = max_depth
        self.fail_rate = fail_rate
        self._rng = random.Random(seed)
        self.work_backend = work_backend
        self.signal_backend = signal_backend
        self.pool_name = pool_name

    # ── Scheduler actions ──────────────────────────────────────

    def on_action(self, action_name: str, context: Dict[str, Any]) -> Dict[str, Any]:
        dispatch = {
            "pick_batch": self._pick_batch,
            "process_results": self._process_results,
            "run_task": self._run_task,
            "signal_ready": self._signal_ready,
        }
        handler = dispatch.get(action_name)
        if handler:
            return handler(context)
        return context

    def _pick_batch(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Score candidates from work pool, select up to batch_size."""
        candidates = context.get("_candidates", [])
        batch_size = int(context.get("batch_size", 4))
        roots = context.get("roots", {})
        max_active = int(context.get("max_active_roots", 3))

        active_root_ids = {
            rid for rid, r in roots.items()
            if r.get("admitted") and not self._root_done(r)
        }

        newly_admitted: set = set()
        scored = []
        for c in candidates:
            rid = c["root_id"]
            if rid not in roots:
                roots[rid] = {"admitted": False, "completed": 0, "terminal_failures": 0}
            root = roots[rid]
            is_active = rid in active_root_ids or rid in newly_admitted
            can_admit = (len(active_root_ids) + len(newly_admitted)) < max_active

            if not is_active and not can_admit:
                continue

            if not is_active:
                newly_admitted.add(rid)

            s = self._score(c, root, is_active)
            scored.append((s, c))

        scored.sort(key=lambda x: x[0], reverse=True)
        batch = [c for _, c in scored[:batch_size]]

        # Mark admitted
        for c in batch:
            roots[c["root_id"]]["admitted"] = True

        context["batch"] = batch
        context["roots"] = roots
        context["all_done"] = (not candidates and not batch)
        return context

    def _process_results(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Process batch results: count completions, collect children."""
        results = context.get("batch_results", [])
        roots = context.get("roots", {})
        new_children = []

        if isinstance(results, list):
            items = results
        elif isinstance(results, dict):
            items = list(results.values())
        else:
            items = []

        for result in items:
            if not isinstance(result, dict):
                continue
            rid = result.get("root_id", "")
            if rid in roots:
                if result.get("error"):
                    roots[rid]["terminal_failures"] = roots[rid].get("terminal_failures", 0) + 1
                else:
                    roots[rid]["completed"] = roots[rid].get("completed", 0) + 1

            children = result.get("children", [])
            if isinstance(children, list):
                new_children.extend(children)

        # Push children to work pool (done by caller in tests, by signal_backend in prod)
        context["_new_children"] = new_children
        context["batch"] = []
        context["batch_results"] = []
        context["roots"] = roots

        # Check if all roots done
        all_done = all(self._root_done(r) for r in roots.values()) if roots else False
        context["all_done"] = all_done
        return context

    @staticmethod
    def _root_done(root: Dict[str, Any]) -> bool:
        return root.get("admitted", False) and root.get("_pending", 0) <= 0

    @staticmethod
    def _score(item: Dict[str, Any], root: Dict[str, Any], is_active: bool) -> float:
        depth = float(item.get("depth", 0))
        s = 0.0
        s += 300.0 if is_active else 0.0
        s += depth * 18.0
        s += 120.0 if item.get("resource_class") == "slow" else 0.0
        return s

    # ── Task actions ───────────────────────────────────────────

    def _run_task(self, context: Dict[str, Any]) -> Dict[str, Any]:
        if self._rng.random() < self.fail_rate:
            raise RuntimeError(f"transient failure in {context.get('task_id')}")

        task_id = str(context.get("task_id", ""))
        root_id = str(context.get("root_id", ""))
        depth = int(context.get("depth", 0))

        children = self._generate_children(task_id, root_id, depth)
        context["children"] = children
        context["result"] = f"ok:{task_id}"
        return context

    def _signal_ready(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Signal that work is ready. No-op in unit tests (no signal backend)."""
        # In production: self.signal_backend.send("dfss/ready", {...})
        return context

    def _generate_children(
        self, task_id: str, root_id: str, depth: int
    ) -> List[Dict[str, Any]]:
        if depth >= self.max_depth:
            return []

        n = self._rng.randint(0, 2)
        children = []
        for i in range(n):
            children.append({
                "task_id": f"{task_id}.{i}",
                "root_id": root_id,
                "depth": depth + 1,
                "resource_class": self._rng.choice(["fast", "slow"]),
            })
        return children
