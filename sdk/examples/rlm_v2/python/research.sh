#!/usr/bin/env bash
# Convenience wrapper for research_qa workflows.
#
# Presets:
#   ./research.sh index [index args...]
#   ./research.sh basic -q "question" [ask args...]
#   ./research.sh fast -q "question" [ask args...]
#   ./research.sh compare -q "question" [ask args...]
#   ./research.sh ask [raw ask args...]
#
# Wrapper flags:
#   --local|-l         install flatagents/flatmachines from local repo sources
#   --install          install/reinstall dependencies into .venv
#   --db <path>        default DB path (applies to index/ask presets)
#   --artifact-dir <d> directory for auto-saved outputs in basic/fast/compare
#   --question|-q <q>  question for basic/fast/compare
#
# Trace behavior:
#   All ask-like commands always enable tracing by default:
#   --inspect --inspect-level summary --trace-dir ./traces --print-iterations
#   You can override inspect-level/trace-dir by passing those flags explicitly.

set -euo pipefail

VENV_PATH=".venv"
LOCAL_INSTALL=false
FORCE_INSTALL=false
DB_PATH="./research_index.db"
ARTIFACT_DIR="./artifacts"
QUESTION=""
COMMAND=""
PASSTHROUGH_ARGS=()

print_help() {
    cat <<'EOF'
Research QA wrapper (RLM v2)

Usage:
  ./research.sh <command> [wrapper options] [passthrough args]

Commands:
  index     Build/rebuild index (forwards to rlm_v2.research_qa index)
  basic     Native-mode ask preset (quality-first)
  fast      Retrieval-mode ask preset (cost/latency-first)
  compare   Run both native and retrieval presets for the same question
  ask       Raw ask passthrough (you control all ask flags)
  help      Show this help

Wrapper options:
  --local, -l            Install flatmachines/flatagents from local sdk sources
  --install              Install/reinstall dependencies into .venv
  --db <path>            DB path (default: ./research_index.db)
  --artifact-dir <dir>   Output dir for saved json artifacts (default: ./artifacts)
  --question, -q <text>  Question (required for basic/fast/compare)

Tracing:
  ask/basic/fast/compare always enable tracing by default:
    --inspect --inspect-level summary --trace-dir ./traces --print-iterations
  Override with explicit ask args (e.g. --inspect-level full, --trace-dir /tmp/traces).

Depth:
  ask/basic/fast/compare default to --max-depth 1 unless you explicitly pass --max-depth.

Examples:
  ./research.sh index --root ~/code/analysis/ml_research_analysis_2025
  ./research.sh basic -q "What are the strongest 2025 long-context results?"
  ./research.sh fast -q "LoRA for vision" --top-k 30
  ./research.sh compare -q "What works best for long-context QA?"
  ./research.sh ask --question "LoRA" --mode native --dry-run
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --local|-l)
            LOCAL_INSTALL=true
            shift
            ;;
        --install)
            FORCE_INSTALL=true
            shift
            ;;
        --db)
            DB_PATH="$2"
            shift 2
            ;;
        --artifact-dir)
            ARTIFACT_DIR="$2"
            shift 2
            ;;
        --question|-q)
            QUESTION="$2"
            shift 2
            ;;
        -h|--help|help)
            COMMAND="help"
            shift
            ;;
        index|basic|fast|compare|ask)
            if [[ -n "$COMMAND" ]]; then
                PASSTHROUGH_ARGS+=("$1")
            else
                COMMAND="$1"
            fi
            shift
            ;;
        *)
            PASSTHROUGH_ARGS+=("$1")
            shift
            ;;
    esac
done

if [[ -z "$COMMAND" ]]; then
    COMMAND="help"
fi

if [[ "$COMMAND" == "help" ]]; then
    print_help
    exit 0
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

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
FLATAGENTS_SDK_PATH="$PROJECT_ROOT/sdk/python/flatagents"
FLATMACHINES_SDK_PATH="$PROJECT_ROOT/sdk/python/flatmachines"

cd "$SCRIPT_DIR"

