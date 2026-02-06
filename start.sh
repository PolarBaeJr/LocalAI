#!/usr/bin/env bash

if [ -z "${BASH_VERSION:-}" ]; then
  exec bash "$0" "$@"
fi

# Start Cloudflare tunnel, Ollama, and the FastAPI server together.
# Uses existing Cloudflare config at ~/.cloudflared/config.yml
# Streams output to this terminal and also tees to /tmp/*.log. Exits when any process stops.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="$ROOT_DIR/Logs/run_active"
mkdir -p "$LOG_DIR"

# Encourage ANSI colors in child processes.
export TERM="${TERM:-xterm-256color}"
export CLICOLOR_FORCE=1
export FORCE_COLOR=1
unset NO_COLOR

# Optional conda environment for launching services.
CONDA_ENV_NAME="${CONDA_ENV_NAME:-LocalAI}"
CONDA_RUN=""
if command -v conda >/dev/null 2>&1; then
  CONDA_RUN="conda run -n ${CONDA_ENV_NAME} --no-capture-output"
fi
# Default to empty prefix so set -u doesn't choke.
BUFFER_PREFIX=""

# Choose a line-buffer helper if available.
if command -v stdbuf >/dev/null 2>&1; then
  BUFFER_PREFIX="stdbuf -oL -eL "
elif command -v unbuffer >/dev/null 2>&1; then
  BUFFER_PREFIX="unbuffer "
else
  BUFFER_PREFIX=""
fi

prefix_tee() {
  local tag="$1"
  local log_a="$2"
  local log_b="$3"
  python -u -c 'import sys
tag, log_a, log_b = sys.argv[1:4]
f1 = open(log_a, "a", buffering=1, encoding="utf-8", errors="ignore")
f2 = open(log_b, "a", buffering=1, encoding="utf-8", errors="ignore")
COLORS = {"CLOUDFLARED":"\033[36m","OLLAMA":"\033[35m","APP":"\033[33m"}
WARN_COLOR = "\033[31m"
ERR_COLOR = "\033[31;2m"
color = COLORS.get(tag, "")
reset = "\033[0m"
def emit(line: str) -> None:
    if not line.endswith("\n"):
        line += "\n"
    f1.write(line); f2.write(line)
    upper = line.upper()
    if "ERROR" in upper or "ERR" in upper:
        prefix_color = ERR_COLOR
    elif "WARN" in upper or "WARNING" in upper:
        prefix_color = WARN_COLOR
    else:
        prefix_color = color
    sys.stdout.write(f"{prefix_color}[{tag}]{reset} " + line)
    sys.stdout.flush()
for raw in sys.stdin:
    raw = raw.replace("\r\n", "\n").replace("\r", "\n")
    for part in raw.splitlines(True):
        emit(part.rstrip("\n"))' "$tag" "$log_a" "$log_b"
}

emit_test_line() {
  local tag="$1"
  shift
  local text="$*"
  printf "%s\n" "$text" | prefix_tee "$tag" /dev/null /dev/null
}

run_with_prefix() {
  local name="$1"
  local log_a="$2"
  local log_b="$3"
  local use_conda="$4"
  shift 4
  local cmd="$*"
  if [[ "${use_conda}" == "1" && -n "${CONDA_RUN}" ]]; then
    eval "${BUFFER_PREFIX}${CONDA_RUN} ${cmd}" 2>&1 | prefix_tee "$name" "$log_a" "$log_b" &
  else
    eval "${BUFFER_PREFIX}${cmd}" 2>&1 | prefix_tee "$name" "$log_a" "$log_b" &
  fi
  PIDS+=("$!")
}

start_tail() {
  local name="$1"
  local src="$2"
  local dest="$3"
  tail -n 0 -F "$src" 2>/dev/null \
    | tee -a "$dest" \
    | awk -v p="$name" '{printf("[%s] %s\n", p, $0); fflush()}' &
  TAIL_PIDS+=("$!")
}

PIDS=()
TAIL_PIDS=()

