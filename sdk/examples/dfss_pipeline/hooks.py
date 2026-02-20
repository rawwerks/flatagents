from __future__ import annotations

import random
from typing import Any, Dict

from flatmachines import MachineHooks


class TaskHooks(MachineHooks):
    """Task execution hooks for DFSS example.

    Important: hooks simulate execution/failure only. They do not emit children.
    """

    def __init__(self, max_depth: int = 3, fail_rate: float = 0.15, seed: int = 7):
        self.max_depth = max_depth
        self.fail_rate = float(fail_rate)
        self._rng = random.Random(seed)

    def on_action(self, action_name: str, context: Dict[str, Any]) -> Dict[str, Any]:
        if action_name != "run_task":
            return context

        if self._rng.random() < self.fail_rate:
            task_id = context.get("task_id", "unknown")
            raise RuntimeError(f"transient failure in {task_id}")

        task_id = context.get("task_id", "unknown")
        context["result"] = f"ok:{task_id}"

        # Explicitly avoid runtime child discovery in this implementation.
        if "children" in context:
            context.pop("children", None)

        return context
