# Local Chat (FastAPI)

Lightweight local chat UI that talks to an Ollama-served model, with optional web search context.

## Features
- Custom HTML/CSS front-end (no NiceGUI); streams tokens from the server.
- File uploads are appended into the prompt for extra context.
- Optional Brave/Google/DuckDuckGo search results included in the model prompt.
- Session-based state kept in memory per `session_id`.

## Requirements
- Python 3.10+
- `fastapi`, `uvicorn`, `requests` (install via `pip install -r requirements.txt` or `pip install fastapi uvicorn requests`)
- Running Ollama endpoint at `http://localhost:11434/api/generate`
- (Optional) Brave search key: set `BRAVE_API_KEY` or place it in `APIkeys.py`
- (Optional) Google CSE: set `GOOGLE_CSE_ID` and `GOOGLE_API_KEY`

## Run
```bash
python Main.py
# or
uvicorn Main:app --reload --port 7860
```
Open http://localhost:7860 in a browser.

## Configuration
- Defaults: search on, auto-fetch top result off, file context empty. Override in `Config.py`.
- Model/endpoint/time budget: tweak `MODEL`, `OLLAMA_URL`, `SEARCH_TIME_BUDGET` in `Model.py`.

## Usage
1) Toggle “Enable search” if you want web snippets in context.  
2) Attach files (txt/pdf/docx/etc.)—they’re concatenated into the prompt.  
3) Type a message and send; streaming tokens appear live.  
4) Reasoning blocks in `<think>...</think>` are split from the final answer when present.

## Notes
- `index.html` is generated automatically if missing; feel free to edit it for layout/styles.  
- `UI.py` (NiceGUI) is now unused; keep or delete as you prefer.  
- State is in-memory; restarting the server clears history.  
- Logs/timings are tracked in the session debug fields (`Debug.py`).
