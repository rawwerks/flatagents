import asyncio
from pathlib import Path

from flatmachines import FlatMachine

from .tools import (
    MachineRegistry,
    InstanceTracker,
    DynamicMachineToolProvider,
    DynamicInlineInvoker,
)


def _config_path(name: str) -> str:
    return str(Path(__file__).resolve().parents[3] / "config" / name)


async def run():
    registry = MachineRegistry()
    tracker = InstanceTracker()
    provider = DynamicMachineToolProvider(registry=registry, tracker=tracker)
    invoker = DynamicInlineInvoker(registry=registry, tracker=tracker)

    machine = FlatMachine(
        config_file=_config_path("machine.yml"),
        tool_provider=provider,
        invoker=invoker,
    )
    provider.bind_machine(machine)

    result = await machine.execute(input={
        "task": "Discover machines and launch if needed.",
    })

    # Wait for any launched instances to finish
    await tracker.wait_all()

    print("---")
    print(f"Result: {result}")
    print(f"Cost: ${machine.total_cost:.4f} | API calls: {machine.total_api_calls}")


def main():
    asyncio.run(run())


if __name__ == "__main__":
    main()
