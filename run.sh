#!/usr/bin/env bash
set -eo pipefail

# ==============================================================================
# Convergence Factory - Unified Runner Script
# Executes full portfolio convergence: census, AST probes, code clones,
# vector embeddings recall, pairwise LLM judge, CI/CD ratchets & OpenRewrite.
# ==============================================================================

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export PYTHONPATH="${ROOT_DIR}/src:${PYTHONPATH:-}"

# ==============================================================================
# USER CONFIGURATION (Optional - provide your settings directly below)
# ==============================================================================

# 1. Custom Repositories Directory (optional default):
#    Example: CONFIG_TARGET_DIR="/Users/mahesh/projects/my-microservices"
CONFIG_TARGET_DIR=""

# 2. LLM Configuration:
#    Set to true to force-enable LLM (or leave false to enable when endpoint/model is set)
CONFIG_ENABLE_LLM=false

#    LLM Chat/Completions Endpoint:
#    - Ollama local : "http://localhost:11434/api/generate" or "http://localhost:11434/v1/chat/completions"
#    - OpenAI cloud : "https://api.openai.com/v1/chat/completions"
#    - Azure OpenAI : "https://<resource>.openai.azure.com/openai/deployments/<model>/chat/completions?api-version=2024-02-15-preview"
#    - Groq cloud   : "https://api.groq.com/openai/v1/chat/completions"
CONFIG_LLM_ENDPOINT=""

#    LLM Model Name:
#    - Examples: "llama3.1:latest", "gpt-4o-mini", "mistral", "qwen2.5:latest"
CONFIG_LLM_MODEL=""

#    LLM API Key or Bearer Token (leave empty for local Ollama):
#    - Example: "sk-proj-..." or "Bearer ..."
CONFIG_LLM_KEY=""

# ==============================================================================

# Auto-source local .env file if present
if [[ -f "${ROOT_DIR}/.env" ]]; then
  # shellcheck disable=SC1091
  set -a
  source "${ROOT_DIR}/.env"
  set +a
fi

# Initialize defaults from direct config, environment, or fallbacks
TARGET_DIR="${CONFIG_TARGET_DIR:-${CONVERGENCE_TARGET_DIR:-}}"
OUT_DIR="${ROOT_DIR}/.factory"
ENABLE_LLM="${CONFIG_ENABLE_LLM:-false}"
LLM_ENDPOINT="${CONFIG_LLM_ENDPOINT:-${CONVERGENCE_LLM_ENDPOINT:-}}"
LLM_MODEL="${CONFIG_LLM_MODEL:-${CONVERGENCE_LLM_MODEL:-}}"
LLM_KEY="${CONFIG_LLM_KEY:-${CONVERGENCE_LLM_KEY:-${OPENAI_API_KEY:-}}}"
LLM_TIMEOUT=""
AUTO_SERVE=false

usage() {
    cat << 'HELP'
Usage: ./run.sh [REPOS_DIR] [OPTIONS]
       ./run.sh test-llm [OPTIONS]

Run the complete Convergence Factory pipeline across heterogeneous repositories.

Arguments:
  REPOS_DIR                 Path to repository folder (default: bundled fixtures/repos)

Commands:
  test-llm                  Test connection, latency, and response from configured LLM

Options:
  --all                     Run all pipeline stages (enabled by default)
  --out <dir>               Output directory for artifacts and report (default: .factory)
  --llm                     Enable live LLM pairwise judge
  --llm-endpoint <url>      LLM chat/completions endpoint (e.g. http://localhost:11434/api/generate)
  --llm-model <model>       LLM model name (e.g. llama3.1:latest, gpt-4o-mini)
  --llm-key <token>         LLM API key or Bearer token (for OpenAI, Azure, Groq)
  --llm-timeout <sec>       Timeout per LLM request in seconds (default: 60)
  --test-llm                Run the LLM connectivity and latency diagnostic
  --serve                   Automatically open and serve the interactive Redundancy Map in browser
  -h, --help                Show this help message

Examples:
  # 1. Run everything on reference portfolio:
  ./run.sh

  # 2. Test LLM connectivity and benchmark response latency:
  ./run.sh test-llm

  # 3. Run with your local Ollama model:
  ./run.sh --llm --llm-model llama3.1:latest

  # 4. Run on custom repositories folder with Cloud LLM:
  ./run.sh /path/to/my_repos --llm \
      --llm-endpoint "https://api.openai.com/v1/chat/completions" \
      --llm-model "gpt-4o-mini" \
      --llm-key "sk-proj-..."

  # 5. Run and immediately preview the visual report in your browser:
  ./run.sh --serve
HELP
    exit 0
}

ACTION="run"
ARGS=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help)
      usage
      ;;
    --all)
      shift
      ;;
    --census|census)
      ACTION="census"
      shift
      ;;
    --test-llm|test-llm)
      ACTION="test-llm"
      shift
      ;;
    --serve|serve)
      AUTO_SERVE=true
      shift
      ;;
    --out)
      OUT_DIR="$2"
      shift 2
      ;;
    --llm)
      ENABLE_LLM=true
      shift
      ;;
    --llm-endpoint)
      ENABLE_LLM=true
      LLM_ENDPOINT="$2"
      shift 2
      ;;
    --llm-model)
      ENABLE_LLM=true
      LLM_MODEL="$2"
      shift 2
      ;;
    --llm-key|--llm-api-key)
      LLM_KEY="$2"
      shift 2
      ;;
    --llm-timeout)
      LLM_TIMEOUT="$2"
      shift 2
      ;;
    *)
      if [[ -z "$TARGET_DIR" && ! "$1" =~ ^-- ]]; then
        TARGET_DIR="$1"
      else
        ARGS+=("$1")
      fi
      shift
      ;;
  esac
