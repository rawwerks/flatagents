# MDAP Demo (JavaScript)

Implements MDAP (first-to-ahead-by-k voting) using regex parsing + JSON Schema validation.

## Prerequisites

1. **Node.js & npm**: Node.js 16+ and npm installed.
2. **LLM API Key**: This demo uses Cerebras by default, so set `CEREBRAS_API_KEY` (or update `config/hanoi.yml`).

## Quick Start (with `run.sh`)

```bash
# Set your API key
export CEREBRAS_API_KEY="your-api-key-here"

# Make the script executable (if you haven't already)
chmod +x run.sh

# Run the demo
./run.sh
```

## Manual Setup

```bash
cd sdk/examples/mdap/js
npm install
npm run build
node dist/mdap/demo.js
```

## File Structure

```
mdap/
├── config/
│   └── hanoi.yml            # Agent config + MDAP metadata
├── js/
│   ├── src/
│   │   └── mdap/
│   │       ├── mdap.ts       # MDAP orchestrator
│   │       └── demo.ts       # Hanoi demo
│   ├── package.json
│   ├── tsconfig.json
│   ├── run.sh
│   └── README.md
└── python/
```

## Notes

- Regex parsing and JSON Schema validation are configured in `metadata` within `config/hanoi.yml`.
- Red-flag tracking follows the MAKER paper (format errors, validation failures, length exceeded).
