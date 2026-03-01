"""
ToolProvider protocol and utilities for FlatAgents tool use.

Shared by both ToolLoopAgent (standalone) and FlatMachine (orchestrated).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Protocol, Union


@dataclass
class ToolResult:
    """Result from executing a tool."""
    content: str
    is_error: bool = False


class ToolProvider(Protocol):
    """
    Provides tool definitions and execution.

    Used by both ToolLoopAgent (standalone) and FlatMachine (orchestrated).
    """

    async def execute_tool(
        self,
        name: str,
        tool_call_id: str,
        arguments: Dict[str, Any],
    ) -> ToolResult:
        """Execute a tool and return its result."""
        ...

    def get_tool_definitions(self) -> List[Dict[str, Any]]:
        """
        Return tool definitions in OpenAI function-calling format.

        Optional — if the agent YAML already has ``tools:`` defined,
        this method doesn't need to return anything.  If it does,
        its definitions are merged with (and override) the YAML ones.
        """
        ...


class SimpleToolProvider:
    """Build a ToolProvider from individual Tool objects."""

    def __init__(self, tools: List["Tool"]):
        self._tools: Dict[str, "Tool"] = {t.name: t for t in tools}

    def get_tool_definitions(self) -> List[Dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.parameters,
                },
            }
            for t in self._tools.values()
        ]

    async def execute_tool(
        self, name: str, tool_call_id: str, arguments: Dict[str, Any]
    ) -> ToolResult:
        tool = self._tools.get(name)
        if tool is None:
            return ToolResult(content=f"Unknown tool: {name}", is_error=True)
        return await tool.execute(tool_call_id, arguments)


# Re-export Tool here so standalone users can do:
#   from flatagents.tools import Tool, ToolResult, ToolProvider
# Tool is defined in tool_loop.py but imported lazily to avoid circular imports.

__all__ = [
    "ToolResult",
    "ToolProvider",
    "SimpleToolProvider",
]
