"""Unit tests for DeepSleepHooks — pure logic, no FlatMachine."""
from __future__ import annotations

import pytest
from _helpers import load_module

hooks_mod = load_module("hooks.py", "deepsleep_hooks")
DeepSleepHooks = hooks_mod.DeepSleepHooks


@pytest.fixture
def hooks():
    return DeepSleepHooks(max_depth=3, fail_rate=0.0, seed=42)


# ── pick_batch ─────────────────────────────────────────────

class TestPickBatch:

    def test_selects_up_to_batch_size(self, hooks):
        candidates = [
            {"task_id": f"r/0.{i}", "root_id": "r", "depth": 1, "resource_class": "fast"}
            for i in range(10)
        ]
        ctx = hooks.on_action("pick_batch", {
            "_candidates": candidates,
            "batch_size": 3,
            "max_active_roots": 2,
            "roots": {},
        })
        assert len(ctx["batch"]) == 3

    def test_empty_candidates_sets_all_done(self, hooks):
        ctx = hooks.on_action("pick_batch", {
            "_candidates": [],
            "batch_size": 4,
            "max_active_roots": 2,
            "roots": {},
        })
        assert ctx["batch"] == []
        assert ctx["all_done"] is True

    def test_respects_max_active_roots(self, hooks):
        candidates = [
            {"task_id": "a/0", "root_id": "a", "depth": 0, "resource_class": "fast"},
            {"task_id": "b/0", "root_id": "b", "depth": 0, "resource_class": "fast"},
            {"task_id": "c/0", "root_id": "c", "depth": 0, "resource_class": "fast"},
        ]
        ctx = hooks.on_action("pick_batch", {
            "_candidates": candidates,
            "batch_size": 10,
            "max_active_roots": 2,
            "roots": {},
        })
        root_ids = {c["root_id"] for c in ctx["batch"]}
        assert len(root_ids) <= 2

    def test_prefers_active_roots(self, hooks):
        candidates = [
            {"task_id": "a/0", "root_id": "a", "depth": 0, "resource_class": "fast"},
            {"task_id": "b/0", "root_id": "b", "depth": 0, "resource_class": "fast"},
        ]
        ctx = hooks.on_action("pick_batch", {
            "_candidates": candidates,
            "batch_size": 1,
            "max_active_roots": 1,
            "roots": {"a": {"admitted": True, "completed": 0, "terminal_failures": 0}},
        })
        assert ctx["batch"][0]["root_id"] == "a"

    def test_prefers_deeper_tasks(self, hooks):
        candidates = [
            {"task_id": "r/0", "root_id": "r", "depth": 0, "resource_class": "fast"},
            {"task_id": "r/0.0", "root_id": "r", "depth": 2, "resource_class": "fast"},
        ]
        ctx = hooks.on_action("pick_batch", {
            "_candidates": candidates,
            "batch_size": 1,
            "max_active_roots": 1,
            "roots": {"r": {"admitted": True, "completed": 0, "terminal_failures": 0}},
        })
        assert ctx["batch"][0]["task_id"] == "r/0.0"


# ── process_results ────────────────────────────────────────

class TestProcessResults:

    def test_counts_completions(self, hooks):
        ctx = hooks.on_action("process_results", {
            "batch_results": [
                {"task_id": "r/0", "root_id": "r", "result": "ok", "children": []},
                {"task_id": "r/1", "root_id": "r", "result": "ok", "children": []},
            ],
            "roots": {"r": {"admitted": True, "completed": 0, "terminal_failures": 0}},
        })
        assert ctx["roots"]["r"]["completed"] == 2

    def test_collects_children(self, hooks):
        ctx = hooks.on_action("process_results", {
            "batch_results": [
                {
                    "task_id": "r/0", "root_id": "r", "result": "ok",
                    "children": [
                        {"task_id": "r/0.0", "root_id": "r", "depth": 1, "resource_class": "fast"},
                    ],
                },
            ],
            "roots": {"r": {"admitted": True, "completed": 0, "terminal_failures": 0}},
        })
        assert len(ctx["_new_children"]) == 1
        assert ctx["_new_children"][0]["task_id"] == "r/0.0"

    def test_counts_errors(self, hooks):
        ctx = hooks.on_action("process_results", {
            "batch_results": [
                {"task_id": "r/0", "root_id": "r", "error": "boom"},
            ],
            "roots": {"r": {"admitted": True, "completed": 0, "terminal_failures": 0}},
        })
        assert ctx["roots"]["r"]["terminal_failures"] == 1

    def test_handles_dict_results(self, hooks):
        """foreach with key returns dict, not list."""
        ctx = hooks.on_action("process_results", {
            "batch_results": {
                0: {"task_id": "r/0", "root_id": "r", "result": "ok", "children": []},
            },
            "roots": {"r": {"admitted": True, "completed": 0, "terminal_failures": 0}},
        })
        assert ctx["roots"]["r"]["completed"] == 1


# ── run_task ───────────────────────────────────────────────

class TestRunTask:

    def test_produces_result(self, hooks):
        ctx = hooks.on_action("run_task", {
            "task_id": "r/0", "root_id": "r", "depth": 0, "resource_class": "fast",
        })
        assert ctx["result"] == "ok:r/0"

    def test_leaf_at_max_depth(self, hooks):
        ctx = hooks.on_action("run_task", {
            "task_id": "r/0", "root_id": "r", "depth": 3, "resource_class": "fast",
        })
        assert ctx["children"] == []

    def test_fail_rate(self):
        hooks = DeepSleepHooks(max_depth=3, fail_rate=1.0, seed=1)
        with pytest.raises(RuntimeError, match="transient failure"):
            hooks.on_action("run_task", {
                "task_id": "r/0", "root_id": "r", "depth": 0, "resource_class": "fast",
            })
