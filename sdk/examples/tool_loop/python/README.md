# ToolLoopAgent Demo


A simple example demonstrating the `ToolLoopAgent` from the `flatagents` library. The agent answers user questions by calling tools, then summarises the results in natural language.

## Tools

| Tool | Description | Implementation |
|------|-------------|----------------|
| `get_weather` | Current weather for a city | Canned data (no API key needed) |
| `get_time` | Current time in a timezone | Real time via Python `datetime` stdlib |

## How It Works

1. A `FlatAgent` is loaded from `config/agent.yml` (system + user prompt, model profile).
2. Two `Tool` objects are defined in `tools.py` with name, description, JSON Schema parameters, and an async `execute` function.
3. `ToolLoopAgent` wraps the agent with the tools and guardrails, then runs the LLM tool-call loop:
   - LLM decides which tool(s) to call
   - Tools execute and return results
   - LLM sees results and either calls more tools or responds
4. The loop stops when the LLM responds without tool calls, or a guardrail fires.

## Prerequisites

1. **Python 3.10+** and **`uv`** package manager.
2. **LLM API Key**: Set `CEREBRAS_API_KEY` (default profile) or `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` and adjust `config/profiles.yml`.

## Quick Start

```bash
export CEREBRAS_API_KEY="your-key-here"

chmod +x run.sh
./run.sh --local
```

## Custom Questions

```bash
# Via run.sh
./run.sh --local -- "What time is it in London?"

# Or directly
.venv/bin/python -m flatagent_tool_loop.main "What's the weather in Paris and the time in Europe/Paris?"
```

## Supported Values

**Cities** (for `get_weather`): Tokyo, New York, London, San Francisco, Paris, Sydney

**Timezones** (for `get_time`): UTC, US/Eastern, US/Central, US/Mountain, US/Pacific, Europe/London, Europe/Paris, Europe/Berlin, Asia/Tokyo, Asia/Shanghai, Australia/Sydney
