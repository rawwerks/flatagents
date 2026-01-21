# RLM Demo (JavaScript)

Recursive Language Model (RLM) demo for long-context processing using a sandboxed REPL + recursive decomposition.

## Prerequisites

1. **Node.js & npm**: Node.js 16+ and npm installed.
2. **LLM API Key**: This demo uses Cerebras by default, so set `CEREBRAS_API_KEY` (or update `config/profiles.yml`).

## Quick Start (with `run.sh`)

```bash
# Set your API key
export CEREBRAS_API_KEY="your-api-key-here"

# Make the script executable (if you haven't already)
chmod +x run.sh

# Run the demo with a file
./run.sh --file document.txt --task "What are the main themes?"
```

## Manual Setup

```bash
cd sdk/examples/rlm/js
npm install
npm run build
node dist/rlm/main.js --file document.txt --task "What are the main themes?"
```

## CLI Options

```bash
node dist/rlm/main.js --file document.txt --task "What are the main themes?" \
  --chunk-size 8000 \
  --max-exploration-rounds 5

# Interactive mode
node dist/rlm/main.js --interactive

# Demo mode
node dist/rlm/main.js --demo
```

## File Structure

```
rlm/
├── config/
│   └── machine.yml          # RLM machine
├── js/
│   ├── src/
│   │   └── rlm/
│   │       ├── repl.ts       # Sandboxed REPL
│   │       ├── hooks.ts      # RLM hooks
│   │       └── main.ts       # CLI + demo
│   ├── package.json
│   ├── tsconfig.json
│   ├── run.sh
│   └── README.md
└── python/
```
