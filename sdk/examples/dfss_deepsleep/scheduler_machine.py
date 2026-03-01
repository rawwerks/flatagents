"""
DFSS Deep Sleep — scheduler as a FlatMachine with checkpoint-and-exit.

The scheduler is itself a machine. Between batches it checkpoints and exits.
Zero processes while idle. Signals wake it when work is ready.

Flow:
  wait_for "dfss/ready"
    → score_and_select (action: pick batch up to available slots)
    → dispatch_batch (foreach: batch, machine: task_runner)
    → process_results (action: push children, send "dfss/ready" signal)
    → loop back to wait_for (or done)
"""
from __future__ import annotations


def scheduler_config() -> dict:
    return {
        "spec": "flatmachine",
        "spec_version": "1.1.1",
        "data": {
            "name": "dfss-deepsleep-scheduler",
            "context": {
                "pool_name": "input.pool_name",
                "max_active_roots": "input.max_active_roots",
                "batch_size": "input.batch_size",
                "roots": {},           # root_id -> {admitted, completed, terminal_failures}
                "batch": [],           # selected tasks for this round
                "all_done": False,
            },
            "machines": {
                "task_runner": "./task_machine.yml",
            },
            "hooks": {
                "file": "./hooks.py",
                "class": "DeepSleepHooks",
            },
            "states": {
                "wait_for_work": {
                    "type": "initial",
                    "wait_for": "dfss/ready",
                    "timeout": 0,
                    "transitions": [
                        {"to": "score_and_select"},
                    ],
                },
                "score_and_select": {
                    "action": "pick_batch",
                    "transitions": [
                        {
                            "condition": "context.batch",
                            "to": "dispatch_batch",
                        },
                        {
                            "condition": "context.all_done",
                            "to": "done",
                        },
                        {"to": "wait_for_work"},
                    ],
                },
                "dispatch_batch": {
                    "foreach": "context.batch",
                    "as": "task",
                    "machine": "task_runner",
                    "input": {
                        "task_id": "{{ task.task_id }}",
                        "root_id": "{{ task.root_id }}",
                        "depth": "{{ task.depth }}",
                        "resource_class": "{{ task.resource_class }}",
                    },
                    "mode": "settled",
                    "output_to_context": {
                        "batch_results": "output",
                    },
                    "on_error": "process_results",
                    "transitions": [
                        {"to": "process_results"},
                    ],
                },
                "process_results": {
                    "action": "process_results",
                    "transitions": [
                        {
                            "condition": "context.all_done",
                            "to": "done",
                        },
                        {"to": "wait_for_work"},
                    ],
                },
                "done": {
                    "type": "final",
                    "output": {
                        "roots": "context.roots",
                    },
                },
            },
        },
    }
