# Research QA (RLM v2) — Dedicated README

This README is only for the `research_qa` workflow (`python/src/rlm_v2/research_qa.py`).

It covers setup, indexing, ask modes, outputs, and troubleshooting.

---

## What this tool does

`research_qa` is a research-corpus question-answering CLI on top of RLM v2.

It supports two modes:

1. **native** (default):
   - Loads a lightweight corpus manifest into REPL `context` (DOC id + path + metadata, no full bodies).
   - Lets the recursive loop do symbolic decomposition (`search/slice/chunk`) and targeted file reads via Python, with optional sub-calls via `llm_query(...)`.

2. **retrieval**:
   - Uses SQLite FTS5/BM25 prefilter.
   - Runs RLM over the retrieved subset (includes body text for selected docs).

Both modes produce a deterministic verification payload (citations + doc paths + quotes + confidence).

---

## File locations

- CLI implementation: `python/src/rlm_v2/research_qa.py`
- Entry point script: `rlm-v2-research` (from `python/pyproject.toml`)
- RLM runtime: `python/src/rlm_v2/main.py`, `python/src/rlm_v2/hooks.py`
- Machine config: `config/machine.yml`
- Model profiles: `config/profiles.yml`

---

## Prerequisites

- Python 3.10+
- Installed dependencies from `python/pyproject.toml`
- Valid model/provider credentials for your configured profile in `config/profiles.yml`
  - Current example profile uses OpenRouter model names.

---

## Setup

From `sdk/examples/rlm_v2/python`:

```bash
# create venv if needed
uv venv .venv

# install this example package + deps
uv pip install --python .venv/bin/python -e .
```

You can then run either:

```bash
.venv/bin/rlm-v2-research --help
```

or

```bash
.venv/bin/python -m rlm_v2.research_qa --help
```

---

## Quick wrapper (recommended)

Use `python/research.sh` for common runs with presets:

```bash
./research.sh <index|basic|fast|compare|ask> [options]
```

Live status monitor:

```bash
# one-shot status
./watch_research_status.sh

# live refresh with watch
watch -n 2 ./watch_research_status.sh
# or
./watch_research_status.sh --watch --interval 2
```

Examples:

```bash
# Index corpus
./research.sh index --root ~/code/analysis/ml_research_analysis_2025

# Quality-first native run
./research.sh basic -q "What are the strongest 2025 long-context results?"

# Fast retrieval-first run
./research.sh fast -q "LoRA for vision" --top-k 30

# Run both native and retrieval for side-by-side artifacts
./research.sh compare -q "What works best for long-context QA?"
```

Notes:
- Presets auto-save selected docs + verification JSON into `./artifacts`.
- Use `--db` to point at a custom index path.
- Wrapper default: if `.venv` already exists, it **does not install** packages.
- Use `--install` to install/reinstall dependencies into `.venv`.
- Use `--local` with `--install` to reinstall from local FlatAgents/FlatMachines SDK sources.
- `ask/basic/fast/compare` always enable tracing by default (`--inspect --inspect-level summary --trace-dir ./traces --print-iterations`).
  You can override inspect level/trace dir by passing explicit ask flags.

---

## Command overview

```bash
rlm-v2-research {index,ask}
```

### `index`
Build/rebuild local SQLite index over markdown files.

```bash
rlm-v2-research index --help
```

Key flags:
- `--db`: SQLite DB path (default `./research_index.db`)
- `--root`: repeatable root directory containing `*.md`
- `--max-body-chars`: max chars stored per doc body (`0` = no truncation, default)

### `ask`
Ask a question over the indexed corpus using RLM.

```bash
rlm-v2-research ask --help
```

