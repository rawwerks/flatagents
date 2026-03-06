import asyncio
import os
from pathlib import Path

from flatmachines import FlatMachine

from .tools import ParentToolProvider


def _config_path(name: str) -> str:
    return str(Path(__file__).resolve().parents[3] / "config" / name)


async def run():
    keep_artifacts = os.getenv("CLONE_MACHINE_KEEP_ARTIFACTS", "0") == "1"
    provider = ParentToolProvider(keep_artifacts=keep_artifacts)

    machine = FlatMachine(
        config_file=_config_path("machine.yml"),
        tool_provider=provider,
    )
    provider.bind_machine(machine)

    result = await machine.execute(input={
        "task": "Generate a native tool for this run, then launch the child subprocess.",
    })

    print("---")
    print(f"Result: {result}")
    print(f"Cost: ${machine.total_cost:.4f} | API calls: {machine.total_api_calls}")


def main():
    asyncio.run(run())


if __name__ == "__main__":
    main()
