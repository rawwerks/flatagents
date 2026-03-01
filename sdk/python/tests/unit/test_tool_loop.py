"""
Unit tests for ToolLoopAgent (standalone, flatagents layer).

Tests:
- Complete loop: agent calls tool → gets result → responds
- Multi-round: multiple rounds of tool calls before completion
- Guardrails: max_turns, max_tool_calls, max_cost, total_timeout
- Denied/allowed tools
- Error handling: tool exceptions, tool timeout, unknown tools, LLM errors
- Steering injection
- Usage aggregation
- ToolProvider protocol: SimpleToolProvider, direct ToolProvider
- call() argument verification (tools param, messages param)
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from flatagents.tools import ToolResult, ToolProvider, SimpleToolProvider
from flatagents.tool_loop import (
    ToolLoopAgent,
    Tool,
    Guardrails,
    ToolLoopResult,
    AggregateUsage,
    StopReason,
)
from flatagents.baseagent import FinishReason


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

@dataclass
class FakeUsage:
    input_tokens: int = 10
    output_tokens: int = 5
    total_tokens: int = 15
    cost: Optional[Any] = None
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0


@dataclass
class FakeCost:
    input: float = 0.001
    output: float = 0.002
    cache_read: float = 0.0
    cache_write: float = 0.0
    total: float = 0.003


@dataclass
class FakeError:
    error_type: str = "ServerError"
    message: str = "something went wrong"
    status_code: int = 500
    retryable: bool = True


@dataclass
class FakeToolCall:
    id: str
    tool: str
    arguments: Dict[str, Any]
    server: Optional[str] = None


def make_response(
    content="done",
    finish_reason=FinishReason.STOP,
    tool_calls=None,
    error=None,
    usage=None,
    rendered_user_prompt="rendered prompt",
):
    """Build a mock AgentResponse."""
    resp = MagicMock()
    resp.content = content
    resp.finish_reason = finish_reason
    resp.tool_calls = tool_calls
    resp.error = error
    resp.usage = usage or FakeUsage()
    resp.rendered_user_prompt = rendered_user_prompt
    return resp


def make_tool_response(tool_calls_data, content=None):
    """Build a mock AgentResponse with tool calls."""
    tcs = [
        FakeToolCall(id=tc["id"], tool=tc["name"], arguments=tc.get("arguments", {}))
        for tc in tool_calls_data
    ]
    return make_response(
        content=content,
        finish_reason=FinishReason.TOOL_USE,
        tool_calls=tcs,
    )


async def _echo_execute(tool_call_id, args):
    return ToolResult(content=f"result for {args}")


def make_tool(name="test_tool", description="a test tool"):
    return Tool(
        name=name,
        description=description,
        parameters={"type": "object", "properties": {"x": {"type": "string"}}},
        execute=_echo_execute,
    )


# ---------------------------------------------------------------------------
# Tests: Basic Loop
# ---------------------------------------------------------------------------

class TestBasicLoop:
    """Test the fundamental tool loop flow."""

    @pytest.mark.asyncio
    async def test_no_tool_calls_single_turn(self):
        """Agent responds without tool calls → loop completes in 1 turn."""
        agent = AsyncMock()
        agent.call = AsyncMock(return_value=make_response(content="hello"))

        loop = ToolLoopAgent(agent=agent, tools=[make_tool()])
        result = await loop.run(task="say hello")

        assert result.content == "hello"
        assert result.stop_reason == StopReason.COMPLETE
        assert result.turns == 1
        assert result.tool_calls_count == 0

    @pytest.mark.asyncio
    async def test_one_tool_call_then_complete(self):
        """Agent calls a tool, gets result, then completes."""
        agent = AsyncMock()
        agent.call = AsyncMock(side_effect=[
            make_tool_response([{"id": "call_1", "name": "test_tool", "arguments": {"x": "1"}}]),
            make_response(content="done with tools"),
        ])

        loop = ToolLoopAgent(agent=agent, tools=[make_tool()])
        result = await loop.run(task="do work")

        assert result.content == "done with tools"
        assert result.stop_reason == StopReason.COMPLETE
        assert result.turns == 2
        assert result.tool_calls_count == 1

    @pytest.mark.asyncio
    async def test_multi_round_tool_calls(self):
        """Agent calls tools across 3 rounds before completing."""
        agent = AsyncMock()
        agent.call = AsyncMock(side_effect=[
            make_tool_response([{"id": "c1", "name": "test_tool", "arguments": {"x": "1"}}]),
            make_tool_response([{"id": "c2", "name": "test_tool", "arguments": {"x": "2"}}]),
            make_tool_response([{"id": "c3", "name": "test_tool", "arguments": {"x": "3"}}]),
            make_response(content="all done"),
        ])

        loop = ToolLoopAgent(agent=agent, tools=[make_tool()])
        result = await loop.run(task="three rounds")

        assert result.turns == 4
        assert result.tool_calls_count == 3
        assert result.stop_reason == StopReason.COMPLETE

    @pytest.mark.asyncio
    async def test_multiple_tools_in_one_round(self):
        """Agent returns multiple tool calls in a single response."""
        agent = AsyncMock()
        agent.call = AsyncMock(side_effect=[
            make_tool_response([
                {"id": "c1", "name": "test_tool", "arguments": {"x": "a"}},
                {"id": "c2", "name": "test_tool", "arguments": {"x": "b"}},
                {"id": "c3", "name": "test_tool", "arguments": {"x": "c"}},
            ]),
            make_response(content="batch done"),
        ])

        loop = ToolLoopAgent(agent=agent, tools=[make_tool()])
        result = await loop.run(task="batch")

        assert result.tool_calls_count == 3
        assert result.turns == 2

    @pytest.mark.asyncio
    async def test_chain_seeded_with_user_prompt(self):
        """The rendered user prompt is added to chain on first turn."""
        agent = AsyncMock()
        agent.call = AsyncMock(side_effect=[
            make_tool_response(
                [{"id": "c1", "name": "test_tool", "arguments": {}}],
                content="thinking",
            ),
            make_response(content="done"),
        ])

        loop = ToolLoopAgent(agent=agent, tools=[make_tool()])
        result = await loop.run(task="test")

        # Second call should receive messages chain
        second_call_kwargs = agent.call.call_args_list[1]
        messages = second_call_kwargs.kwargs.get("messages") or second_call_kwargs[1].get("messages")
        assert messages is not None
        assert messages[0]["role"] == "user"
        assert messages[0]["content"] == "rendered prompt"

    @pytest.mark.asyncio
    async def test_first_call_passes_input_data(self):
        """First call passes input_data as kwargs for template rendering."""
        agent = AsyncMock()
        agent.call = AsyncMock(return_value=make_response(content="ok"))

        loop = ToolLoopAgent(agent=agent, tools=[make_tool()])
        await loop.run(task="my task", extra="val")

        first_call = agent.call.call_args_list[0]
        assert first_call.kwargs.get("task") == "my task"
        assert first_call.kwargs.get("extra") == "val"

    @pytest.mark.asyncio
    async def test_tools_passed_to_agent_call(self):
        """The tools parameter is passed to every agent.call()."""
        agent = AsyncMock()
        agent.call = AsyncMock(return_value=make_response())

        tool = make_tool()
        loop = ToolLoopAgent(agent=agent, tools=[tool])
        await loop.run(task="test")

        call_kwargs = agent.call.call_args_list[0].kwargs
        tools_arg = call_kwargs.get("tools")
        assert tools_arg is not None
        assert len(tools_arg) == 1
        assert tools_arg[0]["function"]["name"] == "test_tool"


# ---------------------------------------------------------------------------
# Tests: Guardrails
# ---------------------------------------------------------------------------

class TestGuardrails:

    @pytest.mark.asyncio
    async def test_max_turns(self):
        """Loop stops after max_turns LLM calls."""
        agent = AsyncMock()
        # Always return tool calls → never naturally completes
        agent.call = AsyncMock(return_value=make_tool_response(
            [{"id": "c1", "name": "test_tool", "arguments": {}}]
        ))

        loop = ToolLoopAgent(
            agent=agent,
            tools=[make_tool()],
            guardrails=Guardrails(max_turns=3),
        )
        result = await loop.run(task="loop forever")

        assert result.stop_reason == StopReason.MAX_TURNS
        assert result.turns == 3

    @pytest.mark.asyncio
    async def test_max_tool_calls(self):
        """Loop stops when total tool calls exceed limit."""
        call_count = 0

        async def counting_call(**kwargs):
            nonlocal call_count
            call_count += 1
            # Each response has 2 tool calls
            return make_tool_response([
                {"id": f"c{call_count}a", "name": "test_tool", "arguments": {}},
                {"id": f"c{call_count}b", "name": "test_tool", "arguments": {}},
            ])

        agent = AsyncMock()
        agent.call = AsyncMock(side_effect=counting_call)

        loop = ToolLoopAgent(
            agent=agent,
            tools=[make_tool()],
            guardrails=Guardrails(max_tool_calls=3, max_turns=100),
        )
        result = await loop.run(task="many tools")

        assert result.stop_reason == StopReason.MAX_TOOL_CALLS
        # After first round (2 calls), tries second round (2 more would exceed 3)
        assert result.tool_calls_count == 2

    @pytest.mark.asyncio
    async def test_max_cost(self):
        """Loop stops when cost exceeds limit."""
        agent = AsyncMock()
        usage = FakeUsage(cost=FakeCost(total=0.60))
        resp1 = make_tool_response(
            [{"id": "c1", "name": "test_tool", "arguments": {}}],
        )
        resp1.usage = usage
        resp2 = make_tool_response(
            [{"id": "c2", "name": "test_tool", "arguments": {}}],
        )
        resp2.usage = usage
        agent.call = AsyncMock(side_effect=[resp1, resp2])

        loop = ToolLoopAgent(
            agent=agent,
            tools=[make_tool()],
            guardrails=Guardrails(max_cost=1.00),
        )
        result = await loop.run(task="expensive")

        # After turn 1 (0.60) the loop continues, turn 2 (1.20) triggers cost check
        # before executing tools on turn 2
        assert result.stop_reason == StopReason.COST_LIMIT

    @pytest.mark.asyncio
    async def test_total_timeout(self):
        """Loop stops when total time exceeds limit."""
        agent = AsyncMock()

        async def slow_call(**kwargs):
            await asyncio.sleep(0.05)
            return make_tool_response([{"id": "c1", "name": "test_tool", "arguments": {}}])

        agent.call = AsyncMock(side_effect=slow_call)

        loop = ToolLoopAgent(
            agent=agent,
            tools=[make_tool()],
            guardrails=Guardrails(total_timeout=0.01),
        )
        result = await loop.run(task="slow")

        assert result.stop_reason == StopReason.TIMEOUT


# ---------------------------------------------------------------------------
# Tests: Tool Filtering
# ---------------------------------------------------------------------------

class TestToolFiltering:

    @pytest.mark.asyncio
    async def test_denied_tool(self):
        """Denied tools return error result without executing."""
        agent = AsyncMock()
        agent.call = AsyncMock(side_effect=[
            make_tool_response([{"id": "c1", "name": "dangerous", "arguments": {}}]),
            make_response(content="ok"),
        ])

        loop = ToolLoopAgent(
            agent=agent,
            tools=[make_tool("dangerous")],
            guardrails=Guardrails(denied_tools=["dangerous"]),
        )
        result = await loop.run(task="test")

        assert result.stop_reason == StopReason.COMPLETE
        # The tool result message should say not allowed
        tool_msg = [m for m in result.messages if m.get("role") == "tool"]
        assert len(tool_msg) == 1
        assert "not allowed" in tool_msg[0]["content"]

    @pytest.mark.asyncio
    async def test_allowed_tools_blocks_unlisted(self):
        """Only tools in allowed_tools can execute."""
        agent = AsyncMock()
        agent.call = AsyncMock(side_effect=[
            make_tool_response([{"id": "c1", "name": "bad_tool", "arguments": {}}]),
            make_response(content="ok"),
        ])

        loop = ToolLoopAgent(
            agent=agent,
            tools=[make_tool("bad_tool"), make_tool("good_tool")],
            guardrails=Guardrails(allowed_tools=["good_tool"]),
        )
        result = await loop.run(task="test")

        tool_msg = [m for m in result.messages if m.get("role") == "tool"]
        assert "not allowed" in tool_msg[0]["content"]


# ---------------------------------------------------------------------------
# Tests: Error Handling
# ---------------------------------------------------------------------------

class TestErrorHandling:

    @pytest.mark.asyncio
    async def test_unknown_tool(self):
        """Unknown tool returns error result."""
        agent = AsyncMock()
        agent.call = AsyncMock(side_effect=[
            make_tool_response([{"id": "c1", "name": "nonexistent", "arguments": {}}]),
            make_response(content="ok"),
        ])

        loop = ToolLoopAgent(agent=agent, tools=[make_tool("other_tool")])
        result = await loop.run(task="test")

        tool_msg = [m for m in result.messages if m.get("role") == "tool"]
        assert "Unknown tool" in tool_msg[0]["content"]

    @pytest.mark.asyncio
    async def test_tool_exception(self):
        """Tool that raises exception returns error result."""
        async def failing_tool(tool_call_id, args):
            raise ValueError("boom")

        tool = Tool(
            name="fail",
            description="fails",
            parameters={"type": "object"},
            execute=failing_tool,
        )
        agent = AsyncMock()
        agent.call = AsyncMock(side_effect=[
            make_tool_response([{"id": "c1", "name": "fail", "arguments": {}}]),
            make_response(content="recovered"),
        ])

        loop = ToolLoopAgent(agent=agent, tools=[tool])
        result = await loop.run(task="test")

        assert result.stop_reason == StopReason.COMPLETE
        tool_msg = [m for m in result.messages if m.get("role") == "tool"]
        assert "boom" in tool_msg[0]["content"]

    @pytest.mark.asyncio
    async def test_tool_timeout(self):
        """Tool that takes too long returns timeout error."""
        async def slow_tool(tool_call_id, args):
            await asyncio.sleep(10)
            return ToolResult(content="done")

        tool = Tool(
            name="slow",
            description="slow",
            parameters={"type": "object"},
            execute=slow_tool,
        )
        agent = AsyncMock()
        agent.call = AsyncMock(side_effect=[
            make_tool_response([{"id": "c1", "name": "slow", "arguments": {}}]),
            make_response(content="ok"),
        ])

        loop = ToolLoopAgent(
            agent=agent,
            tools=[tool],
            guardrails=Guardrails(tool_timeout=0.01),
        )
        result = await loop.run(task="test")

        tool_msg = [m for m in result.messages if m.get("role") == "tool"]
        assert "timed out" in tool_msg[0]["content"]

    @pytest.mark.asyncio
    async def test_llm_error(self):
        """LLM error stops the loop with ERROR reason."""
        agent = AsyncMock()
        agent.call = AsyncMock(return_value=make_response(
            content=None,
            finish_reason=FinishReason.ERROR,
            error=FakeError(),
        ))

        loop = ToolLoopAgent(agent=agent, tools=[make_tool()])
        result = await loop.run(task="test")

        assert result.stop_reason == StopReason.ERROR
        assert result.error is not None


# ---------------------------------------------------------------------------
# Tests: ToolProvider Protocol
# ---------------------------------------------------------------------------

class TestToolProvider:

    @pytest.mark.asyncio
    async def test_simple_tool_provider(self):
        """SimpleToolProvider wraps Tool objects correctly."""
        tool = make_tool("greet")
        provider = SimpleToolProvider([tool])

        defs = provider.get_tool_definitions()
        assert len(defs) == 1
        assert defs[0]["function"]["name"] == "greet"

        result = await provider.execute_tool("greet", "id1", {"x": "hello"})
        assert "hello" in result.content

    @pytest.mark.asyncio
    async def test_simple_provider_unknown_tool(self):
        """SimpleToolProvider returns error for unknown tools."""
        provider = SimpleToolProvider([make_tool("known")])
        result = await provider.execute_tool("unknown", "id1", {})
        assert result.is_error
        assert "Unknown tool" in result.content

    @pytest.mark.asyncio
    async def test_tool_loop_agent_with_provider(self):
        """ToolLoopAgent works with explicit ToolProvider."""

        class CustomProvider:
            def get_tool_definitions(self):
                return [{"type": "function", "function": {"name": "custom", "description": "custom tool", "parameters": {}}}]

            async def execute_tool(self, name, tool_call_id, arguments):
                return ToolResult(content=f"custom result: {name}")

        agent = AsyncMock()
        agent.call = AsyncMock(side_effect=[
            make_tool_response([{"id": "c1", "name": "custom", "arguments": {}}]),
            make_response(content="done"),
        ])

        loop = ToolLoopAgent(agent=agent, tool_provider=CustomProvider())
        result = await loop.run(task="test")

        assert result.stop_reason == StopReason.COMPLETE
        assert result.tool_calls_count == 1

    def test_must_provide_tools_or_provider(self):
        """ToolLoopAgent raises if neither tools nor tool_provider given."""
        agent = AsyncMock()
        with pytest.raises(ValueError, match="Either 'tools' or 'tool_provider'"):
            ToolLoopAgent(agent=agent)


# ---------------------------------------------------------------------------
# Tests: Usage Aggregation
# ---------------------------------------------------------------------------

class TestUsageAggregation:

    @pytest.mark.asyncio
    async def test_usage_accumulated_across_turns(self):
        """Usage metrics accumulate across multiple turns."""
        agent = AsyncMock()
        usage = FakeUsage(input_tokens=100, output_tokens=50, total_tokens=150, cost=FakeCost(total=0.01))
        resp1 = make_tool_response([{"id": "c1", "name": "test_tool", "arguments": {}}])
        resp1.usage = usage
        resp2 = make_response(content="done")
        resp2.usage = usage
        agent.call = AsyncMock(side_effect=[resp1, resp2])

        loop = ToolLoopAgent(agent=agent, tools=[make_tool()])
        result = await loop.run(task="test")

        assert result.usage.api_calls == 2
        assert result.usage.input_tokens == 200
        assert result.usage.output_tokens == 100
        assert result.usage.total_cost == pytest.approx(0.02)


# ---------------------------------------------------------------------------
# Tests: Steering
# ---------------------------------------------------------------------------

class TestSteering:

    @pytest.mark.asyncio
    async def test_steering_messages_injected(self):
        """Steering provider injects messages between rounds."""
        async def steering_fn():
            return [{"role": "user", "content": "keep going"}]

        agent = AsyncMock()
        agent.call = AsyncMock(side_effect=[
            make_tool_response([{"id": "c1", "name": "test_tool", "arguments": {}}]),
            make_response(content="done"),
        ])

        loop = ToolLoopAgent(agent=agent, tools=[make_tool()], steering=steering_fn)
        result = await loop.run(task="test")

        # Check chain contains the steering message
        steering_msgs = [m for m in result.messages if m.get("content") == "keep going"]
        assert len(steering_msgs) == 1