if ! command -v uv &> /dev/null; then
    echo "📥 Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
fi

echo "🔧 Ensuring virtual environment..."
CREATED_VENV=false
if [[ ! -d "$VENV_PATH" ]]; then
    uv venv "$VENV_PATH"
    CREATED_VENV=true
else
    echo "✅ Virtual environment already exists."
fi

SHOULD_INSTALL=false
if [[ "$CREATED_VENV" == true || "$FORCE_INSTALL" == true ]]; then
    SHOULD_INSTALL=true
fi

if [[ "$SHOULD_INSTALL" == true ]]; then
    REINSTALL_ARGS=()
    if [[ "$FORCE_INSTALL" == true ]]; then
        echo "📦 Reinstalling dependencies (--install)..."
        REINSTALL_ARGS=(--reinstall)
    else
        echo "📦 Installing dependencies (new .venv)..."
    fi

    if [[ "$LOCAL_INSTALL" == true ]]; then
        echo "  - Installing flatmachines from local source..."
        uv pip install "${REINSTALL_ARGS[@]}" --python "$VENV_PATH/bin/python" -e "$FLATMACHINES_SDK_PATH[flatagents]"
        echo "  - Installing flatagents from local source..."
        uv pip install "${REINSTALL_ARGS[@]}" --python "$VENV_PATH/bin/python" -e "$FLATAGENTS_SDK_PATH[litellm]"
    else
        echo "  - Installing flatmachines from PyPI..."
        uv pip install "${REINSTALL_ARGS[@]}" --python "$VENV_PATH/bin/python" "flatmachines[flatagents]"
        echo "  - Installing flatagents from PyPI..."
        uv pip install "${REINSTALL_ARGS[@]}" --python "$VENV_PATH/bin/python" "flatagents[litellm]"
    fi

    echo "  - Installing rlm_v2 package..."
    uv pip install "${REINSTALL_ARGS[@]}" --python "$VENV_PATH/bin/python" -e "$SCRIPT_DIR"
else
    echo "⏭️ Skipping install (existing .venv). Use --install to reinstall."

    if ! "$VENV_PATH/bin/python" -c "import flatagents, flatmachines, rlm_v2.research_qa" >/dev/null 2>&1; then
        echo "❌ Required packages are not available in $VENV_PATH." >&2
        echo "   Re-run with --install to install/reinstall dependencies." >&2
        exit 1
    fi
fi

run_research_qa() {
    "$VENV_PATH/bin/python" -m rlm_v2.research_qa "$@"
}

arg_in_passthrough() {
    local needle="$1"
    for arg in "${PASSTHROUGH_ARGS[@]}"; do
        if [[ "$arg" == "$needle" ]]; then
            return 0
        fi
    done
    return 1
}

passthrough_has_question=false
if arg_in_passthrough "--question" || arg_in_passthrough "-q"; then
    passthrough_has_question=true
fi

ensure_question() {
    if [[ -z "$QUESTION" && "$passthrough_has_question" == false ]]; then
        echo "Error: question is required for '$COMMAND'. Use --question/-q or pass --question in passthrough." >&2
        exit 1
    fi
}

maybe_question_args=()
if [[ -n "$QUESTION" ]]; then
    maybe_question_args=(--question "$QUESTION")
fi

TRACE_ARGS=()
if ! arg_in_passthrough "--inspect"; then
    TRACE_ARGS+=(--inspect)
fi
if ! arg_in_passthrough "--inspect-level"; then
    TRACE_ARGS+=(--inspect-level summary)
fi
if ! arg_in_passthrough "--trace-dir"; then
    TRACE_ARGS+=(--trace-dir ./traces)
fi
if ! arg_in_passthrough "--print-iterations"; then
    TRACE_ARGS+=(--print-iterations)
fi

DEPTH_ARGS=()
if ! arg_in_passthrough "--max-depth"; then
    DEPTH_ARGS+=(--max-depth 1)
fi

timestamp="$(date +%Y%m%d_%H%M%S)"
mkdir -p "$ARTIFACT_DIR"

