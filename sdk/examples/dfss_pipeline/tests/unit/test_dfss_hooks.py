from __future__ import annotations

import inspect
import pytest

from _dfss_test_helpers import load_dfss_module



def _hooks_module():
    return load_dfss_module("hooks.py", "dfss_hooks")


async def _call_on_action(hooks, action_name: str, context: dict):
    result = hooks.on_action(action_name, context)
    if inspect.isawaitable(result):
        return await result
    return result


@pytest.mark.asyncio
async def test_on_action_run_task_sets_result():
    mod = _hooks_module()
    hooks = mod.TaskHooks(max_depth=3, fail_rate=0.0)

    ctx = {
        "task_id": "root-000/0",
        "root_id": "root-000",
        "depth": 0,
        "resource_class": "fast",
        "has_expensive_descendant": False,
    }
    out = await _call_on_action(hooks, "run_task", ctx)
    assert out.get("result") is not None


@pytest.mark.asyncio
async def test_fail_rate_1_raises_transient_error():
    mod = _hooks_module()
    hooks = mod.TaskHooks(max_depth=3, fail_rate=1.0)

    ctx = {
        "task_id": "root-000/0",
        "root_id": "root-000",
        "depth": 0,
        "resource_class": "fast",
        "has_expensive_descendant": False,
    }
    with pytest.raises(RuntimeError):
        await _call_on_action(hooks, "run_task", ctx)


@pytest.mark.asyncio
async def test_hooks_do_not_emit_children():
    mod = _hooks_module()
    hooks = mod.TaskHooks(max_depth=3, fail_rate=0.0)

    ctx = {
        "task_id": "root-001/0",
        "root_id": "root-001",
        "depth": 0,
        "resource_class": "fast",
        "has_expensive_descendant": True,
    }
    out = await _call_on_action(hooks, "run_task", ctx)

    assert "children" not in out or out.get("children") in (None, [])
