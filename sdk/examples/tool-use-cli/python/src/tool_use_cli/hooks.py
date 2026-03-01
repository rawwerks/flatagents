"""
CLI Tool Use Hooks.

Provides the tool provider, file tracking, per-call display, and human review.
"""

import sys
from typing import Any, Dict, List

from flatmachines import MachineHooks
from .tools import CLIToolProvider


def _dim(text: str) -> str:
    return f"\033[2m{text}\033[0m"


def _bold(text: str) -> str:
    return f"\033[1m{text}\033[0m"


class CLIToolHooks(MachineHooks):
    """Hooks for CLI tool-use workflow with per-call display and human review."""

    def __init__(self, working_dir: str = "."):
        self._provider = CLIToolProvider(working_dir)

    def get_tool_provider(self, state_name: str):
        return self._provider

    def on_action(self, action_name: str, context: Dict[str, Any]) -> Dict[str, Any]:
        if action_name == "human_review":
            return self._human_review(context)
        return context

    def on_tool_calls(self, state_name: str, tool_calls: List[Dict[str, Any]], context: Dict[str, Any]) -> Dict[str, Any]:
        """Print agent thinking/content and token usage before tool execution."""
        # Show agent thinking/content if present
        content = context.get("_tool_loop_content")
        if content and content.strip():
            print()
            print(_dim(content.strip()))

        # Show token/cost metrics
        usage = context.get("_tool_loop_usage") or {}
        parts = []
        input_tokens = usage.get("input_tokens")
        output_tokens = usage.get("output_tokens")
        if input_tokens is not None or output_tokens is not None:
            parts.append(f"tokens: {input_tokens or 0}→{output_tokens or 0}")
        cost = context.get("_tool_loop_cost")
        if cost:
            parts.append(f"${cost:.4f}")
        if parts:
            print(_dim(" | ".join(parts)))

        return context

    def on_tool_result(self, state_name: str, tool_result: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """Print tool call result and track modified files."""
        name = tool_result.get("name", "")
        args = tool_result.get("arguments", {})
        is_error = tool_result.get("is_error", False)
        content = tool_result.get("content", "")

        # Print tool call summary
        if name == "bash":
            label = f"bash: {args.get('command', '')}"
        elif name == "read":
            label = f"read: {args.get('path', '')}"
            offset = args.get("offset")
            limit = args.get("limit")
            if offset or limit:
                extras = []
                if offset:
                    extras.append(f"offset={offset}")
                if limit:
                    extras.append(f"limit={limit}")
                label += f" ({', '.join(extras)})"
        elif name == "write":
            n = len(args.get("content", ""))
            label = f"write: {args.get('path', '')} ({n} bytes)"
        elif name == "edit":
            label = f"edit: {args.get('path', '')}"
        else:
            label = f"{name}: {args}"

        status = "✗" if is_error else "✓"
        print(f"  {status} {_bold(label)}")

        # Track files modified
        if not is_error and name in ("write", "edit"):
            path = args.get("path", "")
            if path:
                modified = context.setdefault("files_modified", [])
                if path not in modified:
                    modified.append(path)

        return context

    def _human_review(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Show agent output, ask for follow-up or accept."""
        result = context.get("result", "")
        if result:
            print()
            print(result)

        files = context.get("files_modified", [])
        if files:
            print()
            print(_dim(f"Files modified: {', '.join(files)}"))

        print()
        try:
            response = input("Follow-up (or Enter to finish): ").strip()
        except (EOFError, KeyboardInterrupt):
            response = ""

        if response:
            context["human_approved"] = False
            context["feedback"] = response
        else:
            context["human_approved"] = True
            context["feedback"] = ""

        return context