case "$COMMAND" in
    index)
        echo "🚧 Running index build..."
        run_research_qa index --db "$DB_PATH" "${PASSTHROUGH_ARGS[@]}"
        ;;

    ask)
        echo "❓ Running raw ask (tracing enabled)..."
        run_research_qa ask --db "$DB_PATH" "${TRACE_ARGS[@]}" "${DEPTH_ARGS[@]}" "${maybe_question_args[@]}" "${PASSTHROUGH_ARGS[@]}"
        ;;

    basic)
        ensure_question
        verification_path="$ARTIFACT_DIR/verification.basic.${timestamp}.json"
        selected_path="$ARTIFACT_DIR/selected_docs.basic.${timestamp}.json"

        echo "🧠 Running basic preset (native mode)..."
        run_research_qa ask \
            --db "$DB_PATH" \
            --mode native \
            "${TRACE_ARGS[@]}" \
            "${DEPTH_ARGS[@]}" \
            --timeout-seconds 300 \
            --max-iterations 20 \
            --max-steps 80 \
            --save-retrieval "$selected_path" \
            --save-verification "$verification_path" \
            "${maybe_question_args[@]}" \
            "${PASSTHROUGH_ARGS[@]}"

        echo "Saved verification: $verification_path"
        echo "Saved selected docs: $selected_path"
        ;;

    fast)
        ensure_question
        verification_path="$ARTIFACT_DIR/verification.fast.${timestamp}.json"
        selected_path="$ARTIFACT_DIR/selected_docs.fast.${timestamp}.json"

        echo "⚡ Running fast preset (retrieval mode)..."
        run_research_qa ask \
            --db "$DB_PATH" \
            --mode retrieval \
            "${TRACE_ARGS[@]}" \
            "${DEPTH_ARGS[@]}" \
            --top-k 40 \
            --max-docs 30 \
            --timeout-seconds 180 \
            --max-iterations 10 \
            --max-steps 40 \
            --save-retrieval "$selected_path" \
            --save-verification "$verification_path" \
            "${maybe_question_args[@]}" \
            "${PASSTHROUGH_ARGS[@]}"

        echo "Saved verification: $verification_path"
        echo "Saved selected docs: $selected_path"
        ;;

    compare)
        ensure_question

        native_verification="$ARTIFACT_DIR/verification.native.${timestamp}.json"
        native_selected="$ARTIFACT_DIR/selected_docs.native.${timestamp}.json"
        retrieval_verification="$ARTIFACT_DIR/verification.retrieval.${timestamp}.json"
        retrieval_selected="$ARTIFACT_DIR/selected_docs.retrieval.${timestamp}.json"

        echo "🔬 Running compare preset: native"
        run_research_qa ask \
            --db "$DB_PATH" \
            --mode native \
            "${TRACE_ARGS[@]}" \
            "${DEPTH_ARGS[@]}" \
            --timeout-seconds 300 \
            --max-iterations 20 \
            --max-steps 80 \
            --save-retrieval "$native_selected" \
            --save-verification "$native_verification" \
            "${maybe_question_args[@]}" \
            "${PASSTHROUGH_ARGS[@]}"

        echo "🔬 Running compare preset: retrieval"
        run_research_qa ask \
            --db "$DB_PATH" \
            --mode retrieval \
            "${TRACE_ARGS[@]}" \
            "${DEPTH_ARGS[@]}" \
            --top-k 60 \
            --timeout-seconds 240 \
            --max-iterations 14 \
            --max-steps 60 \
            --save-retrieval "$retrieval_selected" \
            --save-verification "$retrieval_verification" \
            "${maybe_question_args[@]}" \
            "${PASSTHROUGH_ARGS[@]}"

        echo "Saved native verification: $native_verification"
        echo "Saved native selected docs: $native_selected"
        echo "Saved retrieval verification: $retrieval_verification"
        echo "Saved retrieval selected docs: $retrieval_selected"
        ;;

    *)
        echo "Unknown command: $COMMAND" >&2
        print_help
        exit 1
        ;;
esac
