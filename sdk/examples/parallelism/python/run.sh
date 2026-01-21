#!/bin/bash
set -e

VENV_PATH=".venv"

# Parse arguments
LOCAL_INSTALL=false
PASSTHROUGH_ARGS=()
while [[ $# -gt 0 ]]; do
    case $1 in
        --local|-l) LOCAL_INSTALL=true; shift ;;
        *) PASSTHROUGH_ARGS+=("$1"); shift ;;
    esac
done

echo "--- Parallelism Demo Runner ---"

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

echo "📁 Project root: $PROJECT_ROOT"
echo "📁 Python SDK: $PYTHON_SDK_PATH"

cd "$SCRIPT_DIR"

# Create venv
if [ ! -d "$VENV_PATH" ]; then
    uv venv "$VENV_PATH"
fi

# Install (PyPI by default, local with --local flag)
if [ "$LOCAL_INSTALL" = true ]; then
    uv pip install --python "$VENV_PATH/bin/python" -e "$PYTHON_SDK_PATH[litellm]"
else
    uv pip install --python "$VENV_PATH/bin/python" "flatagents[litellm]"
fi
uv pip install --python "$VENV_PATH/bin/python" -e "$SCRIPT_DIR"

# Run
"$VENV_PATH/bin/python" -m parallelism.main "${PASSTHROUGH_ARGS[@]}"