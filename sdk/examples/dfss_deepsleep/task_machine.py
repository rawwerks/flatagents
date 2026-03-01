"""
Task runner machine for DFSS Deep Sleep.

Runs a single task via hook action, outputs result + children.
Signals "dfss/ready" on completion so the scheduler wakes.
"""
from __future__ import annotations


def task_config() -> dict:
    return {
        "spec": "flatmachine",
        "spec_version": "1.1.1",
        "data": {
            "name": "dfss-deepsleep-task",
            "context": {
                "task_id": "input.task_id",
                "root_id": "input.root_id",
                "depth": "input.depth",
                "resource_class": "input.resource_class",
                "result": None,
                "children": [],
            },
            "hooks": {
                "file": "./hooks.py",
                "class": "DeepSleepHooks",
            },
            "states": {
                "start": {
                    "type": "initial",
                    "transitions": [{"to": "run_task"}],
                },
                "run_task": {
                    "action": "run_task",
                    "on_error": "error_exit",
                    "transitions": [{"to": "signal_done"}],
                },
                "signal_done": {
                    "action": "signal_ready",
                    "transitions": [{"to": "done"}],
                },
                "done": {
                    "type": "final",
                    "output": {
                        "task_id": "context.task_id",
                        "root_id": "context.root_id",
                        "result": "context.result",
                        "children": "context.children",
                    },
                },
                "error_exit": {
                    "type": "final",
                    "output": {
                        "task_id": "context.task_id",
                        "root_id": "context.root_id",
                        "error": "context.last_error",
                    },
                },
            },
        },
    }
