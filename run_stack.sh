#!/usr/bin/env bash

# Start Cloudflare tunnel, Ollama, and the FastAPI server together.
# Uses existing Cloudflare config at ~/.cloudflared/config.yml
# Streams output to this terminal and also tees to /tmp/*.log. Exits when any process stops.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="$ROOT_DIR/Logs/run_active"
mkdir -p "$LOG_DIR"

# Choose a line-buffer helper if available.
if command -v stdbuf >/dev/null 2>&1; then
  BUFFER_CMD=(stdbuf -oL -eL)
elif command -v unbuffer >/dev/null 2>&1; then
  BUFFER_CMD=(unbuffer)
else
  BUFFER_CMD=()
fi

PIDS=()

cleanup() {
  log "Stopping services..."
  for pid in "${PIDS[@]:-}"; do
    if kill -0 "$pid" >/dev/null 2>&1; then
      kill "$pid" >/dev/null 2>&1 || true
    fi
  done
  wait >/dev/null 2>&1 || true
  log "All services stopped."
  exit 0
}

trap cleanup INT TERM

log () { printf "[%s] %s\n" "$(date -u +"%Y-%m-%dT%H:%M:%SZ")" "$*"; }

# Start cloudflared tunnel if not already running
start_cloudflare() {
  if pgrep -x cloudflared >/dev/null; then
    log "cloudflared already running"
    return
  fi
  if [[ ! -f "$HOME/.cloudflared/config.yml" ]]; then
    log "No ~/.cloudflared/config.yml found; skipping tunnel start."
    return
  fi
  log "Starting cloudflared tunnel (stream + /tmp/cloudflared.log + $LOG_DIR/cloudflared.log)"
  "${BUFFER_CMD[@]}" cloudflared tunnel --config "$HOME/.cloudflared/config.yml" run \
    | tee /tmp/cloudflared.log "$LOG_DIR/cloudflared.log" &
  PIDS+=("$!")
}

# Start Ollama serve if not already running
start_ollama() {
  if pgrep -x ollama >/dev/null; then
    log "ollama already running"
    return
  fi
  log "Starting ollama serve (stream + /tmp/ollama.log + $LOG_DIR/ollama.log)"
  "${BUFFER_CMD[@]}" ollama serve | tee /tmp/ollama.log "$LOG_DIR/ollama.log" &
  PIDS+=("$!")
}

# Start the FastAPI app
start_app() {
  if pgrep -f "python Main.py" >/dev/null; then
    log "Main.py already running"
    return
  fi
  log "Starting FastAPI server (stream + /tmp/localchat.log + $LOG_DIR/localchat.log)"
  cd "$ROOT_DIR"
  python -u Main.py | tee /tmp/localchat.log "$LOG_DIR/localchat.log" &
  PIDS+=("$!")
}

start_cloudflare
start_ollama
start_app

log "All services launched (cloudflared, ollama, Main.py). Output streaming below. Ctrl+C to stop all."
wait
