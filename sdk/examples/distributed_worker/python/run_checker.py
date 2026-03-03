#!/usr/bin/env python3
"""
Run the parallelization checker machine.

Checks pool depth vs active workers and spawns new workers if needed.

Usage:
    python run_checker.py
    python run_checker.py --max-workers 5
    python run_checker.py --pool my_pool
"""

import argparse
import asyncio
import sys
from pathlib import Path

# Add parent directories to path
EXAMPLE_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(Path(__file__).parent))

from flatmachines import FlatMachine, HooksRegistry
from hooks import DemoHooks


async def main():
    parser = argparse.ArgumentParser(description="Run parallelization checker")
    parser.add_argument("--max-workers", "-m", type=int, default=3, help="Maximum workers to spawn")
    parser.add_argument("--pool", "-p", default="default", help="Pool ID")
    parser.add_argument("--db", default=None, help="Database path (optional)")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    args = parser.parse_args()
    
    config_path = EXAMPLE_DIR / "config" / "parallelization_checker.yml"
    
    print(f"Running parallelization checker (max_workers={args.max_workers}, pool={args.pool})")
    
    registry = HooksRegistry()
    registry.register("distributed-worker", DemoHooks)
    machine = FlatMachine(config_file=str(config_path), hooks_registry=registry)
    
    result = await machine.execute(input={
        "pool_id": args.pool,
        "max_workers": args.max_workers,
    })
    
    spawned = result.get("spawned", 0)
    print(f"\n✅ Checker complete! Spawned {spawned} worker(s).")
    
    return result


if __name__ == "__main__":
    asyncio.run(main())
