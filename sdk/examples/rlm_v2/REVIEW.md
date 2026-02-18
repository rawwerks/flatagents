
 PLAN.md Review

 I've read the plan, the source digest (RLM_DIGEST.md), and the existing v1
 implementation. Here's my assessment:

 ### ✅ What's Good

 1. Dramatically simpler architecture — V1 has 12+ states and 7 agents; v2 has
 ~5 states and 1 agent. This is the right call. The paper's Algorithm 1 is a
 tight loop, not a pipeline.
 2. Persistent REPL — V1 has a critical flaw: _execute_repl creates a fresh
 REPLExecutor() every call, so variables don't persist across iterations. The
 plan correctly fixes this (section 6: "Persistent namespace across loop
 iterations").
 3. Bounded metadata — Returning stdout_prefix, stdout_length, error flags
 instead of raw output matches the paper's design. The prompt instruction to
 "maintain buffers in variables" is a key paper insight.
 4. Strict Final variable — Clean, avoids the FINAL(...) / FINAL_VAR(...) tag
 confusion the paper identifies as a failure signature. Abstracted via
 TerminationStrategy for later extension.
 5. Parameter plumbing — CLI → machine input → context → hooks/repl. Clean
 end-to-end.

 ─────────────────────────────────────────────────────────────────────────────

 ### ⚠️ Issues & Gaps

 1. Recursive llm_query mechanism is underspecified (biggest risk)

 The plan says llm_query "launches same machine recursively with sub-prompt
 input" — but how? FlatMachines has no native "invoke self from within a hook
 action" pattern. The hook would need to programmatically load the machine
 config, construct a new Machine instance, and call execute() synchronously.
 This is the hardest part of the implementation and deserves a concrete
 sketch:
 - Where does the machine config path come from? Hard-coded? Passed via
 context?
 - How is the flatmachines Machine class imported and invoked inside hooks.py?
 - Is there a risk of circular imports or config resolution issues?

 2. Depth tracking not threaded through context

 The plan mentions max_depth (default 5) and "increments depth" but doesn't
 specify:
 - Where current_depth lives in context (should be an explicit context
 variable in machine.yml)
 - How it's passed into recursive invocations (needs to be in the input
 mapping of the recursive llm_query call)
 - What the sub-machine's initial state receives

 3. History management is hand-waved

 Section 4 says generate_code receives "compact history metadata" but there's
 no detail on:
 - How iteration history accumulates in context
 - Whether there's a sliding window or fixed-size buffer
 - What "compact" means concretely (last N entries? summary? just the metadata
 dicts?)

 This matters because context window saturation on the root model is the exact
 problem RLMs solve at the input level — you don't want to re-introduce it at
 the history level.

 4. No concrete machine.yml sketch

 The plan describes states in prose but doesn't show even pseudocode YAML.
 Given the v1 machine.yml is 130+ lines, a v2 sketch would clarify:
 - How the generate_code → execute_code → check_final loop transitions back
 - Whether execute_code and check_final are separate action states or combined
 - How max_iterations is enforced (transition condition vs max_steps)

 5. Sync vs async for subcalls

 "Per-subcall timeout via asyncio.wait_for/equivalent wrapper" — but is the
 main loop sync or async? If hooks.py calls machine.execute() synchronously
 inside a REPL exec(), and the REPL is called from another hook, you may hit
 event loop nesting issues. Needs a decision: fully sync with threading.Timer
 for timeouts, or async throughout.

 6. max_iter_done output undefined

 What does this final state return? The user needs to know the task hit the
 iteration cap. Should include the best partial result from REPL variables
 (e.g., if Final was never set but some variable holds a partial answer).

 7. No demo task specified

 Section 10 says "simple demo task succeeds" — what task? V1 presumably had
 something. A concrete example (e.g., "count occurrences of X in a 200K-char
 doc") would anchor the validation.

 8. llm_query(prompt, model=None) — model routing unclear

 The paper uses different models for root vs sub-calls (GPT-5-mini for
 sub-calls). What does model=None do — use the same profile as root? Fall back
 to default profile? This should be explicit.

 ─────────────────────────────────────────────────────────────────────────────

 ### 📝 Suggestions

 1. Add a machine.yml skeleton (even 20 lines of pseudo-YAML) to section 4
 2. Add a llm_query implementation sketch to section 6 showing the recursive
 Machine instantiation
 3. Add current_depth: 0 and iteration_history: [] as explicit context
 variables
 4. Specify history compaction: e.g., "keep last 5 iteration metadata dicts,
 each ≤200 chars"
 5. Decide sync-only for v2 (simpler; matches paper's blocking approach) with
 signal.alarm or thread-based timeout
 6. Define max_iter_done output: { answer: context.best_partial, reason:
 "max_iterations", iterations: N }
 7. Pick a concrete demo: e.g., counting named entities in a long document, or
 answering a question over a 500K-char text file

 ### Verdict

 The plan is directionally correct and a significant improvement over v1. The
 core loop design faithfully follows Algorithm 1. The main gap is the
 recursive llm_query mechanism — that's the novel/hard part and needs more
 design before implementation.
