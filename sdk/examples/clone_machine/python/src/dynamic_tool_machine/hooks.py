from __future__ import annotations

import uuid
from typing import Any, Dict

from flatmachines import CheckpointManager, MachineHooks, clone_snapshot


class CloneMachineHooks(MachineHooks):
    """Implements a deterministic clone_machine action.

    Behavior:
    - Uses the latest checkpoint saved immediately before state execution
      (event == "execute")
    - Clones that snapshot to a new execution ID
    - Stores structured clone metadata in context['clone']
    """

    def __init__(self):
        self._machine = None

    def bind_machine(self, machine) -> None:
        self._machine = machine

    async def on_action(self, action_name: str, context: Dict[str, Any]) -> Dict[str, Any]:
        if action_name != "clone_machine":
            return context

        if self._machine is None:
            raise RuntimeError("CloneMachineHooks must be bound to a machine before use")

        manager = CheckpointManager(self._machine.persistence, self._machine.execution_id)
        source = await manager.load_latest()
        if source is None:
            raise RuntimeError("No source checkpoint found for clone_machine action")

        # The pre-action checkpoint is the one saved right before _execute_state.
        if source.event != "execute":
            raise RuntimeError(
                f"clone_machine expected latest checkpoint event='execute', got '{source.event}'"
            )

        cloned_execution_id = f"{self._machine.execution_id}:clone:{uuid.uuid4().hex[:8]}"
        cloned = await clone_snapshot(
            snapshot=source,
            new_execution_id=cloned_execution_id,
            persistence=self._machine.persistence,
        )

        updated = dict(context)
        updated["clone"] = {
            "status": "cloned",
            "source_execution_id": source.execution_id,
            "source_state": source.current_state,
            "source_event": source.event,
            "cloned_execution_id": cloned.execution_id,
            "cloned_parent_execution_id": cloned.parent_execution_id,
        }
        return updated
