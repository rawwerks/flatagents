#!/bin/bash
# Multi-Paper Research Synthesizer Demo
# Analyzes multiple research papers and synthesizes insights

set -e

# --- Configuration ---
VENV_DIR=".venv"

# --- Parse Arguments ---
LOCAL_INSTALL=false
while [[ $# -gt 0 ]]; do
    case $1 in
        --local|-l)
            LOCAL_INSTALL=true
            shift
            ;;
        *)
            shift
            ;;
    esac
done

# --- Script Logic ---
echo "--- Multi-Paper Research Synthesizer ---"

# Check for API key
if [ -z "$CEREBRAS_API_KEY" ]; then
    echo "Error: CEREBRAS_API_KEY environment variable not set"
    echo "Export it before running: export CEREBRAS_API_KEY='your-key'"
    exit 1
fi

# Get the directory the script is located in
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Establish project root by walking up to find .git
# This ensures paths work regardless of where the script is invoked from
find_project_root() {
    local dir="$1"
    while [[ "$dir" != "/" ]]; do
        if [[ -e "$dir/.git" ]]; then
            echo "$dir"
            return 0
        fi
        dir="$(dirname "$dir")"
    done
    echo "Error: Could not find project root (no .git found)" >&2
    return 1
}

PROJECT_ROOT="$(find_project_root "$SCRIPT_DIR")"
PYTHON_SDK_PATH="$PROJECT_ROOT/sdk/python"

echo "📁 Project root: $PROJECT_ROOT"
echo "📁 Python SDK: $PYTHON_SDK_PATH"

# Change to the script's directory so `uv` can find pyproject.toml
cd "$SCRIPT_DIR"

# 0. Ensure uv is installed
if ! command -v uv &> /dev/null; then
    echo "📥 Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
fi

# Create venv if needed
echo "Ensuring virtual environment..."
if [ ! -d "$VENV_DIR" ]; then
    echo "Creating virtual environment..."
    uv venv "$VENV_DIR"
fi

echo "Virtual environment ready."

# Install dependencies
echo "Installing dependencies..."
if [ "$LOCAL_INSTALL" = true ]; then
    echo "  - Installing flatagents from local source..."
    uv pip install --python "$VENV_DIR/bin/python" -e "$PYTHON_SDK_PATH[litellm]" --quiet
else
    echo "  - Installing flatagents from PyPI..."
    uv pip install --python "$VENV_DIR/bin/python" "flatagents[litellm]" --quiet
fi

echo "  - Installing multi_paper_synthesizer package..."
uv pip install --python "$VENV_DIR/bin/python" -e "$SCRIPT_DIR" --quiet

# Run the demo
echo "Running demo..."
echo "---"
"$VENV_DIR/bin/python" -m multi_paper_synthesizer.main
echo "---"
echo "Demo complete!"
