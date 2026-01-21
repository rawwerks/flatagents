#!/bin/bash
# GEPA Self-Optimizer - Test Run
# An inexpensive test run with minimal examples and iterations

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
echo "=========================================="
echo "GEPA Self-Optimizer - Test Run"
echo "=========================================="
echo ""

# Get the directory where this script lives
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

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

# 0. Ensure uv is installed
if ! command -v uv &> /dev/null; then
    echo "📥 Installing uv..."
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

# Minimal test configuration
NUM_EXAMPLES=10        # Small dataset for testing
BUDGET=2               # 2 optimization iterations

# Estimated calls:
# - Data generation: 10 * 2 (task + response) = 20
# - Base pareto eval: ~3 (d_pareto size)
# - Per iteration: ~10 (minibatch evals + reflective update + pareto eval if promoted)
# - Summary: 1
# Total: ~20 + 3 + 2*10 + 1 = ~44 calls

echo ""
echo "Test configuration:"
echo "  - Examples: $NUM_EXAMPLES"
echo "  - Budget (iterations): $BUDGET"
echo ""
echo "Estimated LLM calls: ~44"
echo ""

echo ""
echo "Step 1: Generating evaluation data..."
echo "----------------------------------------"
"$VENV_PATH/bin/python" main.py generate-data \
    --num-examples $NUM_EXAMPLES \
    --correct-ratio 0.3

echo ""
echo "Step 2: Evaluating baseline judge..."
echo "----------------------------------------"
"$VENV_PATH/bin/python" main.py evaluate

echo ""
echo "Step 3: Running optimization..."
echo "----------------------------------------"
"$VENV_PATH/bin/python" main.py optimize \
    --budget $BUDGET

echo ""
echo "=========================================="
echo "Test run complete!"
echo "=========================================="
echo ""
echo "Outputs:"
echo "  - Optimized judge: ../output/optimized_judge.yml"
echo "  - Optimization log: ../output/optimization_log.json"
echo "  - Summary: ../output/summary.json"
echo ""
echo "To evaluate the optimized judge:"
echo "  .venv/bin/python main.py evaluate --judge ../output/optimized_judge.yml"
