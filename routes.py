import asyncio
import json
import threading
import time
from typing import List

import requests
from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, StreamingResponse, Response

from Prompt import build_prompt, build_chat_context
from Debug import (
    init_debug,
    set_prompt,
    attach_state,
    dbg,
    add_error,
    add_timing,
    set_debug,
)
from Model import SEARCH_TIME_BUDGET, get_ollama_endpoint
from logic import split_thinking, gather_context
from uiconfig import HTML_TEMPLATE, ensure_html_exists
from sid_create import (
    get_state,
    save_session,
    list_session_ids,
    delete_session as delete_session_store,
    create_session,
)
import uuid

router = APIRouter()


@router.get("/favicon.ico", include_in_schema=False)
async def favicon() -> Response:
    """Serve a lightweight embedded favicon to avoid 404s."""
    svg = """<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'>
<circle cx='32' cy='32' r='30' fill='#0c98c7' stroke='#0b1d30' stroke-width='4'/>
<circle cx='32' cy='26' r='10' fill='#0b1d30'/>
<path d='M16 52c4-14 14-18 16-18s12 4 16 18' fill='#0b1d30'/>
</svg>"""
    return Response(content=svg, media_type="image/svg+xml")


@router.get("/", response_class=HTMLResponse)
async def index() -> HTMLResponse:
    """Serve the lightweight HTML shell."""
    ensure_html_exists()
    return HTMLResponse(HTML_TEMPLATE.read_text(encoding="utf-8"))


@router.get("/api/sessions")
async def list_sessions():
    """List known session IDs (from disk + in-memory)."""
    return {"sessions": list_session_ids()}


@router.post("/api/sessions")
async def create_session_endpoint():
    """Create and persist a new session, returning its ID."""
    sid = create_session()
    return {"session_id": sid}


@router.delete("/api/sessions/{session_id}")
async def delete_session(session_id: str):
    """Delete a session from memory and disk."""
    sid = delete_session_store(session_id)
    return {"deleted": sid}


@router.get("/api/history")
async def history(session_id: str):
    state = get_state(session_id)
    attach_state(state)
    dbg(f"History requested for session {session_id}")
    return {"history": state["history"]}


@router.post("/api/upload")
async def upload_files(
    session_id: str = Form(...), files: List[UploadFile] = File(...)
):
    state = get_state(session_id)
    attach_state(state)
    dbg(f"Upload received: {len(files)} files for session {session_id}")
    count = 0
    for file in files:
        content = await file.read()
        text = content.decode("utf-8", errors="ignore")
        state["file_context"] += f"FILE {file.filename}:\n{text.strip()}\n\n"
        count += 1
    file_count = len(
        [chunk for chunk in state["file_context"].split("FILE ") if chunk.strip()]
    )
    save_session(session_id, state)
    return {"loaded_files": count, "total_files": file_count}


@router.post("/api/send")
async def send(request: Request):
    payload = await request.json()
    prompt: str = (payload.get("prompt") or "").strip()
    session_id: str = payload.get("session_id") or ""
    use_search: bool = bool(payload.get("use_search", False))
    location = payload.get("location")
    location_failed = bool(payload.get("location_failed", False))

    if not prompt:
        raise HTTPException(status_code=400, detail="prompt is required")

    state = get_state(session_id)
    attach_state(state)
    init_debug(state)
    dbg(f"Send called session={session_id} prompt_len={len(prompt)} use_search={use_search}")
    if location_failed:
        use_search = False
    state["use_search"] = use_search
    state["auto_fetch_top_result"] = use_search
    if isinstance(location, dict) and location.get("lat") is not None and location.get("lon") is not None:
        state["user_location"] = location
    elif location is None:
        # Keep existing location unless explicitly cleared.
        pass
    else:
        state["user_location"] = None

    state["history"].append(("user", prompt))
    save_session(session_id, state)

    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()
    acc_parts: List[str] = []

    def push_status(text: str):
        asyncio.run_coroutine_threadsafe(
            queue.put({"type": "status", "text": text}), loop
        )

    push_status("Preparing request…")
    if use_search:
        push_status("Searching for data…")
    else:
        push_status("Skipping search; compiling context…")

    deadline = time.monotonic() + SEARCH_TIME_BUDGET
    search_context, web_context, timed_out, search_error = gather_context(
        prompt, "", deadline
    )
    set_debug("search_error", search_error)
    if search_error:
        add_error(search_error)
    if timed_out:
        dbg("Search timed out before completion")
    push_status("Building prompt…")

    chat_context = build_chat_context(state["history"])
    file_ctx = state.get("file_context", "")
    loc = state.get("user_location") or {}
    location_ctx = ""
    if isinstance(loc, dict) and loc.get("lat") is not None and loc.get("lon") is not None:
        parts = [f"lat={loc.get('lat')}", f"lon={loc.get('lon')}"]
        if loc.get("accuracy") is not None:
            parts.append(f"accuracy_m={loc.get('accuracy')}")
        if loc.get("timestamp"):
            parts.append(f"timestamp={loc.get('timestamp')}")
        location_ctx = "USER LOCATION: " + ", ".join(parts)
    if location_ctx:
        file_ctx = f"{location_ctx}\n\n{file_ctx}" if file_ctx else location_ctx

    full_prompt = build_prompt(
        file_ctx, search_context, web_context, chat_context
    )
    set_prompt(full_prompt)

    def model_worker():
        try:
            generate_url, headers, model = get_ollama_endpoint()
            dbg(f"Streaming request to model={model} url={generate_url}")
            push_status("Generating response…")
            with requests.post(
                generate_url,
                json={"model": model, "prompt": full_prompt, "stream": True},
                stream=True,
                timeout=300,
                headers=headers,
            ) as r:
                r.raise_for_status()
                for line in r.iter_lines(decode_unicode=True):
                    if not line:
                        continue
                    data = json.loads(line)
                    chunk = data.get("response", "")
                    if chunk:
                        acc_parts.append(chunk)
                        if len(acc_parts) % 50 == 0:
                            dbg(f"Streaming progress: {len(acc_parts)} chunks")
                        asyncio.run_coroutine_threadsafe(
                            queue.put({"type": "token", "text": chunk}), loop
                        )
                    if data.get("done"):
                        break
        except Exception as e:  # noqa: BLE001
            asyncio.run_coroutine_threadsafe(
                queue.put({"type": "error", "text": str(e)}), loop
            )
            add_error(str(e))
        finally:
            push_status("Finalizing output…")
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
                dbg(f"Model worker error: {item['text']}")
                push_status("Model error; see logs")
                yield json.dumps(item) + "\n"
                break
            elif item["type"] == "end":
                acc = "".join(acc_parts)
                thinking, answer, has_thinking = split_thinking(acc)
                if has_thinking:
                    set_debug("model_thinking", thinking)
                    dbg(f"Model thinking captured ({len(thinking)} chars)")
                state["history"].append(("assistant", acc))
                save_session(session_id, state)
                dbg("Streaming finished; response saved to history")
                push_status("Done")
                meta = {
                    "type": "final",
                    "raw": acc,
                    "answer": answer if has_thinking else acc,
                    "thinking": thinking,
                }
                yield json.dumps(meta) + "\n"
                break

    return StreamingResponse(event_stream(), media_type="text/plain")
