#!/bin/bash
set -e

# --- Configuration ---
VENV_PATH=".venv"
PORT=8081  # Different port from helloworld

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
echo "--- FlatAgents GCP Parallelism Demo ---"

# Get the directory the script is located in
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Establish project root by walking up to find .git
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

# Change to the script's directory
cd "$SCRIPT_DIR"

# 0. Ensure uv is installed
if ! command -v uv &> /dev/null; then
    echo "📥 Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
fi

# 1. Create Virtual Environment
echo "🔧 Ensuring virtual environment..."
if [ ! -d "$VENV_PATH" ]; then
    uv venv "$VENV_PATH"
else
    echo "✅ Virtual environment already exists."
fi

# 2. Install Dependencies
echo "📦 Installing dependencies..."
if [ "$LOCAL_INSTALL" = true ]; then
    echo "  - Installing flatagents from local source..."
    uv pip install --python "$VENV_PATH/bin/python" -e "$PYTHON_SDK_PATH[gcp]"
else
    echo "  - Installing flatagents from PyPI..."
    uv pip install --python "$VENV_PATH/bin/python" "flatagents[gcp]"
fi

echo "  - Installing Cloud Functions framework..."
uv pip install --python "$VENV_PATH/bin/python" functions-framework

# 3. Check for LLM API key
if [ -z "$LLM_API_KEY" ] && [ -z "$OPENAI_API_KEY" ] && [ -z "$CEREBRAS_API_KEY" ]; then
    echo ""
    echo "⚠️  No LLM API key found. Set one of:"
    echo "    export LLM_API_KEY=your-key"
    echo "    export OPENAI_API_KEY=your-key"
    echo "    export CEREBRAS_API_KEY=your-key"
    exit 1
fi

# 4. Check if port is already in use
if lsof -i:$PORT > /dev/null 2>&1; then
    echo "❌ Error: Port $PORT is already in use."
    echo "   Kill the existing process with: lsof -ti:$PORT | xargs kill -9"
    exit 1
fi

# 5. Start function server in background
echo ""
echo "🚀 Starting Cloud Function server on port $PORT..."

# Set required env vars
export GOOGLE_CLOUD_PROJECT="${GOOGLE_CLOUD_PROJECT:-demo-project}"

# Start server in background
"$VENV_PATH/bin/python" -m functions_framework --target=parallelism --port=$PORT &
SERVER_PID=$!

# Cleanup function
cleanup() {
    echo ""
    echo "🧹 Stopping server..."
    kill $SERVER_PID 2>/dev/null || true
}
trap cleanup EXIT

# Wait for server to be ready
echo "⏳ Waiting for server to start..."
for i in {1..30}; do
    if curl -s http://localhost:$PORT > /dev/null 2>&1; then
        break
    fi
    sleep 0.5
done

# Check if server started
if ! curl -s http://localhost:$PORT > /dev/null 2>&1; then
    echo "❌ Server failed to start"
    exit 1
fi
echo "✅ Server ready"

# 6. Run the tests
echo ""
echo "🧪 Test 1: Fire-and-forget launch (uses MachineInvoker)"
echo "---"

RESULT1=$(curl -s -X POST "http://localhost:$PORT" \
    -H "Content-Type: application/json" \
    -d '{"type": "background_notifications", "message": "Hello from GCP!"}')

echo "Response: $RESULT1"

if echo "$RESULT1" | grep -q '"result"'; then
    echo "✅ Test 1 passed!"
else
    echo "❌ Test 1 failed."
    exit 1
fi

echo ""
echo "🧪 Test 2: Parallel aggregation (uses ResultBackend)"
echo "---"

RESULT2=$(curl -s -X POST "http://localhost:$PORT" \
    -H "Content-Type: application/json" \
    -d '{"type": "parallel_aggregation", "texts": ["Hello world", "Goodbye world"]}')

echo "Response: $RESULT2"

if echo "$RESULT2" | grep -q '"result"'; then
    echo "✅ Test 2 passed!"
else
    echo "❌ Test 2 failed."
    exit 1
fi

echo ""
echo "✅ All tests passed! (PersistenceBackend, ResultBackend, MachineInvoker all exercised)"
