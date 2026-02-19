
 Agreed. Here’s a clean fix plan focused on the smoking gun only.

 Root cause (confirmed)

 Task was destroyed but it is pending! ... LoggingWorker._worker_loop() is
 from LiteLLM’s global async logging worker surviving nested subcall loop
 teardown.

 Plan (minimal + maintainable)

 ### 1) Add a runtime guard to disable LiteLLM background logging worker
 (Needed)

 Where: python/src/rlm_v2/hooks.py
 Why there: runs for root + subcalls regardless of CLI entry path.

 - Add a private helper in hooks, e.g.
 _disable_litellm_background_logging_worker_once().
 - Lazy-import GLOBAL_LOGGING_WORKER.
 - One-time monkeypatch:
     - replace ensure_initialized_and_enqueue(...) with no-op.
     - mark with sentinel flag so it’s idempotent.
 - Call helper from RLMV2Hooks.__init__.

 This avoids creating background worker tasks at all, so no pending-task
 destruction warnings.

 ─────────────────────────────────────────────────────────────────────────────

 ### 2) Add unit tests for the guard (Needed)

 File: python/tests/unit/test_hooks.py

 Add tests that verify:
 - guard is idempotent (safe to call multiple times),
 - enqueue function becomes no-op,
 - no exception if LiteLLM import is unavailable.

 (Use monkeypatch/fake worker object; no real network/model calls.)

 ─────────────────────────────────────────────────────────────────────────────

 ### 3) Verify on real run + traces (Needed)

 Run demo and check traces:
 - no Task was destroyed but it is pending! in stderr_preview,
 - no LoggingWorker._worker_loop leakage,
 - run still reaches final.

 ─────────────────────────────────────────────────────────────────────────────

 Optional hardening (Desirable, not required for fix)

 1. Add env toggle (RLM_V2_DISABLE_LITELLM_BG_WORKER=1 default on) so behavior
 is explicit.
 2. Add post-run grep check script for this warning string.
 3. Open upstream LiteLLM issue with reproduction pattern (nested sync
 subcalls + loop teardown).

 ─────────────────────────────────────────────────────────────────────────────

 If you approve, I’ll implement exactly steps 1–3 only.


