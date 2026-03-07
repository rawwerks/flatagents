"""
Machine resume abstraction.

Provides an ABC for resuming parked machines and a concrete implementation
that reconstructs from the config stored in a content-addressed ConfigStore,
referenced by the checkpoint's ``config_hash``.

Usage (simple — no hooks):

    resumer = ConfigStoreResumer(signal_backend, persistence, config_store)
    dispatcher = SignalDispatcher(signal_backend, persistence, resumer=resumer)

Usage (with hooks registry):

    registry = HooksRegistry()
    registry.register("my-hooks", MyHooks)
    resumer = ConfigStoreResumer(
        signal_backend, persistence, config_store,
        hooks_registry=registry,
    )

Usage (subclass for app-specific reconstruction):

    class MyResumer(ConfigStoreResumer):
        def __init__(self, signal_backend, persistence, config_store, db_path):
            super().__init__(signal_backend, persistence, config_store)
            self._db_path = db_path

        async def build_machine(self, execution_id, snapshot, config_dict):
            machine = await super().build_machine(execution_id, snapshot, config_dict)
            # ... customize machine ...
            return machine
"""

import json
import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

from .hooks import MachineHooks, HooksRegistry
from .persistence import (
    CheckpointManager,
    ConfigStore,
    MachineSnapshot,
    PersistenceBackend,
)
from .signals import SignalBackend

logger = logging.getLogger(__name__)


class MachineResumer(ABC):
    """Knows how to reconstruct and resume a parked machine from checkpoint."""

    @abstractmethod
    async def resume(self, execution_id: str, signal_data: Any) -> Any:
        """Resume a parked machine.

        Args:
            execution_id: The execution ID of the parked machine.
            signal_data: Data from the signal that triggered resume.

        Returns:
            The machine's final output dict.
        """
        ...


class ConfigStoreResumer(MachineResumer):
    """Resumes a machine from config stored in a content-addressed ConfigStore.

    Reads ``config_hash`` from the checkpoint, fetches the raw config from the
    store, parses it, and reconstructs the FlatMachine.

    Supports optional hooks, hooks_registry, and tool_provider injection.
    If a hooks_registry is provided and the machine config references hooks
    by name, they will be resolved automatically — same as initial execution.

    For app-specific reconstruction (custom DB connections, environment setup,
    etc.), subclass and override ``build_machine()``.

    Args:
        signal_backend: Signal storage backend.
        persistence_backend: Checkpoint persistence backend.
        config_store: Content-addressed config store.
        hooks: Explicit MachineHooks instance (bypasses registry).
        hooks_registry: Registry for resolving hooks by name from config.
        tool_provider: Default ToolProvider for tool_loop states.
    """

    def __init__(
        self,
        signal_backend: SignalBackend,
        persistence_backend: PersistenceBackend,
        config_store: ConfigStore,
        hooks: Optional[MachineHooks] = None,
        hooks_registry: Optional[HooksRegistry] = None,
        tool_provider: Optional[Any] = None,
    ):
        self._signal_backend = signal_backend
        self._persistence = persistence_backend
        self._config_store = config_store
        self._hooks = hooks
        self._hooks_registry = hooks_registry
        self._tool_provider = tool_provider

    async def _load_snapshot(self, execution_id: str) -> MachineSnapshot:
        """Load the latest checkpoint for an execution ID."""
        snapshot = await CheckpointManager(
            self._persistence, execution_id
        ).load_latest()
        if not snapshot:
            raise RuntimeError(f"No checkpoint found for execution {execution_id}")
        return snapshot

    async def _load_config(self, snapshot: MachineSnapshot) -> Dict[str, Any]:
        """Load and parse config from the config store."""
        if not snapshot.config_hash:
            raise RuntimeError(
                f"No config_hash in checkpoint for execution {snapshot.execution_id}. "
                f"Machine was created without a config_store. "
                f"Provide a custom MachineResumer subclass for this case."
            )

        raw = await self._config_store.get(snapshot.config_hash)
        if raw is None:
            raise RuntimeError(
                f"Config not found in store for hash {snapshot.config_hash}. "
                f"The config store may have been cleaned up."
            )

        # Parse YAML or JSON
        try:
            import yaml
            return yaml.safe_load(raw)
        except ImportError:
            return json.loads(raw)

    async def build_machine(
        self,
        execution_id: str,
        snapshot: MachineSnapshot,
        config_dict: Dict[str, Any],
    ):
        """Construct a FlatMachine ready for resume.

        Override this method to customize machine reconstruction (e.g.
        inject app-specific hooks, tools, or environment).

        Args:
            execution_id: The execution ID to resume.
            snapshot: The latest checkpoint snapshot.
            config_dict: Parsed machine config from the config store.

        Returns:
            A FlatMachine instance configured for resume.
        """
        from .flatmachine import FlatMachine

        return FlatMachine(
            config_dict=config_dict,
            persistence=self._persistence,
            signal_backend=self._signal_backend,
            config_store=self._config_store,
            hooks=self._hooks,
            hooks_registry=self._hooks_registry,
            tool_provider=self._tool_provider,
        )

    async def resume(self, execution_id: str, signal_data: Any) -> Any:
        """Load checkpoint, reconstruct machine, and resume execution."""
        snapshot = await self._load_snapshot(execution_id)
        config_dict = await self._load_config(snapshot)
        machine = await self.build_machine(execution_id, snapshot, config_dict)
        result = await machine.execute(resume_from=execution_id)
        logger.info(f"Resumed {execution_id}: {result}")
        return result


# Backward-compatible alias
ConfigFileResumer = ConfigStoreResumer

__all__ = [
    "MachineResumer",
    "ConfigStoreResumer",
    "ConfigFileResumer",
]