cleanup() {
  log "Stopping services..."
  for pid in "${TAIL_PIDS[@]:-}"; do
    if kill -0 "$pid" >/dev/null 2>&1; then
      kill "$pid" >/dev/null 2>&1 || true
    fi
  done
  for pid in "${PIDS[@]:-}"; do
    if kill -0 "$pid" >/dev/null 2>&1; then
      kill "$pid" >/dev/null 2>&1 || true
    fi
  done
  wait >/dev/null 2>&1 || true
  log "All services stopped."
  exit 0
}

trap 'stop_services; log "All services stopped. Exiting."; exit 0' INT TERM
trap cleanup ERR

stop_services() {
  log "Stopping services..."
  for pid in "${TAIL_PIDS[@]:-}"; do
    if kill -0 "$pid" >/dev/null 2>&1; then
      kill "$pid" >/dev/null 2>&1 || true
    fi
  done
  TAIL_PIDS=()
  if [[ -d "$ROOT_DIR/Logs/run_active" && ! -f "$ROOT_DIR/Logs/run_active/session_end.txt" ]]; then
    printf "Session ended at %sZ\nReason: Restarted\n" "$(date -u +"%Y-%m-%dT%H:%M:%S")" \
      > "$ROOT_DIR/Logs/run_active/session_end.txt" || true
  fi
  pkill -x cloudflared >/dev/null 2>&1 || true
  pkill -x ollama >/dev/null 2>&1 || true
  pkill -f "python Main.py" >/dev/null 2>&1 || true
  sleep 1
  log "Services stopped."
}

log () { printf "[%s] %s\n" "$(date -u +"%Y-%m-%dT%H:%M:%SZ")" "$*"; }

# Start cloudflared tunnel if not already running
start_cloudflare() {
  if pgrep -x cloudflared >/dev/null 2>&1; then
    log "cloudflared already running"
    return
  fi
  if [[ ! -f "$HOME/.cloudflared/config.yml" ]]; then
    log "No ~/.cloudflared/config.yml found; skipping tunnel start."
    return 1
  fi
  log "Starting cloudflared tunnel (stream + /tmp/cloudflared.log + $LOG_DIR/cloudflared.log)"
  run_with_prefix "CLOUDFLARED" /tmp/cloudflared.log "$LOG_DIR/cloudflared.log" 0 \
    cloudflared tunnel --config "$HOME/.cloudflared/config.yml" run
}

# Start Ollama serve if not already running
start_ollama() {
  local ollama_bin="${OLLAMA_BIN:-/Users/matthewcheng/miniforge3/envs/LocalAI/bin/ollama}"
  if [[ ! -x "$ollama_bin" ]]; then
    if command -v ollama >/dev/null 2>&1; then
      ollama_bin="$(command -v ollama)"
    fi
  fi
  if [[ ! -x "$ollama_bin" ]]; then
    log "ollama not found. Set OLLAMA_BIN or fix PATH."
    return 1
  fi
  log "Using ollama binary: $ollama_bin"
  if pgrep -x ollama >/dev/null 2>&1; then
    log "ollama already running"
    return
  fi
  log "Starting ollama serve (stream + /tmp/ollama.log + $LOG_DIR/ollama.log)"
  "$ollama_bin" serve >> /tmp/ollama.log 2>&1 &
  PIDS+=("$!")
  # Stream ollama log to terminal and run_active separately to avoid buffering issues.
  start_tail "OLLAMA" /tmp/ollama.log "$LOG_DIR/ollama.log"
  # Defer readiness checks to wait_for_ollama.
  return 0
}

# Wait for Ollama HTTP endpoint to respond before starting the app.
wait_for_ollama() {
  local url_primary="http://127.0.0.1:11434/api/version"
  local url_fallback="http://localhost:11434/api/version"
  local log_file="/tmp/ollama.log"
  local max_wait="${OLLAMA_STARTUP_WAIT_SECONDS:-20}"
  local start_ts
  start_ts="$(date +%s)"
  log "Waiting for Ollama to be ready (up to ${max_wait}s)..."
  while true; do
    if curl -s "$url_primary" >/dev/null 2>&1 || curl -s "$url_fallback" >/dev/null 2>&1; then
      log "Ollama is ready."
      return 0
    fi
    if [[ -f "$log_file" ]] && rg -q "Listening on .*:11434" "$log_file" 2>/dev/null; then
      log "Ollama reported ready in logs."
      return 0
    fi
    local now
    now="$(date +%s)"
    local elapsed=$((now - start_ts))
    if (( elapsed >= max_wait )); then
      log "Ollama is not ready after ${max_wait}s."
      log "Exiting."
      exit 1
    fi
    log "Ollama not ready yet... ${elapsed}s"
    sleep 1
  done
}

