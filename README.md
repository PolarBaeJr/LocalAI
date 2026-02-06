# Local Chat (FastAPI)

Lightweight web UI for chatting with a local LLM served by Ollama, with optional web search context. Runs fully on your machine; can expose via Cloudflare Tunnel for sharing.

## Quick Start
```bash
# One-time Cloudflare tunnel auth
cloudflared tunnel login

# Create a named tunnel (once)
cloudflared tunnel create localchat

# Create and activate env
conda create -n LocalAI python=3.10
conda activate LocalAI

# Install deps
pip install -r requirements.txt

# Start everything (ollama + cloudflared + app)
./start.sh
```
Open http://localhost:7860.

## Prerequisites
- Python 3.10+
- Conda env (recommended): `conda create -n LocalAI python=3.10`
  Activate: `conda activate LocalAI`
- Install deps: `pip install -r requirements.txt` (or `pip install fastapi uvicorn requests`)
- Ollama running locally at `http://localhost:11434` with your chosen model pulled.
- Optional search keys: set `BRAVE_API_KEY` or Google `GOOGLE_CSE_ID` + `GOOGLE_API_KEY` (env vars or edit `APIkeys.py`).

## Run locally
```bash
# Basic run (no tunnel):
python Main.py                   # binds 0.0.0.0:7860
# or with auto-reload:
uvicorn Main:app --reload --port 7860
```
Open http://localhost:7860. The assistant favicon is built-in; no static files needed.

### Recommended (start script)
```bash
./start.sh
```

## Share via Cloudflare Tunnel
```bash
brew install cloudflared         # once
cloudflared tunnel login         # once
cloudflared tunnel create localchat
```
Create `~/.cloudflared/config.yml` and map your hostname to the local app. Example:
```yaml
tunnel: <your-tunnel-id>
credentials-file: /Users/matthewcheng/.cloudflared/<your-tunnel-id>.json

ingress:
  - hostname: app.polardev.org
    service: http://localhost:7860
  - service: http_status:404
```
Then run:
```bash
cloudflared tunnel run
```
The `start.sh` script will start cloudflared automatically if configured.

## Start script commands
While `./start.sh` is running:
- Type `help` to see commands.
- `restart` to restart services.
- `stop` / `quit` / `exit` to stop and exit.
- `test-info`, `test-warn`, `test-error`, `test-all` to test log coloring.
- From another terminal: `echo test-all > /tmp/start.cmd`

## UI basics
- Chat bar is pinned to the bottom; history scrolls above.
- Attach context files (txt/pdf/docx/etc.) next to Send; they’re appended into the prompt.
- “Enable search” toggle sits in the chat bar; when on, search snippets feed the model but aren’t echoed to the user.
- Location is requested automatically for location‑related prompts (e.g., weather). GPS is stored per session.
- If GPS permission fails, search is skipped for that request.
- Avatars are fixed: user = profile icon, assistant = robot; typing shows a spinner bubble.
- Links in messages are clickable; multi-part answers stay in a single bubble.
- Debug panel is available from the `Debug` button in the header.
- Log reader is available at `/logs`.

## Configuration
- `Model.py`: set `SEARCH_TIME_BUDGET`. Ollama host + model pick in this order:
  1) `OLLAMA_HOST` env var (explicit override) → uses cloud model if pointing at `ollama.com`, else local model
  2) reachable local daemon at `http://localhost:11434` → runs `deepseek-r1:14b`
  3) cloud at `https://ollama.com` → runs `deepseek-v3.2:cloud` (needs `OLLAMA_API_KEY` in `APIkeys.py` or env)
  4) if neither endpoint is reachable, the server raises an error and logs the reason
- Debug overrides: `DebugSettings.py` or call `Debug.enable_debug_settings(force_model="cloud"|"local"|"<tag>")` to force a specific model/host choice.
- `Prompt.py`: prompt format; search results are background context only. When `SHOW_THINKING` is enabled, models are asked to wrap reasoning in `<think>...</think>`.
- `Config.py`: UI defaults (search on/off, auto-fetch, etc.) and `user_location`.
- `Main.py` env vars:
  - `HOST` (default `0.0.0.0`), `PORT` (default `7860`)
- `SHOW_THINKING=1` to request reasoning in `<think>` tags (also stored in logs and shown in UI).
- `start.sh` env vars:
  - `OLLAMA_STARTUP_WAIT_SECONDS` (default `20`)
  - `OLLAMA_BIN` (override ollama path)
  - `PYTHON_BIN` (override python path)
  - `CONDA_ENV_NAME` (default `LocalAI`)

## Development tips
- VS Code: interpreter at `.../envs/LocalAI/bin/python`; terminals as login shells so conda activates.
- For hot reload: `uvicorn Main:app --reload --port 7860`.
- Sessions persist on disk in `sessions/`; restart retains history.
- Search results are cached on disk in `SearchHistory/` and reused across sessions.

## Troubleshooting
- `fastapi` import error: ensure the `localai` env is active (`conda activate localai`) before running.
- Blank page: ensure server is on 7860; check browser console for JS errors.
- Favicon 404: already handled by `/favicon.ico` route.
- GPS: browser geolocation requires HTTPS or `http://localhost`.
