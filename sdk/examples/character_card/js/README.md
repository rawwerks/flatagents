# Character Card Example (JavaScript)

Chat with AI characters from Character Card PNG/JSON files.

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
./run.sh card.png
```

## Usage

```bash
# User identity
./run.sh card.png --user "Alice" --persona "A curious student"
./run.sh card.png --persona-file persona.json

# Inject messages
./run.sh card.png --messages-file history.json

# Auto-user mode (LLM generates user responses)
./run.sh card.png --auto-user

# For models without system prompt (Gemma, etc.)
./run.sh card.png --no-system-prompt
```

Type `/quit` to exit.

## Files

### persona.json (optional)

```json
{
  "name": "Alice",
  "description": "A curious graduate student studying AI safety"
}
```

### messages.json (optional)

```json
[
  {"role": "user", "content": "[Start]"},
  {"role": "assistant", "content": "Hello there!"},
  {"role": "user", "content": "Hi, I wanted to ask about..."}
]
```

## Message Format

Following SillyTavern conventions:

1. **Messages alternate** user/assistant
2. **First message**: `[Start]` user message before first_mes
3. **post_history_instructions**: Appended as `\n\nSystem: ...` (not saved)
4. **User persona**: Included in system prompt

## CLI Options

| Option | Description |
|--------|-------------|
| `--user`, `-u` | User name (default: User) |
| `--persona`, `-p` | User description text |
| `--persona-file` | JSON file with persona |
| `--messages-file`, `-m` | JSON file with initial messages |
| `--auto-user`, `-a` | LLM-driven user responses |
| `--max-turns`, `-t` | Max turns for auto-user (default: 1) |
| `--no-system-prompt` | For Gemma and similar models |

## Supported Versions

- **V1**: TavernCardV1 (flat structure)
- **V2**: chara_card_v2 (malfoyslastname spec)
- **V3**: chara_card_v3 (kwaroran spec)
