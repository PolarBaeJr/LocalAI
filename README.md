# Local Chat (FastAPI)  

Lightweight web UI for chatting with a local LLM served by Ollama, with optional web search context. Runs fully on your machine; can expose via ngrok for sharing.

## Prerequisites
- Python 3.10+
- Conda env (recommended): `conda create -n localai python=3.10`  
  Activate: `conda activate localai`
- Install deps: `pip install -r requirements.txt` (or `pip install fastapi uvicorn requests`)
- Ollama running locally at `http://localhost:11434` with your chosen model pulled.
- Optional search keys: set `BRAVE_API_KEY` or Google `GOOGLE_CSE_ID` + `GOOGLE_API_KEY` (env vars or edit `APIkeys.py`).

## Run locally
```bash
python Main.py                   # binds 0.0.0.0:7860
# or with auto-reload:
uvicorn Main:app --reload --port 7860
```
Open http://localhost:7860. The assistant favicon is built-in; no static files needed.

## Share via ngrok (no router changes)
```bash
brew install ngrok/ngrok/ngrok         # once
ngrok config add-authtoken <token>     # once
USE_NGROK=1 PORT=7860 python Main.py
```
Terminal prints both Local and Public URLs (e.g., `https://<random>.ngrok.io`). Keep the process running to keep the link alive.

## UI basics
- Chat bar is pinned to the bottom; history scrolls above.
- Attach context files (txt/pdf/docx/etc.) next to Send; they’re appended into the prompt.
- “Enable search” toggle sits in the chat bar; when on, search snippets feed the model but aren’t echoed to the user.
- Avatars are fixed: user = profile icon, assistant = robot; typing shows a spinner bubble.
- Links in messages are clickable; multi-part answers stay in a single bubble.

## Configuration
- `Model.py`: set `MODEL`, `OLLAMA_URL`, `SEARCH_TIME_BUDGET`.
- `Config.py`: UI defaults (search on/off, auto-fetch, etc.).
- `Prompt.py`: prompt format; search results are used as background context only.
- `Main.py` env vars:
  - `HOST` (default `0.0.0.0`), `PORT` (default `7860`)
  - `USE_NGROK=1` to auto-tunnel and print public URL

## Development tips
- VS Code: interpreter at `.../envs/localai/bin/python`; terminals as login shells so conda activates.
- For hot reload: `uvicorn Main:app --reload --port 7860`.
- State is in-memory; restart clears history.

## Troubleshooting
- `fastapi` import error: ensure the `localai` env is active (`conda activate localai`) before running.
- Blank page: ensure server is on 7860; check browser console for JS errors.
- Favicon 404: already handled by `/favicon.ico` route.