# Start the FastAPI app
start_app() {
  local port="${PORT:-7860}"
  local py_bin="${PYTHON_BIN:-/Users/matthewcheng/miniforge3/envs/LocalAI/bin/python}"
  if pgrep -f "python Main.py" >/dev/null 2>&1; then
    log "Main.py already running"
    return
  fi
  if lsof -n -iTCP:"${port}" -sTCP:LISTEN >/dev/null 2>&1; then
    log "Port ${port} already in use; stopping existing listener."
    lsof -n -iTCP:"${port}" -sTCP:LISTEN -t | xargs -r kill >/dev/null 2>&1 || true
    sleep 1
  fi
  log "Starting FastAPI server (stream + /tmp/localchat.log + $LOG_DIR/localchat.log)"
  cd "$ROOT_DIR"
  if [[ ! -x "$py_bin" ]]; then
    if command -v python >/dev/null 2>&1; then
      py_bin="$(command -v python)"
    fi
  fi
  if [[ ! -x "$py_bin" ]]; then
    log "python not found. Set PYTHON_BIN or fix PATH."
    return 1
  fi
  log "Using python binary: $py_bin"
  "$py_bin" -u Main.py >> /tmp/localchat.log 2>&1 &
  PIDS+=("$!")
  start_tail "APP" /tmp/localchat.log "$LOG_DIR/localchat.log"
  for _ in {1..5}; do
    if curl -s "http://127.0.0.1:${port}/" >/dev/null 2>&1; then
      log "Main.py started successfully."
      return 0
    fi
    sleep 1
  done
  log "Main.py failed to start (no HTTP response). Check /tmp/localchat.log."
  return 1
}

start_stack() {
  start_cloudflare
  start_ollama
  wait_for_ollama
  start_app
  # Log tailing no longer needed; output is already prefixed and flushed.
}

if [[ "${1:-}" == "restart" ]]; then
  stop_services
fi

start_stack

log "All services launched (cloudflared, ollama, Main.py)."
log "Type 'restart' to restart services, 'stop' to stop and exit, or Ctrl+C to stop all."

while true; do
  if ! read -r -t 1 cmd; then
    # Check for file-based commands.
    if [[ -f /tmp/start.cmd ]]; then
      cmd="$(cat /tmp/start.cmd)"
      : > /tmp/start.cmd
    else
      continue
    fi
  fi
  if [[ -z "${cmd}" ]]; then
    continue
  fi
  cmd="${cmd%%$'\r'}"
  cmd="$(echo "$cmd" | xargs)"
  if [[ -z "${cmd}" ]]; then
    continue
  fi
  log "Command received: ${cmd}"
  if [[ "${cmd}" == "help" ]]; then
    log "Commands: restart | stop/quit/exit | test-info | test-warn | test-error | test-all"
    log "Also supports file trigger: echo test-all > /tmp/start.cmd"
    continue
  fi
  case "${cmd}" in
    restart)
      stop_services
      start_stack
      log "Restart complete."
      ;;
    test-info)
      emit_test_line "APP" "INFO: Test info message"
      ;;
    test-warn)
      emit_test_line "APP" "WARNING: Test warning message"
      ;;
    test-error)
      emit_test_line "APP" "ERROR: Test error message"
      ;;
    test-all)
      emit_test_line "CLOUDFLARED" "INFO: Cloudflared test message"
      emit_test_line "OLLAMA" "INFO: Ollama test message"
      emit_test_line "APP" "INFO: App test message"
      emit_test_line "APP" "WARNING: App test warning"
      emit_test_line "APP" "ERROR: App test error"
      ;;
    stop|quit|exit)
      stop_services
      log "All services stopped. Exiting."
      exit 0
      ;;
    "")
      ;;
    *)
      log "Unknown command: ${cmd}"
      ;;
  esac
done
