"""
Unit tests for ToolLoopAgent.

Tests the tool-call loop without real LLM calls by mocking FlatAgent.
"""

import asyncio
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock

import pytest

from flatagents.baseagent import FinishReason, UsageInfo, CostInfo, ErrorInfo, ToolCall, AgentResponse
from flatagents.tool_loop import (
    ToolLoopAgent,
    Tool,
    ToolResult,
    Guardrails,
    ToolLoopResult,
    AggregateUsage,
    StopReason,
    _tools_for_llm,
    _build_assistant_message,
    _build_tool_result_message,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_response(
    content: str = "",
    tool_calls: Optional[List[ToolCall]] = None,
    finish_reason: FinishReason = FinishReason.STOP,
    error: Optional[ErrorInfo] = None,
    usage: Optional[UsageInfo] = None,
    rendered_user_prompt: Optional[str] = None,
) -> AgentResponse:
    """Build a mock AgentResponse."""
    return AgentResponse(
        content=content,
        tool_calls=tool_calls,
        finish_reason=finish_reason,
        error=error,
        usage=usage,
        rendered_user_prompt=rendered_user_prompt,
    )


def make_tool_call(id: str, name: str, arguments: dict) -> ToolCall:
    """Build a ToolCall."""
    return ToolCall(id=id, server="", tool=name, arguments=arguments)


async def echo_execute(tool_call_id: str, args: dict) -> ToolResult:
    """Simple tool that echoes its arguments."""
    return ToolResult(content=f"echo: {args}")


async def failing_execute(tool_call_id: str, args: dict) -> ToolResult:
    """Tool that always raises."""
    raise RuntimeError("tool exploded")


async def slow_execute(tool_call_id: str, args: dict) -> ToolResult:
    """Tool that takes too long."""
    await asyncio.sleep(100)
    return ToolResult(content="done")


def make_echo_tool(name: str = "echo") -> Tool:
    return Tool(
        name=name,
        description="Echoes arguments",
        parameters={"type": "object", "properties": {"text": {"type": "string"}}},
        execute=echo_execute,
    )


def make_failing_tool(name: str = "fail") -> Tool:
    return Tool(
        name=name,
        description="Always fails",
        parameters={"type": "object", "properties": {}},
        execute=failing_execute,
    )


def make_slow_tool(name: str = "slow") -> Tool:
    return Tool(
        name=name,
        description="Takes forever",
        parameters={"type": "object", "properties": {}},
        execute=slow_execute,
    )


def make_mock_agent(responses: List[AgentResponse]) -> AsyncMock:
    """Create a mock FlatAgent that returns responses in sequence."""
    agent = AsyncMock()
    agent.call = AsyncMock(side_effect=responses)
    return agent


# ---------------------------------------------------------------------------
# Unit tests: helpers
# ---------------------------------------------------------------------------

class TestToolConversion:
    def test_tools_for_llm_format(self):
        tools = [make_echo_tool("read"), make_echo_tool("bash")]
        result = _tools_for_llm(tools)
        assert len(result) == 2
        assert result[0]["type"] == "function"
        assert result[0]["function"]["name"] == "read"
        assert result[1]["function"]["name"] == "bash"

    def test_tools_for_llm_empty(self):
        assert _tools_for_llm([]) == []


class TestBuildMessages:
    def test_assistant_message_no_tools(self):
        resp = make_response(content="Hello")
        msg = _build_assistant_message(resp)
        assert msg["role"] == "assistant"
        assert msg["content"] == "Hello"
        assert "tool_calls" not in msg

    def test_assistant_message_with_tools(self):
        tc = make_tool_call("c1", "echo", {"text": "hi"})
        resp = make_response(content="", tool_calls=[tc])
        msg = _build_assistant_message(resp)
        assert msg["role"] == "assistant"
        assert len(msg["tool_calls"]) == 1
        assert msg["tool_calls"][0]["id"] == "c1"
        assert msg["tool_calls"][0]["function"]["name"] == "echo"

    def test_tool_result_message(self):
        msg = _build_tool_result_message("c1", "file contents")
        assert msg == {"role": "tool", "tool_call_id": "c1", "content": "file contents"}


# ---------------------------------------------------------------------------
# Integration tests: full loop
# ---------------------------------------------------------------------------

class TestToolLoopComplete:
    """Tests where the model stops without calling tools."""

    async def test_no_tool_calls(self):
        """Model responds directly, no tools needed."""
        agent = make_mock_agent([make_response(content="The answer is 42")])
        loop = ToolLoopAgent(agent, tools=[make_echo_tool()])

        result = await loop.run(task="What is 42?")

        assert result.stop_reason == StopReason.COMPLETE
        assert result.content == "The answer is 42"
        assert result.tool_calls_count == 0
        assert result.turns == 1
        assert len(result.messages) == 1  # just the assistant message
        assert result.messages[0]["role"] == "assistant"

    async def test_one_tool_call_then_stop(self):
        """Model calls a tool, gets result, then responds."""
        tc = make_tool_call("c1", "echo", {"text": "hello"})
        responses = [
            make_response(content="", tool_calls=[tc], finish_reason=FinishReason.TOOL_USE),
            make_response(content="Done: echo said hello"),
        ]
        agent = make_mock_agent(responses)
        loop = ToolLoopAgent(agent, tools=[make_echo_tool()])

        result = await loop.run(task="echo hello")

        assert result.stop_reason == StopReason.COMPLETE
        assert result.content == "Done: echo said hello"
        assert result.tool_calls_count == 1
        assert result.turns == 2
        # Chain: assistant(tool_call) → tool_result → assistant(final)
        assert len(result.messages) == 3
        assert result.messages[0]["role"] == "assistant"
        assert result.messages[1]["role"] == "tool"
        assert result.messages[2]["role"] == "assistant"

    async def test_multiple_tool_calls_single_turn(self):
        """Model calls multiple tools in one response."""
        tc1 = make_tool_call("c1", "echo", {"text": "a"})
        tc2 = make_tool_call("c2", "echo", {"text": "b"})
        responses = [
            make_response(content="", tool_calls=[tc1, tc2], finish_reason=FinishReason.TOOL_USE),
            make_response(content="Both done"),
        ]
        agent = make_mock_agent(responses)
        loop = ToolLoopAgent(agent, tools=[make_echo_tool()])

        result = await loop.run(task="echo both")

        assert result.stop_reason == StopReason.COMPLETE
        assert result.tool_calls_count == 2
        assert result.turns == 2
        # Chain: assistant(2 tool_calls) → tool_result → tool_result → assistant(final)
        assert len(result.messages) == 4

    async def test_multi_round_tool_loop(self):
        """Model calls tools across multiple rounds."""
        tc1 = make_tool_call("c1", "echo", {"text": "round1"})
        tc2 = make_tool_call("c2", "echo", {"text": "round2"})
        responses = [
            make_response(content="", tool_calls=[tc1], finish_reason=FinishReason.TOOL_USE),
            make_response(content="", tool_calls=[tc2], finish_reason=FinishReason.TOOL_USE),
            make_response(content="All done"),
        ]
        agent = make_mock_agent(responses)
        loop = ToolLoopAgent(agent, tools=[make_echo_tool()])

        result = await loop.run(task="do two rounds")

        assert result.stop_reason == StopReason.COMPLETE
        assert result.tool_calls_count == 2
        assert result.turns == 3


class TestToolLoopGuardrails:
    """Tests for guardrail enforcement."""

    async def test_max_turns(self):
        """Loop stops at max_turns."""
        tc = make_tool_call("c1", "echo", {"text": "loop"})
        # Agent always returns tool calls — should be stopped by guardrail
        responses = [
            make_response(content="", tool_calls=[tc], finish_reason=FinishReason.TOOL_USE)
            for _ in range(100)
        ]
        agent = make_mock_agent(responses)
        loop = ToolLoopAgent(
            agent, tools=[make_echo_tool()],
            guardrails=Guardrails(max_turns=3),
        )

        result = await loop.run(task="loop forever")

        assert result.stop_reason == StopReason.MAX_TURNS
        assert result.turns == 3

    async def test_max_tool_calls(self):
        """Loop stops when total tool calls would exceed limit."""
        tc1 = make_tool_call("c1", "echo", {"text": "a"})
        tc2 = make_tool_call("c2", "echo", {"text": "b"})
        # First response has 2 tool calls, second has 2 — limit is 3
        responses = [
            make_response(content="", tool_calls=[tc1, tc2], finish_reason=FinishReason.TOOL_USE),
            make_response(content="", tool_calls=[tc1, tc2], finish_reason=FinishReason.TOOL_USE),
            make_response(content="done"),
        ]
        agent = make_mock_agent(responses)
        loop = ToolLoopAgent(
            agent, tools=[make_echo_tool()],
            guardrails=Guardrails(max_tool_calls=3),
        )

        result = await loop.run(task="lots of tools")

        # First round: 2 tool calls executed (total=2)
        # Second round: would add 2 more (total=4 > limit 3), so stops
        assert result.stop_reason == StopReason.MAX_TOOL_CALLS
        assert result.tool_calls_count == 2

    async def test_total_timeout(self):
        """Loop stops on total timeout."""
        tc = make_tool_call("c1", "echo", {"text": "x"})
        responses = [
            make_response(content="", tool_calls=[tc], finish_reason=FinishReason.TOOL_USE)
            for _ in range(100)
        ]
        agent = make_mock_agent(responses)
        loop = ToolLoopAgent(
            agent, tools=[make_echo_tool()],
            guardrails=Guardrails(total_timeout=0.0),  # immediate timeout
        )

        result = await loop.run(task="timeout")

        assert result.stop_reason == StopReason.TIMEOUT

    async def test_denied_tool(self):
        """Denied tool returns error message to LLM."""
        tc = make_tool_call("c1", "dangerous", {"cmd": "rm -rf /"})
        responses = [
            make_response(content="", tool_calls=[tc], finish_reason=FinishReason.TOOL_USE),
            make_response(content="OK, won't do that"),
        ]
        agent = make_mock_agent(responses)
        dangerous_tool = Tool(
            name="dangerous", description="Bad tool",
            parameters={"type": "object", "properties": {}},
            execute=echo_execute,
        )
        loop = ToolLoopAgent(
            agent, tools=[dangerous_tool],
            guardrails=Guardrails(denied_tools=["dangerous"]),
        )

        result = await loop.run(task="be bad")

        assert result.stop_reason == StopReason.COMPLETE
        # Tool result should contain the denial message
        tool_msg = result.messages[1]
        assert tool_msg["role"] == "tool"
        assert "not allowed" in tool_msg["content"]

    async def test_allowed_tools_whitelist(self):
        """Only allowed tools can execute."""
        tc = make_tool_call("c1", "echo", {"text": "hi"})
        responses = [
            make_response(content="", tool_calls=[tc], finish_reason=FinishReason.TOOL_USE),
            make_response(content="done"),
        ]
        agent = make_mock_agent(responses)
        loop = ToolLoopAgent(
            agent, tools=[make_echo_tool()],
            guardrails=Guardrails(allowed_tools=["read"]),  # echo not in whitelist
        )

        result = await loop.run(task="echo")

        tool_msg = result.messages[1]
        assert "not allowed" in tool_msg["content"]


class TestToolLoopErrors:
    """Tests for error handling."""

    async def test_tool_execution_error(self):
        """Tool raises exception — error returned to LLM, loop continues."""
        tc = make_tool_call("c1", "fail", {})
        responses = [
            make_response(content="", tool_calls=[tc], finish_reason=FinishReason.TOOL_USE),
            make_response(content="I see the tool failed"),
        ]
        agent = make_mock_agent(responses)
        loop = ToolLoopAgent(agent, tools=[make_failing_tool()])

        result = await loop.run(task="try failing")

        assert result.stop_reason == StopReason.COMPLETE
        assert result.content == "I see the tool failed"
        tool_msg = result.messages[1]
        assert "Error" in tool_msg["content"]
        assert "exploded" in tool_msg["content"]

    async def test_tool_timeout(self):
        """Tool exceeds timeout — error returned to LLM."""
        tc = make_tool_call("c1", "slow", {})
        responses = [
            make_response(content="", tool_calls=[tc], finish_reason=FinishReason.TOOL_USE),
            make_response(content="Tool was too slow"),
        ]
        agent = make_mock_agent(responses)
        loop = ToolLoopAgent(
            agent, tools=[make_slow_tool()],
            guardrails=Guardrails(tool_timeout=0.01),
        )

        result = await loop.run(task="be slow")

        assert result.stop_reason == StopReason.COMPLETE
        tool_msg = result.messages[1]
        assert "timed out" in tool_msg["content"]

    async def test_unknown_tool(self):
        """LLM calls a tool that doesn't exist."""
        tc = make_tool_call("c1", "nonexistent", {})
        responses = [
            make_response(content="", tool_calls=[tc], finish_reason=FinishReason.TOOL_USE),
            make_response(content="OK"),
        ]
        agent = make_mock_agent(responses)
        loop = ToolLoopAgent(agent, tools=[make_echo_tool()])

        result = await loop.run(task="call unknown")

        tool_msg = result.messages[1]
        assert "Unknown tool" in tool_msg["content"]

    async def test_llm_error_response(self):
        """LLM returns an error — loop stops."""
        error = ErrorInfo(
            error_type="RateLimitError",
            message="Too many requests",
            status_code=429,
            retryable=True,
        )
        responses = [make_response(error=error, finish_reason=FinishReason.ERROR)]
        agent = make_mock_agent(responses)
        loop = ToolLoopAgent(agent, tools=[make_echo_tool()])

        result = await loop.run(task="error")

        assert result.stop_reason == StopReason.ERROR
        assert result.error == "Too many requests"

    async def test_length_finish_reason(self):
        """LLM hits max tokens — loop returns an error stop reason."""
        responses = [make_response(content="partial...", finish_reason=FinishReason.LENGTH)]
        agent = make_mock_agent(responses)
        loop = ToolLoopAgent(agent, tools=[make_echo_tool()])

        result = await loop.run(task="long output")

        assert result.stop_reason == StopReason.ERROR
        assert "length" in (result.error or "").lower()
        assert result.content == "partial..."

    async def test_aborted_finish_reason(self):
        """Agent aborted finish reason maps to ABORTED."""
        responses = [make_response(content="partial", finish_reason=FinishReason.ABORTED)]
        agent = make_mock_agent(responses)
        loop = ToolLoopAgent(agent, tools=[make_echo_tool()])

        result = await loop.run(task="abort")

        assert result.stop_reason == StopReason.ABORTED


class TestToolLoopSteering:
    """Tests for steering message injection."""

    async def test_steering_injects_message(self):
        """Steering callback injects a user message between rounds."""
        steering_called = False

        async def steering():
            nonlocal steering_called
            if not steering_called:
                steering_called = True
                return [{"role": "user", "content": "also check tests/"}]
            return []

        tc = make_tool_call("c1", "echo", {"text": "src"})
        responses = [
            make_response(content="", tool_calls=[tc], finish_reason=FinishReason.TOOL_USE),
            make_response(content="Checked both"),
        ]
        agent = make_mock_agent(responses)
        loop = ToolLoopAgent(agent, tools=[make_echo_tool()], steering=steering)

        result = await loop.run(task="check files")

        assert result.stop_reason == StopReason.COMPLETE
        # Chain: assistant(tool) → tool_result → user(steering) → assistant(final)
        assert len(result.messages) == 4
        assert result.messages[2]["role"] == "user"
        assert "tests/" in result.messages[2]["content"]

    async def test_no_steering(self):
        """Loop works fine without steering."""
        tc = make_tool_call("c1", "echo", {"text": "hi"})
        responses = [
            make_response(content="", tool_calls=[tc], finish_reason=FinishReason.TOOL_USE),
            make_response(content="done"),
        ]
        agent = make_mock_agent(responses)
        loop = ToolLoopAgent(agent, tools=[make_echo_tool()])

        result = await loop.run(task="no steering")

        assert result.stop_reason == StopReason.COMPLETE
        assert result.turns == 2

    async def test_steering_exception_returns_error(self):
        """Steering callback errors are returned as structured ERROR stop."""
        async def steering():
            raise RuntimeError("queue offline")

        tc = make_tool_call("c1", "echo", {"text": "x"})
        agent = make_mock_agent([
            make_response(content="", tool_calls=[tc], finish_reason=FinishReason.TOOL_USE),
            make_response(content="done"),
        ])
        loop = ToolLoopAgent(agent, tools=[make_echo_tool()], steering=steering)

        result = await loop.run(task="x")

        assert result.stop_reason == StopReason.ERROR
        assert "queue offline" in (result.error or "")

    async def test_steering_cancelled_returns_aborted(self):
        """Steering callback cancellation maps to ABORTED stop reason."""
        async def steering():
            raise asyncio.CancelledError()

        tc = make_tool_call("c1", "echo", {"text": "x"})
        agent = make_mock_agent([
            make_response(content="", tool_calls=[tc], finish_reason=FinishReason.TOOL_USE),
            make_response(content="done"),
        ])
        loop = ToolLoopAgent(agent, tools=[make_echo_tool()], steering=steering)

        result = await loop.run(task="x")

        assert result.stop_reason == StopReason.ABORTED


class TestToolLoopUsage:
    """Tests for usage aggregation."""

    async def test_usage_accumulated(self):
        """Usage is summed across turns."""
        usage1 = UsageInfo(input_tokens=100, output_tokens=50, total_tokens=150,
                           cost=CostInfo(total=0.01))
        usage2 = UsageInfo(input_tokens=200, output_tokens=80, total_tokens=280,
                           cost=CostInfo(total=0.02))
        tc = make_tool_call("c1", "echo", {"text": "x"})
        responses = [
            make_response(content="", tool_calls=[tc], finish_reason=FinishReason.TOOL_USE, usage=usage1),
            make_response(content="done", usage=usage2),
        ]
        agent = make_mock_agent(responses)
        loop = ToolLoopAgent(agent, tools=[make_echo_tool()])

        result = await loop.run(task="track usage")

        assert result.usage.api_calls == 2
        assert result.usage.input_tokens == 300
        assert result.usage.output_tokens == 130
        assert result.usage.total_tokens == 430
        assert abs(result.usage.total_cost - 0.03) < 0.001

    async def test_cost_limit(self):
        """Loop stops when cost limit is reached."""
        usage = UsageInfo(input_tokens=100, output_tokens=50, total_tokens=150,
                          cost=CostInfo(total=0.10))
        tc = make_tool_call("c1", "echo", {"text": "x"})
        responses = [
            make_response(content="", tool_calls=[tc], finish_reason=FinishReason.TOOL_USE, usage=usage),
            make_response(content="", tool_calls=[tc], finish_reason=FinishReason.TOOL_USE, usage=usage),
            make_response(content="done"),
        ]
        agent = make_mock_agent(responses)
        loop = ToolLoopAgent(
            agent, tools=[make_echo_tool()],
            guardrails=Guardrails(max_cost=0.15),
        )

        result = await loop.run(task="expensive")

        # After first turn: cost=0.10, second turn: cost=0.20 > 0.15
        assert result.stop_reason == StopReason.COST_LIMIT
        assert result.turns == 2
        # Should stop before executing second round's tool batch
        assert result.tool_calls_count == 1


class TestToolLoopAgentCallArgs:
    """Tests that verify ToolLoopAgent passes correct args to FlatAgent.call()."""

    async def test_first_call_gets_input_data(self):
        """First LLM call gets input_data kwargs."""
        agent = make_mock_agent([make_response(content="ok")])
        tools = [make_echo_tool()]
        loop = ToolLoopAgent(agent, tools=tools)

        await loop.run(task="hello", context="world")

        call_kwargs = agent.call.call_args_list[0]
        assert call_kwargs.kwargs["task"] == "hello"
        assert call_kwargs.kwargs["context"] == "world"
        assert call_kwargs.kwargs["tools"] is not None

    async def test_subsequent_calls_get_chain(self):
        """Second LLM call gets the message chain with tool results."""
        tc = make_tool_call("c1", "echo", {"text": "x"})

        # Capture chain snapshots at each call
        chain_snapshots = []

        async def capture_call(**kwargs):
            msgs = kwargs.get("messages")
            if msgs is not None:
                chain_snapshots.append(list(msgs))  # snapshot
            return responses.pop(0)

        responses = [
            make_response(
                content="",
                tool_calls=[tc],
                finish_reason=FinishReason.TOOL_USE,
                rendered_user_prompt="task: test",
            ),
            make_response(content="done"),
        ]
        agent = AsyncMock()
        agent.call = AsyncMock(side_effect=capture_call)
        loop = ToolLoopAgent(agent, tools=[make_echo_tool()])

        await loop.run(task="test")

        # First call has messages=None (or empty), second has the chain
        assert len(chain_snapshots) == 1  # only second call has messages
        second_chain = chain_snapshots[0]
        assert len(second_chain) == 3
        assert second_chain[0]["role"] == "user"
        assert second_chain[1]["role"] == "assistant"
        assert second_chain[2]["role"] == "tool"

    async def test_tools_passed_to_every_call(self):
        """Tools are passed to FlatAgent.call() on every turn."""
        tc = make_tool_call("c1", "echo", {"text": "x"})
        responses = [
            make_response(content="", tool_calls=[tc], finish_reason=FinishReason.TOOL_USE),
            make_response(content="done"),
        ]
        agent = make_mock_agent(responses)
        tools = [make_echo_tool()]
        loop = ToolLoopAgent(agent, tools=tools)

        await loop.run(task="test")

        for call_args in agent.call.call_args_list:
            assert call_args.kwargs["tools"] is not None
            assert len(call_args.kwargs["tools"]) == 1