Key flags:
- `--question` / `-q` (required)
- `--mode native|retrieval` (default: `native`)
- `--top-k` (retrieval mode only)
- `--max-docs` (`0` = all docs for selected mode)
- `--max-doc-chars` (`0` = no truncation; mainly relevant to retrieval mode bodies)
- `--dry-run` (print selected docs only; skip RLM)
- RLM controls: `--max-depth --timeout-seconds --max-iterations --max-steps`
- Inspect/trace: `--inspect --inspect-level summary|full --trace-dir --print-iterations`
- Output files: `--save-retrieval --save-verification`

---

## Quick start

## 1) Build index

```bash
.venv/bin/rlm-v2-research index \
  --db ./research_index.db \
  --root ~/code/analysis/ml_research_analysis_2023 \
  --root ~/code/analysis/ml_research_analysis_2024 \
  --root ~/code/analysis/ml_research_analysis_2025
```

If no `--root` is passed, these 2023/2024/2025 paths are used by default.

## 2) Preview selection without running LLM

```bash
.venv/bin/rlm-v2-research ask \
  --db ./research_index.db \
  --question "What are the strongest findings about test-time scaling in 2025?" \
  --mode native \
  --dry-run
```

## 3) Run RLM in native mode (recommended default)

```bash
.venv/bin/rlm-v2-research ask \
  --db ./research_index.db \
  --question "What are the strongest findings about test-time scaling in 2025?" \
  --mode native \
  --inspect --inspect-level summary --print-iterations \
  --save-verification ./artifacts/verification.native.json
```

## 4) Run in retrieval mode (optional fallback)

```bash
.venv/bin/rlm-v2-research ask \
  --db ./research_index.db \
  --question "What are the strongest findings about test-time scaling in 2025?" \
  --mode retrieval --top-k 60 \
  --inspect --print-iterations \
  --save-retrieval ./artifacts/selected_docs.retrieval.json \
  --save-verification ./artifacts/verification.retrieval.json
```

---

## Output behavior

Console output includes:
- selected docs preview
- answer text
- mode (`native` or `retrieval`)
- reason (`final`, `max_iterations`, `error`, etc.)
- citation count
- confidence
- trace path (if inspect enabled)

`--save-verification` writes JSON with fields like:
- `question`
- `answer_text`
- `confidence`
- `citation_count`
- `citations[]` (`doc_id`, `path`, `title`, `arxiv_id`, `year`, `quote`, `why`)
- `invalid_doc_ids`
- `top_hits`

---

## Recommended settings

For high-fidelity research QA:
- `--mode native`
- start with bounded catalog size (e.g. `--max-docs 2000..10000`) and increase as needed
- `--inspect --inspect-level summary`
- `--print-iterations`

For cheaper/faster exploratory runs:
- `--mode retrieval --top-k 20..60`
- `--max-docs 20..40`
- `--max-iterations 8..12`

---

## Common issues

1. **`Index DB not found`**
   - Run `index` first, or pass the correct `--db` path.

2. **No docs selected / empty retrieval**
   - Verify index roots contain `.md` files.
   - Rebuild index and check returned `indexed` count.
   - In retrieval mode, try broader question terms or larger `--top-k`.

3. **Model/provider auth errors**
   - Ensure credentials/env vars for your profile provider are set.
   - Check `config/profiles.yml` model names and provider compatibility.

4. **Run ends with `max_iterations`**
   - Increase `--max-iterations` and/or `--timeout-seconds`.
   - Reduce scope with `--max-docs` for very large corpora.

5. **Cost/runtime too high**
   - Start with retrieval mode for triage.
   - Lower `--max-iterations` and `--max-depth`.

---

## Re-indexing guidance

Re-run `index` whenever corpus files change. Current index behavior is rebuild-style (clears and re-inserts docs).

---

## One-liner recipe

```bash
cd python && \
.venv/bin/rlm-v2-research index --db ./research_index.db && \
.venv/bin/rlm-v2-research ask --db ./research_index.db \
  --question "Summarize strongest 2025 long-context results" \
  --mode native --inspect --print-iterations \
  --save-verification ./artifacts/verification.json
```
