import asyncio
from pathlib import Path

from flatmachines import FlatMachine

from .hooks import CloneMachineHooks


def _config_path(name: str) -> str:
    return str(Path(__file__).resolve().parents[3] / "config" / name)


async def run():
    hooks = CloneMachineHooks()

    machine = FlatMachine(
        config_file=_config_path("machine.yml"),
        hooks=hooks,
    )
    hooks.bind_machine(machine)

    result = await machine.execute(input={})

    print("---")
    print(f"Execution ID: {machine.execution_id}")
    print(f"Result: {result}")


def main():
    asyncio.run(run())


if __name__ == "__main__":
    main()
