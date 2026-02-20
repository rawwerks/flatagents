from __future__ import annotations

from _dfss_test_helpers import load_dfss_module



def _scheduler_module():
    return load_dfss_module("scheduler.py", "dfss_scheduler")



def test_score_prefers_slow_and_predecessor_drill_tasks():
    mod = _scheduler_module()

    root = mod.RootState(root_id="root-001", admitted=True, pending=5)
    cheap_item = {
        "task_id": "root-001/0",
        "root_id": "root-001",
        "depth": 0,
        "resource_class": "fast",
        "has_expensive_descendant": False,
    }
    drill_item = {
        "task_id": "root-001/0.0",
        "root_id": "root-001",
        "depth": 1,
        "resource_class": "fast",
        "has_expensive_descendant": True,
    }
    slow_item = {
        "task_id": "root-001/0.0.0.0",
        "root_id": "root-001",
        "depth": 3,
        "resource_class": "slow",
        "has_expensive_descendant": False,
    }

    assert mod.score(drill_item, root, is_active=True) > mod.score(cheap_item, root, is_active=True)
    assert mod.score(slow_item, root, is_active=True) > mod.score(drill_item, root, is_active=True)



def test_pick_next_fills_slow_slots_when_open():
    mod = _scheduler_module()

    roots = {
        "root-000": mod.RootState(root_id="root-000", admitted=True, pending=2),
    }
    resources = {
        "fast": mod.ResourcePool(name="fast", capacity=4, in_flight=0, gate_open=True),
        "slow": mod.ResourcePool(name="slow", capacity=2, in_flight=0, gate_open=True),
    }
    candidates = [
        {"task_id": "root-000/0.1.0", "root_id": "root-000", "depth": 2, "resource_class": "fast", "has_expensive_descendant": False},
        {"task_id": "root-000/0.0.0", "root_id": "root-000", "depth": 2, "resource_class": "slow", "has_expensive_descendant": False},
    ]

    best = mod.pick_next(candidates, roots, resources, max_active_roots=3)
    assert best is not None
    assert best["resource_class"] == "slow"



def test_pick_next_respects_gate_closed():
    mod = _scheduler_module()

    roots = {
        "root-000": mod.RootState(root_id="root-000", admitted=True, pending=2),
    }
    resources = {
        "fast": mod.ResourcePool(name="fast", capacity=1, in_flight=0, gate_open=True),
        "slow": mod.ResourcePool(name="slow", capacity=2, in_flight=0, gate_open=False),
    }
    candidates = [
        {"task_id": "root-000/0.0.0", "root_id": "root-000", "depth": 2, "resource_class": "slow", "has_expensive_descendant": False},
        {"task_id": "root-000/0.1.0", "root_id": "root-000", "depth": 2, "resource_class": "fast", "has_expensive_descendant": False},
    ]

    best = mod.pick_next(candidates, roots, resources, max_active_roots=3)
    assert best is not None
    assert best["resource_class"] == "fast"



def test_root_admission_prefers_earlier_slow_unlock():
    mod = _scheduler_module()

    roots = {
        "root-001": mod.RootState(root_id="root-001", admitted=False, pending=4),
        "root-002": mod.RootState(root_id="root-002", admitted=False, pending=4),
    }
    resources = {
        "fast": mod.ResourcePool(name="fast", capacity=4, in_flight=0, gate_open=True),
        "slow": mod.ResourcePool(name="slow", capacity=2, in_flight=0, gate_open=True),
    }
    candidates = [
        {
            "task_id": "root-001/0",
            "root_id": "root-001",
            "depth": 0,
            "resource_class": "fast",
            "has_expensive_descendant": True,
            "distance_to_nearest_slow_descendant": 1,
        },
        {
            "task_id": "root-002/0",
            "root_id": "root-002",
            "depth": 0,
            "resource_class": "fast",
            "has_expensive_descendant": False,
            "distance_to_nearest_slow_descendant": 99,
        },
    ]

    best = mod.pick_next(candidates, roots, resources, max_active_roots=3)
    assert best is not None
    assert best["root_id"] == "root-001"
