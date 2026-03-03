#!/usr/bin/env python3
"""
Run the stale worker reaper machine.

Finds workers that have missed heartbeats and releases their jobs.

Usage:
    python run_reaper.py
    python run_reaper.py --threshold 120
    python run_reaper.py --pool my_pool
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
    parser = argparse.ArgumentParser(description="Run stale worker reaper")
    parser.add_argument("--threshold", "-t", type=int, default=60, help="Stale threshold in seconds")
    parser.add_argument("--pool", "-p", default="default", help="Pool ID")
    parser.add_argument("--db", default=None, help="Database path (optional)")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    args = parser.parse_args()
    
    config_path = EXAMPLE_DIR / "config" / "stale_worker_reaper.yml"
    
    print(f"Running stale worker reaper (threshold={args.threshold}s, pool={args.pool})")
    
    registry = HooksRegistry()
    registry.register("distributed-worker", DemoHooks)
    machine = FlatMachine(config_file=str(config_path), hooks_registry=registry)
    
    result = await machine.execute(input={
        "pool_id": args.pool,
        "stale_threshold_seconds": args.threshold,
    })
    
    reaped = result.get("reaped_count", 0)
    print(f"\n✅ Reaper complete! Cleaned up {reaped} stale worker(s).")
    
    return result


if __name__ == "__main__":
    asyncio.run(main())
