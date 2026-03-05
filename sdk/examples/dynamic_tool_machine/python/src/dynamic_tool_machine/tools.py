from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any, Dict


from flatagents.tools import ToolResult
from flatmachines import FlatMachine, make_uri
from flatmachines.actions import InlineInvoker


class MachineRegistry:
    """In-memory store of machine configs, keyed by name.

    Machines register themselves on init. launch_machine resolves
    targets from this registry.
    """

    def __init__(self):
        self._configs: Dict[str, Dict[str, Any]] = {}
        self._config_dirs: Dict[str, str] = {}
        self._profiles: Dict[str, Any] = {}  # name -> (profiles_dict, profiles_file)

    def register(
        self,
        name: str,
        config: Dict[str, Any],
        config_dir: str,
        profiles_dict: Any = None,
        profiles_file: str | None = None,
    ) -> None:
        self._configs[name] = config
        self._config_dirs[name] = config_dir
        self._profiles[name] = (profiles_dict, profiles_file)

    def get(self, name: str) -> Dict[str, Any] | None:
        return self._configs.get(name)

    def get_config_dir(self, name: str) -> str | None:
        return self._config_dirs.get(name)

    def get_profiles(self, name: str) -> tuple[Any, str | None]:
        return self._profiles.get(name, (None, None))

    def list_machines(self) -> list[str]:
        return sorted(self._configs.keys())


class InstanceTracker:
    """Tracks running instances per machine name.

    Both the original and any launched instance appear the same way.
    No hierarchy — just a set of execution IDs per name.
    """

    def __init__(self):
        self._instances: Dict[str, set[str]] = {}  # machine_name -> {exec_ids}
        self._lock = asyncio.Lock()
        self._tasks: list[asyncio.Task] = []

    async def add(self, machine_name: str, execution_id: str) -> None:
        async with self._lock:
            self._instances.setdefault(machine_name, set()).add(execution_id)

    async def remove(self, machine_name: str, execution_id: str) -> None:
        async with self._lock:
            ids = self._instances.get(machine_name)
            if ids:
                ids.discard(execution_id)
                if not ids:
                    del self._instances[machine_name]

    async def get_instances(self, machine_name: str) -> list[str]:
        async with self._lock:
            return sorted(self._instances.get(machine_name, set()))

    async def count(self, machine_name: str) -> int:
        async with self._lock:
            return len(self._instances.get(machine_name, set()))

    def track_task(self, task: asyncio.Task) -> None:
        self._tasks.append(task)

    async def wait_all(self) -> None:
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
            self._tasks.clear()


class DynamicInlineInvoker(InlineInvoker):
    """Inline invoker that propagates this example's dynamic tool provider."""

    def __init__(self, registry: MachineRegistry, tracker: InstanceTracker):
        super().__init__()
        self._registry = registry
        self._tracker = tracker

    async def invoke(
        self,
        caller_machine,
        target_config: Dict[str, Any],
        input_data: Dict[str, Any],
        execution_id: str | None = None,
    ) -> Dict[str, Any]:
        if not execution_id:
            execution_id = str(uuid.uuid4())

        await self.launch(
            caller_machine=caller_machine,
            target_config=target_config,
            input_data=input_data,
            execution_id=execution_id,
        )

        uri = make_uri(execution_id, "result")
        return await caller_machine.result_backend.read(uri, block=True)

    async def launch(
        self,
        caller_machine,
        target_config: Dict[str, Any],
        input_data: Dict[str, Any],
        execution_id: str,
    ) -> None:
        target_name = target_config.get("data", {}).get("name", "unknown")

        child_provider = DynamicMachineToolProvider(
            registry=self._registry,
            tracker=self._tracker,
        )

        child_machine = FlatMachine(
            config_dict=target_config,
            hooks_registry=getattr(caller_machine, "_hooks_registry", None),
            persistence=caller_machine.persistence,
            lock=caller_machine.lock,
            result_backend=caller_machine.result_backend,
            signal_backend=caller_machine.signal_backend,
            trigger_backend=caller_machine.trigger_backend,
            agent_registry=caller_machine.agent_registry,
            tool_provider=child_provider,
            _config_dir=caller_machine._config_dir,
            _execution_id=execution_id,
            _parent_execution_id=caller_machine.execution_id,
            _profiles_dict=getattr(caller_machine, "_profiles_dict", None),
            _profiles_file=getattr(caller_machine, "_profiles_file", None),
        )
        child_provider.bind_machine(child_machine)

        # Register immediately so parent and child see symmetric instance state.
        await self._tracker.add(target_name, execution_id)
        child_provider._registered = True

        async def _execute_and_write():
            try:
                result = await child_machine.execute(input=input_data)
                uri = make_uri(execution_id, "result")
                await caller_machine.result_backend.write(uri, result)
            except Exception as e:
                uri = make_uri(execution_id, "result")
                await caller_machine.result_backend.write(uri, {
                    "_error": str(e),
                    "_error_type": type(e).__name__,
                })
                raise
            finally:
                await child_provider._deregister()

        task = asyncio.create_task(_execute_and_write())
        caller_machine._background_tasks.add(task)
        task.add_done_callback(caller_machine._background_tasks.discard)


