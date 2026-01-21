# Multi-Paper Research Synthesizer (JavaScript)

Analyzes multiple papers, compares findings, identifies gaps, and produces a synthesized report.

## Prerequisites

1. **Node.js & npm**: Node.js 16+ and npm installed.
2. **LLM API Key**: This demo uses Cerebras by default, so set `CEREBRAS_API_KEY` (or update `config/profiles.yml`).

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
cd sdk/examples/multi_paper_synthesizer/js
npm install
npm run build
node dist/multi_paper_synthesizer/main.js
```

## File Structure

```
multi_paper_synthesizer/
├── config/
│   ├── comparator.yml
│   ├── gap_finder.yml
│   ├── synthesizer.yml
│   ├── critic.yml
│   └── formatter.yml
├── paper_analyzer/
│   └── config/              # Per-paper analysis machine
├── data/
│   ├── papers/              # Downloaded PDFs + extracted text
│   └── synthesis_report.md
├── js/
│   ├── src/
│   │   └── multi_paper_synthesizer/
│   │       └── main.ts
│   ├── package.json
│   ├── tsconfig.json
│   ├── run.sh
│   └── README.md
└── python/
```

## Notes

- Each paper is analyzed with the `paper_analyzer` peer machine.
- The synthesis phase runs comparator → gap finder → synthesis → critique loop → formatter.
- Final report saved to `data/synthesis_report.md`.
