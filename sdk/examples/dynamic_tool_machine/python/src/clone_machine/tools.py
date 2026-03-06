from __future__ import annotations

import importlib.util
import json
import shutil
import tempfile
import textwrap
import uuid
from pathlib import Path
from typing import Any, Dict

from flatagents.tools import ToolResult
from flatmachines import FlatMachine

from .invoker import GeneratedToolSubprocessInvoker


class ParentToolProvider:
    """Native tools for phase 1.

    - generate_native_tool: deterministic codegen (new artifact each run)
    - launch_generated_machine: launch subprocess child that loads artifact

    Launching is delegated to GeneratedToolSubprocessInvoker.
    """

    def __init__(
        self,
        *,
        invoker: GeneratedToolSubprocessInvoker | None = None,
        launch_timeout_seconds: float = 90.0,
        keep_artifacts: bool = False,
    ):
        self._machine = None
        self._last_artifact_dir: Path | None = None
        self._last_manifest: dict[str, Any] | None = None
        self._invoker = invoker or GeneratedToolSubprocessInvoker(cwd=str(_python_root()))
        self._launch_timeout_seconds = launch_timeout_seconds
        self._keep_artifacts = keep_artifacts

    def bind_machine(self, machine: FlatMachine) -> None:
        self._machine = machine

    def get_tool_definitions(self):
        return []

    async def execute_tool(self, name: str, tool_call_id: str, arguments: Dict[str, object]) -> ToolResult:
        if self._machine is None:
            return ToolResult(content="Tool provider not bound to machine", is_error=True)

        if name == "generate_native_tool":
            return await self._generate_native_tool()
        if name == "launch_generated_machine":
            return await self._launch_generated_machine()

        return ToolResult(content=f"Unknown tool: {name}", is_error=True)

    def _cleanup_artifact_dir(self, artifact_dir: Path | None) -> None:
        if artifact_dir and artifact_dir.exists():
            shutil.rmtree(artifact_dir, ignore_errors=True)

    def _cleanup_previous_artifacts(self) -> None:
        if self._keep_artifacts:
            return
        self._cleanup_artifact_dir(self._last_artifact_dir)
        self._last_artifact_dir = None
        self._last_manifest = None

    async def _generate_native_tool(self) -> ToolResult:
        # Keep at most one artifact tree by default to avoid tempdir leaks.
        self._cleanup_previous_artifacts()

        run_id = uuid.uuid4().hex[:10]
        tool_name = f"generated_native_tool_{run_id}"

        artifact_dir = Path(tempfile.mkdtemp(prefix=f"clone_machine_{run_id}_"))
        module_path = artifact_dir / "generated_tool.py"
        manifest_path = artifact_dir / "tool_manifest.json"

        module_code = textwrap.dedent(
            f"""
            from __future__ import annotations

            def run(arguments: dict) -> str:
                text = str(arguments.get("text", ""))
                return "generated_tool run_id={run_id} received: " + text
            """
        ).strip() + "\n"

        manifest = {
            "run_id": run_id,
            "tool_name": tool_name,
            "description": f"Generated native tool for run {run_id}",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Text payload for generated tool"}
                },
                "required": ["text"],
            },
            "module_file": str(module_path),
            "entrypoint": "run",
        }

        module_path.write_text(module_code)
        manifest_path.write_text(json.dumps(manifest, indent=2))

        self._last_artifact_dir = artifact_dir
        self._last_manifest = manifest

        return ToolResult(
            content=json.dumps(
                {
                    "status": "generated",
                    "run_id": run_id,
                    "tool_name": tool_name,
                    "artifact_dir": str(artifact_dir),
                },
                indent=2,
            )
        )

    async def _launch_generated_machine(self) -> ToolResult:
        if self._last_artifact_dir is None:
            return ToolResult(content="No generated tool available. Call generate_native_tool first.", is_error=True)

        artifact_dir = self._last_artifact_dir
        manifest = dict(self._last_manifest or {})
        child_id = str(uuid.uuid4())
        result_file = artifact_dir / f"child_result_{child_id}.json"
        child_config = str(_config_path("child_machine.yml"))

        launch = await self._invoker.launch(
            child_config=child_config,
            artifact_dir=str(artifact_dir),
            child_execution_id=child_id,
            result_file=str(result_file),
            task=f"use generated tool from {manifest.get('run_id', 'unknown')} and report",
            timeout_seconds=self._launch_timeout_seconds,
        )

        payload = {
            "status": launch.status,
            "child_execution_id": launch.child_execution_id,
            "artifact_dir": str(artifact_dir),
            "tool_name": manifest.get("tool_name"),
            "stdout": launch.stdout,
            "stderr": launch.stderr,
            "returncode": launch.returncode,
        }
        if launch.child_payload is not None:
            payload["child_payload"] = launch.child_payload

        is_error = launch.status != "launched_subprocess"

        # Artifact lifecycle: clean generated artifacts after launch by default.
        if not self._keep_artifacts:
            self._cleanup_artifact_dir(artifact_dir)
            self._last_artifact_dir = None
            self._last_manifest = None
            payload["artifacts_retained"] = False
        else:
            payload["artifacts_retained"] = True

        return ToolResult(content=json.dumps(payload, indent=2), is_error=is_error)


class GeneratedToolProvider:
    """Tool provider used by child subprocess.

    It reconstructs the generated native tool from artifact manifest + module file.
    """

    def __init__(self, artifact_dir: str | Path):
        self._artifact_dir = Path(artifact_dir)
        self._manifest = self._load_manifest()
        self._callable = self._load_callable()

    def _load_manifest(self) -> dict[str, Any]:
        manifest_path = self._artifact_dir / "tool_manifest.json"
        if not manifest_path.exists():
            raise FileNotFoundError(f"tool_manifest.json not found in {self._artifact_dir}")
        return json.loads(manifest_path.read_text())

    def _load_callable(self):
        module_file = Path(self._manifest["module_file"])
        entrypoint = self._manifest.get("entrypoint", "run")

        spec = importlib.util.spec_from_file_location("clone_machine_generated_tool", module_file)
        if spec is None or spec.loader is None:
            raise RuntimeError(f"Could not load generated module: {module_file}")

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        fn = getattr(module, entrypoint, None)
        if fn is None:
            raise RuntimeError(f"Entrypoint '{entrypoint}' not found in {module_file}")
        return fn

    def get_tool_definitions(self):
        return [
            {
                "type": "function",
                "function": {
                    "name": self._manifest["tool_name"],
                    "description": self._manifest["description"],
                    "parameters": self._manifest["parameters"],
                },
            }
        ]

    async def execute_tool(self, name: str, tool_call_id: str, arguments: Dict[str, object]) -> ToolResult:
        expected = self._manifest["tool_name"]
        if name != expected:
            return ToolResult(content=f"Unknown generated tool: {name}", is_error=True)

        try:
            value = self._callable(arguments)
            return ToolResult(content=str(value))
        except Exception as e:
            return ToolResult(content=f"Generated tool failed: {e}", is_error=True)


def _python_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _config_path(name: str) -> Path:
    return Path(__file__).resolve().parents[3] / "config" / name
