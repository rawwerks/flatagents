#!/usr/bin/env python3
"""
Run a single worker machine.

Claims one job, processes it, then exits.

Usage:
    python run_worker.py
    python run_worker.py --pool my_pool
    python run_worker.py --worker-id my-worker-123
"""

import argparse
import asyncio
import uuid
import sys
from pathlib import Path

# Add parent directories to path
EXAMPLE_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(Path(__file__).parent))

from flatmachines import FlatMachine, HooksRegistry
from hooks import DemoHooks


async def main():
    parser = argparse.ArgumentParser(description="Run a single job worker")
    parser.add_argument("--pool", "-p", default="default", help="Pool ID")
    parser.add_argument("--worker-id", "-w", default=None, help="Worker ID (auto-generated if not provided)")
    parser.add_argument("--db", default=None, help="Database path (optional)")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    args = parser.parse_args()
    
    worker_id = args.worker_id or f"worker-{uuid.uuid4().hex[:8]}"
    config_path = EXAMPLE_DIR / "config" / "job_worker.yml"
    
    print(f"Starting worker {worker_id} (pool={args.pool})")
    
    registry = HooksRegistry()
    registry.register("distributed-worker", DemoHooks)
    machine = FlatMachine(config_file=str(config_path), hooks_registry=registry)
    
    result = await machine.execute(input={
        "pool_id": args.pool,
        "worker_id": worker_id,
    })
    
    status = result.get("status", "unknown")
    job_id = result.get("job_id")
    
    if job_id:
        print(f"\n✅ Worker complete! Processed job {job_id[:8]}...")
    else:
        print(f"\n⚠️ Worker complete: {status}")
    
    return result


if __name__ == "__main__":
    asyncio.run(main())
