#!/usr/bin/env bash
set -eo pipefail

# ==============================================================================
# Convergence Factory - Unified Runner Script
# Executes full portfolio convergence: census, AST probes, code clones,
# vector embeddings recall, pairwise LLM judge, CI/CD ratchets & OpenRewrite.
# ==============================================================================

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export PYTHONPATH="${ROOT_DIR}/src:${PYTHONPATH:-}"

# Defaults
TARGET_DIR=""
OUT_DIR="${ROOT_DIR}/.factory"
ENABLE_LLM=false
LLM_ENDPOINT="${CONVERGENCE_LLM_ENDPOINT:-}"
LLM_MODEL="${CONVERGENCE_LLM_MODEL:-}"
LLM_KEY="${CONVERGENCE_LLM_KEY:-${OPENAI_API_KEY:-}}"
AUTO_SERVE=false

usage() {
    cat << 'HELP'
Usage: ./run.sh [REPOS_DIR] [OPTIONS]

Run the complete Convergence Factory pipeline across heterogeneous repositories.

Arguments:
  REPOS_DIR                 Path to repository folder (default: bundled fixtures/repos)

Options:
  --all                     Run all pipeline stages (enabled by default)
  --out <dir>               Output directory for artifacts and report (default: .factory)
  --llm                     Enable live LLM pairwise judge
  --llm-endpoint <url>      LLM chat/completions endpoint (e.g. http://localhost:11434/api/generate)
  --llm-model <model>       LLM model name (e.g. llama3.1:latest, gpt-4o-mini)
  --llm-key <token>         LLM API key or Bearer token (for OpenAI, Azure, Groq)
  --serve                   Automatically open and serve the interactive Redundancy Map in browser
  -h, --help                Show this help message

Examples:
  # 1. Run everything on reference portfolio:
  ./run.sh

  # 2. Run with your local Ollama model:
  ./run.sh --llm --llm-model llama3.1:latest

  # 3. Run on custom repositories folder with Cloud LLM:
  ./run.sh /path/to/my_repos --llm \
      --llm-endpoint "https://api.openai.com/v1/chat/completions" \
      --llm-model "gpt-4o-mini" \
      --llm-key "sk-proj-..."

  # 4. Run and immediately preview the visual report in your browser:
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

# If environment variable or model flag is set, auto-enable LLM
if [[ -n "$LLM_ENDPOINT" || -n "$LLM_MODEL" || -n "$LLM_KEY" ]]; then
  ENABLE_LLM=true
fi

# Detect local Ollama default model if --llm passed without explicit model
if [[ "$ENABLE_LLM" == true && -z "$LLM_MODEL" && -z "$LLM_ENDPOINT" ]]; then
  if command -v ollama >/dev/null 2>&1 && curl -s http://localhost:11434/api/tags >/dev/null 2>&1; then
    FIRST_MODEL=$(curl -s http://localhost:11434/api/tags | grep -o '"name":"[^"]*"' | head -n 1 | cut -d'"' -f4 || true)
    if [[ -n "$FIRST_MODEL" ]]; then
      LLM_MODEL="$FIRST_MODEL"
      echo "🤖 Auto-detected local Ollama model: ${LLM_MODEL}"
    fi
  fi
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
fi

echo "🚀 Running Convergence Factory Pipeline..."
if [[ -n "$TARGET_DIR" ]]; then
  echo "📂 Target Repositories: ${TARGET_DIR}"
else
  echo "📂 Target Repositories: fixtures/repos (default reference fixtures)"
  echo "💡 Tip: To run on your own projects, pass your folder path: ./run.sh /path/to/my/projects"
fi
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