class DynamicMachineToolProvider:
    """Tools: discover_machines, launch_machine."""

    def __init__(
        self,
        registry: MachineRegistry,
        tracker: InstanceTracker,
    ):
        self._machine = None
        self._registry = registry
        self._tracker = tracker
        self._registered = False

    @property
    def registry(self) -> MachineRegistry:
        return self._registry

    @property
    def tracker(self) -> InstanceTracker:
        return self._tracker

    def bind_machine(self, machine) -> None:
        self._machine = machine
        self._registered = False

    async def _ensure_registered(self) -> None:
        """Register this machine instance in the registry and tracker on first use."""
        if self._registered or self._machine is None:
            return
        name = self._machine.machine_name
        self._registry.register(
            name=name,
            config=self._machine.config,
            config_dir=self._machine._config_dir,
            profiles_dict=self._machine._profiles_dict,
            profiles_file=self._machine._profiles_file,
        )
        await self._tracker.add(name, self._machine.execution_id)
        self._registered = True

    async def _deregister(self) -> None:
        if self._machine is not None:
            await self._tracker.remove(
                self._machine.machine_name,
                self._machine.execution_id,
            )

    def get_tool_definitions(self):
        return []

    async def execute_tool(self, name: str, tool_call_id: str, arguments: Dict[str, object]) -> ToolResult:
        if self._machine is None:
            return ToolResult(content="Tool provider not bound to machine", is_error=True)

        await self._ensure_registered()

        if name == "discover_machines":
            return await self._discover(arguments)
        elif name == "launch_machine":
            return await self._launch(arguments)
        else:
            return ToolResult(content=f"Unknown tool: {name}", is_error=True)

    async def _discover(self, arguments: Dict) -> ToolResult:
        machines = self._registry.list_machines()
        instances: Dict[str, Any] = {}
        for m in machines:
            instances[m] = {
                "running": await self._tracker.count(m),
                "instance_ids": [
                    eid[:12] for eid in await self._tracker.get_instances(m)
                ],
            }
        payload = {
            "self_name": self._machine.machine_name,
            "self_id": self._machine.execution_id[:12],
            "machines": instances,
        }
        return ToolResult(content=json.dumps(payload, indent=2))

    async def _launch(self, arguments: Dict) -> ToolResult:
        target = arguments.get("target")
        if not target:
            return ToolResult(content="Missing required parameter: target", is_error=True)

        config = self._registry.get(target)
        if config is None:
            return ToolResult(
                content=f"Unknown machine: {target}. Available: {self._registry.list_machines()}",
                is_error=True,
            )

        # Check if another instance is already running (beyond this one if targeting self)
        running = await self._tracker.get_instances(target)
        if target == self._machine.machine_name:
            others = [eid for eid in running if eid != self._machine.execution_id]
        else:
            others = running

        if others:
            return ToolResult(content=json.dumps({
                "status": "already_running",
                "target": target,
                "instances": [eid[:12] for eid in others],
            }, indent=2))

        # Launch a new instance through the machine's invoker (InlineInvoker in this example)
        new_id = str(uuid.uuid4())

        await self._machine.invoker.launch(
            caller_machine=self._machine,
            target_config=config,
            input_data={
                "task": f"You are a new instance of {target}. Discover machines and report status.",
            },
            execution_id=new_id,
        )

        return ToolResult(content=json.dumps({
            "status": "launched",
            "target": target,
            "new_instance_id": new_id[:12],
            "total_running": await self._tracker.count(target),
        }, indent=2))