done

if [[ "$ACTION" == "census" ]]; then
  echo "🔍 Running Project Census..."
  if [[ -n "$TARGET_DIR" ]]; then
    echo "📂 Target Directory: ${TARGET_DIR}"
    python3 -m convergence_factory census "$TARGET_DIR" "${ARGS[@]}"
  else
    echo "📂 Target Directory: fixtures/repos (bundled fixtures)"
    python3 -m convergence_factory census "${ARGS[@]}"
  fi
  exit 0
fi

# Detect local Ollama default model if not explicitly provided
if [[ -z "$LLM_MODEL" && -z "$LLM_ENDPOINT" ]]; then
  if command -v ollama >/dev/null 2>&1 && curl -s http://localhost:11434/api/tags >/dev/null 2>&1; then
    FIRST_MODEL=$(curl -s http://localhost:11434/api/tags | grep -o '"name":"[^"]*"' | head -n 1 | cut -d'"' -f4 || true)
    if [[ -n "$FIRST_MODEL" ]]; then
      LLM_MODEL="$FIRST_MODEL"
    fi
  fi
fi

if [[ "$ACTION" == "test-llm" ]]; then
  echo "🔍 Running LLM Connectivity Diagnostic..."
  CMD=(python3 -m convergence_factory test-llm)
  if [[ -n "$LLM_ENDPOINT" ]]; then
    CMD+=(--endpoint "$LLM_ENDPOINT")
  fi
  if [[ -n "$LLM_MODEL" ]]; then
    CMD+=(--model "$LLM_MODEL")
  fi
  if [[ -n "$LLM_KEY" ]]; then
    CMD+=(--key "$LLM_KEY")
  fi
  if [[ -n "$LLM_TIMEOUT" ]]; then
    CMD+=(--timeout "$LLM_TIMEOUT")
  fi
  "${CMD[@]}" "${ARGS[@]}"
  exit $?
fi

# If environment variable or model flag is set, auto-enable LLM
if [[ -n "$LLM_ENDPOINT" || -n "$LLM_MODEL" || -n "$LLM_KEY" ]]; then
  ENABLE_LLM=true
fi

CMD=(python3 -m convergence_factory run)
if [[ -n "$TARGET_DIR" ]]; then
  CMD+=("$TARGET_DIR")
fi
CMD+=(--all --out "$OUT_DIR")

if [[ "$ENABLE_LLM" == true ]]; then
  CMD+=(--llm)
  if [[ -n "$LLM_ENDPOINT" ]]; then
    CMD+=(--llm-endpoint "$LLM_ENDPOINT")
  fi
  if [[ -n "$LLM_MODEL" ]]; then
    CMD+=(--llm-model "$LLM_MODEL")
  fi
  if [[ -n "$LLM_KEY" ]]; then
    CMD+=(--llm-api-key "$LLM_KEY")
  fi
  if [[ -n "$LLM_TIMEOUT" ]]; then
    CMD+=(--llm-timeout "$LLM_TIMEOUT")
  fi
fi

echo "🚀 Running Convergence Factory Pipeline..."
if [[ -n "$TARGET_DIR" ]]; then
  echo "📂 Target Repositories: ${TARGET_DIR}"
else
  echo "📂 Target Repositories: fixtures/repos (default reference fixtures)"
  echo "💡 Tip: To run on your own projects, pass your folder path: ./run.sh /path/to/my/projects"
fi
if [[ "$ENABLE_LLM" == true ]]; then
  echo "🤖 LLM Judge: ENABLED (Model: ${LLM_MODEL:-auto/default}, Endpoint: ${LLM_ENDPOINT:-local Ollama})"
else
  echo "🤖 LLM Judge: DISABLED (Heuristic judge active. Configure CONFIG_LLM_* in run.sh or pass --llm to enable)"
fi
echo ""
"${CMD[@]}" "${ARGS[@]}"

echo ""
echo "✅ Pipeline run complete!"
echo "📁 Artifacts written to: ${OUT_DIR}"
echo "📊 Redundancy Map site : ${OUT_DIR}/site/index.html"

if [[ "$AUTO_SERVE" == true ]]; then
  echo ""
  echo "🌐 Starting preview server..."
  python3 -m convergence_factory serve --out "$OUT_DIR"
fi
