"""
CLI Tool Use Hooks.

Provides the tool provider, file tracking, and human review action.
"""

from typing import Any, Dict

from flatmachines import MachineHooks
from .tools import CLIToolProvider


class CLIToolHooks(MachineHooks):
    """Hooks for CLI tool-use workflow with human-in-the-loop review."""

    def __init__(self, working_dir: str = "."):
        self._provider = CLIToolProvider(working_dir)

    def get_tool_provider(self, state_name: str):
        return self._provider

    def on_action(self, action_name: str, context: Dict[str, Any]) -> Dict[str, Any]:
        if action_name == "human_review":
            return self._human_review(context)
        return context

    def on_tool_result(self, state_name: str, tool_result: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """Track files modified by write/edit tools."""
        name = tool_result.get("name", "")
        is_error = tool_result.get("is_error", False)

        if not is_error and name in ("write", "edit"):
            path = tool_result.get("arguments", {}).get("path", "")
            if path:
                modified = context.setdefault("files_modified", [])
                if path not in modified:
                    modified.append(path)

        return context

    def _human_review(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Pause for human review of the agent's work."""
        print()
        print("=" * 60)
        print("HUMAN REVIEW")
        print("=" * 60)
        print(f"\nIteration #{context.get('iteration', 1)}")

        # Show what the agent did
        result = context.get("result", "")
        if result:
            print(f"\nAgent response:")
            print("-" * 40)
            print(result)
            print("-" * 40)

        files = context.get("files_modified", [])
        if files:
            print(f"\nFiles modified: {', '.join(files)}")

        print(f"\nTool calls: {context.get('tool_calls', 0)}")
        print(f"Cost so far: ${float(context.get('cost', 0)):.4f}")

        response = input("\nApprove? (y/yes to approve, or enter feedback): ").strip()

        if response.lower() in ("y", "yes", ""):
            context["human_approved"] = True
            context["feedback"] = ""
            print("✓ Approved!")
        else:
            context["human_approved"] = False
            context["feedback"] = response
            print(f"→ Feedback recorded. Running again...")

        print("=" * 60)
        print()
        return context
