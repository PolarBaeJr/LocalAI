import asyncio
import json
import os
import shutil
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional

import requests
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, StreamingResponse, Response

from Prompt import build_prompt, build_chat_context
from Debug import (
    init_debug,
    set_prompt,
    attach_state,
)
from Model import OLLAMA_URL, MODEL, SEARCH_TIME_BUDGET
from Config import apply_defaults
from logic import split_thinking, gather_context
from uiconfig import HTML_TEMPLATE, ensure_html_exists

app = FastAPI()

# Simple in-memory session storage; keyed by client-provided session_id.
STATE: Dict[str, dict] = {}


def get_state(session_id: str) -> dict:
    if not session_id:
        raise HTTPException(status_code=400, detail="session_id is required")
    state = STATE.setdefault(session_id, {})
    apply_defaults(state)
    return state


@app.get("/favicon.ico", include_in_schema=False)
async def favicon() -> Response:
    """Serve a lightweight embedded favicon to avoid 404s."""
    svg = """<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'>
<circle cx='32' cy='32' r='30' fill='#0c98c7' stroke='#0b1d30' stroke-width='4'/>
<circle cx='32' cy='26' r='10' fill='#0b1d30'/>
<path d='M16 52c4-14 14-18 16-18s12 4 16 18' fill='#0b1d30'/>
</svg>"""
    return Response(content=svg, media_type="image/svg+xml")


@app.get("/", response_class=HTMLResponse)
async def index() -> HTMLResponse:
    """Serve the lightweight HTML shell."""
    ensure_html_exists()
    return HTMLResponse(HTML_TEMPLATE.read_text(encoding="utf-8"))


@app.get("/api/history")
async def history(session_id: str):
    state = get_state(session_id)
    attach_state(state)
    return {"history": state["history"]}


@app.post("/api/upload")
async def upload_files(
    session_id: str = Form(...), files: List[UploadFile] = File(...)
):
    state = get_state(session_id)
    attach_state(state)
    count = 0
    for file in files:
        content = await file.read()
        text = content.decode("utf-8", errors="ignore")
        state["file_context"] += f"FILE {file.filename}:\n{text.strip()}\n\n"
        count += 1
    file_count = len(
        [chunk for chunk in state["file_context"].split("FILE ") if chunk.strip()]
    )
    return {"loaded_files": count, "total_files": file_count}


@app.post("/api/send")
async def send(request: Request):
    payload = await request.json()
    prompt: str = (payload.get("prompt") or "").strip()
    session_id: str = payload.get("session_id") or ""
    use_search: bool = bool(payload.get("use_search", False))

    if not prompt:
        raise HTTPException(status_code=400, detail="prompt is required")

    state = get_state(session_id)
    attach_state(state)
    init_debug(state)
    state["use_search"] = use_search
    state["auto_fetch_top_result"] = use_search

    state["history"].append(("user", prompt))

    deadline = time.monotonic() + SEARCH_TIME_BUDGET
    search_context, web_context, timed_out, search_error = gather_context(
        prompt, "", deadline
    )

    chat_context = build_chat_context(state["history"])
    full_prompt = build_prompt(
        state.get("file_context", ""), search_context, web_context, chat_context
    )
    set_prompt(full_prompt)

    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()
    acc_parts: List[str] = []

    def model_worker():
        try:
            with requests.post(
                OLLAMA_URL,
                json={"model": MODEL, "prompt": full_prompt, "stream": True},
                stream=True,
                timeout=300,
            ) as r:
                r.raise_for_status()
                for line in r.iter_lines(decode_unicode=True):
                    if not line:
                        continue
                    data = json.loads(line)
                    chunk = data.get("response", "")
                    if chunk:
                        acc_parts.append(chunk)
                        asyncio.run_coroutine_threadsafe(
                            queue.put({"type": "token", "text": chunk}), loop
                        )
                    if data.get("done"):
                        break
        except Exception as e:  # noqa: BLE001
            asyncio.run_coroutine_threadsafe(
                queue.put({"type": "error", "text": str(e)}), loop
            )
        finally:
            asyncio.run_coroutine_threadsafe(queue.put({"type": "end"}), loop)

    threading.Thread(target=model_worker, daemon=True).start()

    async def event_stream():
        if search_error:
            yield json.dumps(
                {
                    "type": "notice",
                    "text": f"Search unavailable: {search_error}",
                }
            ) + "\n"
        if timed_out:
            yield json.dumps(
                {
                    "type": "notice",
                    "text": f"Search/fetch capped at {SEARCH_TIME_BUDGET // 60} minute(s).",
                }
            ) + "\n"

        while True:
            item = await queue.get()
            if item["type"] == "token":
                yield json.dumps(item) + "\n"
            elif item["type"] == "error":
                yield json.dumps(item) + "\n"
                break
            elif item["type"] == "end":
                acc = "".join(acc_parts)
                thinking, answer, has_thinking = split_thinking(acc)
                state["history"].append(("assistant", acc))
                meta = {
                    "type": "final",
                    "raw": acc,
                    "answer": answer if has_thinking else acc,
                    "thinking": thinking,
                }
                yield json.dumps(meta) + "\n"
                break

    return StreamingResponse(event_stream(), media_type="text/plain")


if not HTML_TEMPLATE.exists():
    ensure_html_exists()


def _start_ngrok(port: int) -> Optional[str]:
    """
    Optionally start an ngrok tunnel if USE_NGROK=1 and ngrok is installed.
    Returns the public URL or None.
    """
    if os.environ.get("USE_NGROK", "0") != "1":
        return None
    if not shutil.which("ngrok"):
        print("USE_NGROK=1 set but no ngrok binary found on PATH")
        return None
    # Launch ngrok in the background
    threading.Thread(
        target=lambda: os.system(f"ngrok http {port} > /tmp/ngrok.log 2>&1"),
        daemon=True,
    ).start()
    # Poll the ngrok API for the public URL
    for _ in range(20):
        try:
            resp = requests.get("http://127.0.0.1:4040/api/tunnels", timeout=1.5)
            data = resp.json()
            tunnels = data.get("tunnels", [])
            if tunnels:
                return tunnels[0].get("public_url")
        except Exception:
            pass
        time.sleep(0.5)
    print("ngrok started but no public URL found (check /tmp/ngrok.log)")
    return None


if __name__ in {"__main__", "__mp_main__"}:
    import uvicorn  # type: ignore

    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "7860"))

    public_url = _start_ngrok(port)
    print("=== Local Chat endpoints ===")
    print(f"Local:  http://localhost:{port}")
    if public_url:
        print(f"Public: {public_url}  (via ngrok)")
    else:
        print("Public: disabled (set USE_NGROK=1 with ngrok installed to expose)")
    print("============================")
    uvicorn.run(app, host=host, port=port)
