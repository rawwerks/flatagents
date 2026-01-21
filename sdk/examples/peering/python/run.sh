#!/bin/bash
set -e

# --- Configuration ---
VENV_PATH=".venv"

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
echo "--- FlatAgents Peering Demo Runner ---"

# Get the directory the script is located in
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

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

echo "Project root: $PROJECT_ROOT"
echo "Python SDK: $PYTHON_SDK_PATH"

# Change to the script's directory so `uv` can find pyproject.toml
cd "$SCRIPT_DIR"

# 0. Ensure uv is installed
if ! command -v uv &> /dev/null; then
    echo "Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
fi

# 1. Create Virtual Environment
echo "Ensuring virtual environment..."
if [ ! -d "$VENV_PATH" ]; then
    uv venv "$VENV_PATH"
else
    echo "Virtual environment already exists."
fi

# 3. Install Dependencies
echo "Installing dependencies..."
if [ "$LOCAL_INSTALL" = true ]; then
    echo "  - Installing flatagents from local source..."
    uv pip install --python "$VENV_PATH/bin/python" -e "$PYTHON_SDK_PATH[litellm]"
else
    echo "  - Installing flatagents from PyPI..."
    uv pip install --python "$VENV_PATH/bin/python" "flatagents[litellm]"
fi

echo "  - Installing peering demo package..."
uv pip install --python "$VENV_PATH/bin/python" -e "$SCRIPT_DIR"

# 4. Run the Demo
echo "Running demo..."
echo "---"
"$VENV_PATH/bin/python" -m peering.main
echo "---"

echo "Demo complete!"
