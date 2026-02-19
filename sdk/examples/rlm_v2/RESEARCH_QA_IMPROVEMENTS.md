# Research QA Improvements

## Summary
Refactored `python/src/rlm_v2/research_qa.py` to align more closely with RLM principles from `RLM_DIGEST.md` (Algorithm-1 style: externalized context in REPL + symbolic decomposition + recursive subcalls), instead of relying on a retrieval-first pipeline.

## 1) RLM-native mode is now the default
**File:** `python/src/rlm_v2/research_qa.py`

- Added ask mode selector:
  - `--mode native` (default): loads a lightweight corpus manifest (DOC ids + paths + metadata) into REPL `context`.
  - `--mode retrieval`: optional BM25 prefilter fallback.
- Native mode now avoids the anti-pattern of serializing full file contents into `context`; the agent can read files on demand in REPL code.

## 2) Truncation removed as default
**File:** `python/src/rlm_v2/research_qa.py`

- `parse_markdown(..., max_body_chars)` now defaults to no truncation.
- `index --max-body-chars` default changed to `0` (`0` = no truncation).
- `ask --max-doc-chars` default changed to `0` (`0` = no truncation).
- This preserves source material for REPL-time decomposition and avoids preemptive context loss.

## 3) Native corpus loading support
**File:** `python/src/rlm_v2/research_qa.py`

- Added `list_corpus_docs(..., include_body=False)` defaulting to manifest-only loading in native mode.
- `build_retrieval_context(...)` now supports toggles for retrieval score/snippet/body so native mode can pass only path metadata while retrieval mode includes body text.
- Verification output remains deterministic and compatible with citation checks.

## 4) Prompt/task framing tightened for RLM behavior
**File:** `python/src/rlm_v2/research_qa.py`

- `_research_task(...)` now explicitly instructs:
  - symbolic operations on `context` (`search/slice/chunk`),
  - `llm_query(...)` for focused semantic sub-analysis,
  - variable-based state accumulation across iterations,
  - setting `Final` only when complete.

## 5) CLI behavior updated
**File:** `python/src/rlm_v2/research_qa.py`

- `ask` command now includes `--mode native|retrieval` (default `native`).
- `--dry-run` prints selected docs in either mode.
- `--save-retrieval` now saves the selected document list for the active mode.

## 6) Documentation updated
**File:** `python/README.md`

- Added native-vs-retrieval usage examples.
- Clarified native mode uses manifest-only context and retrieval mode carries document bodies.

## 7) Tests updated and passing
**File:** `python/tests/unit/test_research_qa.py`

- Added tests for:
  - native corpus loading (`list_corpus_docs`),
  - native context rendering without retrieval-score fields.
- Test result: `31 passed`.

## Potential next improvements
- Add explicit subcall budgets (max subcalls / per-iteration limits).
- Add recursion-depth ablation options for controlled experiments.
- Add per-subcall cost/runtime telemetry and aggregate reporting.
- Add native vs retrieval mode benchmark script (quality/cost/latency side-by-side).
