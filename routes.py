import asyncio
import json
import threading
import time
from typing import List

import requests
from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from io import BytesIO
from pathlib import Path
import uuid
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
from logreader import read_log as read_log_api
from sid_create import (
    get_state,
    save_session,
    list_session_ids,
    delete_session as delete_session_store,
    create_session,
)

router = APIRouter()
UPLOADS_DIR = Path(__file__).with_name("uploads")
UPLOADS_DIR.mkdir(exist_ok=True)


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


@router.get("/api/debug")
async def debug_panel(session_id: str):
    state = get_state(session_id)
    attach_state(state)
    dbg(f"Debug requested for session {session_id}")
    return {
        "dbg_log": state.get("dbg_log", []),
        "dbg_errors": state.get("dbg_errors", []),
        "dbg_timings": state.get("dbg_timings", []),
        "dbg_fetches": state.get("dbg_fetches", []),
        "dbg_evidence": state.get("dbg_evidence", ""),
        "dbg_prompt": state.get("dbg_prompt", ""),
        "dbg_data": state.get("dbg_data", {}),
    }


@router.get("/api/index_mtime")
async def index_mtime():
    try:
        ensure_html_exists()
        path = Path(__file__).with_name("index.html")
        if not path.exists():
            return {"mtime": 0}
        return {"mtime": path.stat().st_mtime}
    except Exception:  # noqa: BLE001
        return {"mtime": 0}


@router.get("/api/index_watch")
async def index_watch():
    async def event_stream():
        ensure_html_exists()
        path = Path(__file__).with_name("index.html")
        last_mtime = 0.0
        while True:
            try:
                mtime = path.stat().st_mtime if path.exists() else 0.0
                if not last_mtime:
                    last_mtime = mtime
                elif mtime and mtime > last_mtime:
                    last_mtime = mtime
                    yield f"data: {json.dumps({'mtime': mtime})}\n\n"
                await asyncio.sleep(0.5)
            except Exception:  # noqa: BLE001
                await asyncio.sleep(1.0)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


# Compatibility route for cached logreader clients (pre-/logs/api change).
@router.get("/api/logs/{name}")
async def logs_compat(name: str):
    return await read_log_api(name)


@router.post("/api/upload")
async def upload_files(
    session_id: str = Form(...), files: List[UploadFile] = File(...)
):
    def sanitize_filename(name: str) -> str:
        base = Path(name).name
        safe = "".join(c for c in base if c.isalnum() or c in "._- ")
        return safe or "upload.bin"

    def is_probably_text(data: bytes) -> bool:
        if not data:
            return True
        sample = data[:4096]
        if b"\x00" in sample:
            return False
        printable = 0
        for b in sample:
            if b in (9, 10, 13) or 32 <= b <= 126:
                printable += 1
        return (printable / len(sample)) >= 0.7

    def extract_text(filename: str, content: bytes) -> str:
        if is_probably_text(content):
            return content.decode("utf-8", errors="ignore")

        ext = Path(filename).suffix.lower()
        if ext == ".pdf":
            try:
                from pypdf import PdfReader  # type: ignore
            except Exception:  # noqa: BLE001
                try:
                    from PyPDF2 import PdfReader  # type: ignore
                except Exception:  # noqa: BLE001
                    PdfReader = None  # type: ignore

            if PdfReader is not None:
                try:
                    reader = PdfReader(BytesIO(content))
                    parts: List[str] = []
                    for page in reader.pages:
                        text = page.extract_text() or ""
                        if text:
                            parts.append(text)
                    return "\n".join(parts)
                except Exception:  # noqa: BLE001
                    return ""
            return ""

        if ext == ".docx":
            try:
                from docx import Document  # type: ignore
                doc = Document(BytesIO(content))
                return "\n".join(p.text for p in doc.paragraphs if p.text)
            except Exception:  # noqa: BLE001
                return ""

        return ""

    state = get_state(session_id)
    attach_state(state)
    dbg(f"Upload received: {len(files)} files for session {session_id}")
    count = 0
    skipped: List[str] = []
    stored: List[str] = []
    state.setdefault("uploaded_files", [])
    session_dir = UPLOADS_DIR / session_id
    session_dir.mkdir(parents=True, exist_ok=True)
    for file in files:
        content = await file.read()
        safe_name = sanitize_filename(file.filename)
        file_path = session_dir / safe_name
        try:
            file_path.write_bytes(content)
            stored.append(safe_name)
            state["uploaded_files"].append(
                {
                    "name": file.filename,
                    "stored_name": safe_name,
                    "path": str(file_path),
                    "size": len(content),
                    "content_type": file.content_type,
                }
            )
        except Exception:  # noqa: BLE001
            skipped.append(file.filename)
            continue

        extracted = extract_text(file.filename, content).strip()
        if extracted:
            state["file_context"] += f"FILE {file.filename}:\n{extracted}\n\n"
            count += 1
        else:
            state["file_context"] += (
                f"FILE {file.filename}:\n[stored, no text extracted]\n\n"
            )
    file_count = len(
        [chunk for chunk in state["file_context"].split("FILE ") if chunk.strip()]
    )
    save_session(session_id, state)
    return {
        "loaded_files": count,
        "total_files": file_count,
        "stored_files": stored,
        "skipped_files": skipped,
    }


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
    result = {
        "acc": "",
        "thinking": "",
        "answer": "",
        "has_thinking": False,
        "saved": False,
    }
    request_id = uuid.uuid4().hex
    state.setdefault("pending_requests", {})
    state.setdefault("jobs", {})
    state["pending_requests"][request_id] = {
        "prompt": prompt,
        "started_at": time.time(),
    }
    state["jobs"][request_id] = {
        "id": request_id,
        "prompt": prompt,
        "status": "running",
        "started_at": time.time(),
        "updated_at": time.time(),
        "answer": "",
        "raw": "",
        "thinking": "",
        "error": "",
    }
    dbg(
        "job id created "
        + json.dumps(
            {
                "id": request_id,
                "status": "running",
                "started_at": state["jobs"][request_id]["started_at"],
                "prompt_len": len(prompt),
            }
        )
    )
    save_session(session_id, state)

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
            state["jobs"][request_id]["status"] = "error"
            state["jobs"][request_id]["error"] = str(e)
            state["jobs"][request_id]["updated_at"] = time.time()
            dbg(
                "job id task ended "
                + json.dumps(
                    {
                        "id": request_id,
                        "status": "error",
                        "updated_at": state["jobs"][request_id]["updated_at"],
                        "error": str(e),
                    }
                )
            )
        finally:
            acc = "".join(acc_parts)
            if acc:
                thinking, answer, has_thinking = split_thinking(acc)
                result["acc"] = acc
                result["thinking"] = thinking
                result["answer"] = answer if has_thinking else acc
                result["has_thinking"] = has_thinking
                if has_thinking:
                    set_debug("model_thinking", thinking)
                    dbg(f"Model thinking captured ({len(thinking)} chars)")
                if not result["saved"]:
                    state["history"].append(("assistant", acc))
                    state["pending_requests"].pop(request_id, None)
                    state["jobs"][request_id]["status"] = "done"
                    state["jobs"][request_id]["raw"] = acc
                    state["jobs"][request_id]["thinking"] = thinking
                    state["jobs"][request_id]["answer"] = result["answer"]
                    state["jobs"][request_id]["updated_at"] = time.time()
                    dbg(
                        "job id task ended "
                        + json.dumps(
                            {
                                "id": request_id,
                                "status": "done",
                                "updated_at": state["jobs"][request_id]["updated_at"],
                                "answer_len": len(state["jobs"][request_id]["answer"] or ""),
                                "raw_len": len(state["jobs"][request_id]["raw"] or ""),
                                "thinking_len": len(state["jobs"][request_id]["thinking"] or ""),
                            }
                        )
                    )
                    save_session(session_id, state)
                    result["saved"] = True
                    dbg("Response saved to history (worker)")
            else:
                state["pending_requests"].pop(request_id, None)
                state["jobs"][request_id]["status"] = "error"
                state["jobs"][request_id]["error"] = "empty response"
                state["jobs"][request_id]["updated_at"] = time.time()
                dbg(
                    "job id task ended "
                    + json.dumps(
                        {
                            "id": request_id,
                            "status": "error",
                            "updated_at": state["jobs"][request_id]["updated_at"],
                            "error": "empty response",
                        }
                    )
                )
                save_session(session_id, state)
            push_status("Finalizing output…")
            asyncio.run_coroutine_threadsafe(queue.put({"type": "end"}), loop)

    threading.Thread(target=model_worker, daemon=True).start()

    async def event_stream():
        yield json.dumps({"type": "job", "job_id": request_id}) + "\n"
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
                acc = result["acc"] or "".join(acc_parts)
                push_status("Done")
                meta = {
                    "type": "final",
                    "raw": acc,
                    "answer": result["answer"] if result["answer"] else acc,
                    "thinking": result["thinking"],
                }
                yield json.dumps(meta) + "\n"
                break

    return StreamingResponse(event_stream(), media_type="text/plain")


@router.post("/api/send_async")
async def send_async(request: Request):
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
    if location_failed:
        use_search = False
    state["use_search"] = use_search
    state["auto_fetch_top_result"] = use_search
    if isinstance(location, dict) and location.get("lat") is not None and location.get("lon") is not None:
        state["user_location"] = location
    elif location is None:
        pass
    else:
        state["user_location"] = None

    state["history"].append(("user", prompt))

    request_id = uuid.uuid4().hex
    state.setdefault("pending_requests", {})
    state.setdefault("jobs", {})
    state["pending_requests"][request_id] = {
        "prompt": prompt,
        "started_at": time.time(),
    }
    state["jobs"][request_id] = {
        "id": request_id,
        "prompt": prompt,
        "status": "running",
        "started_at": time.time(),
        "updated_at": time.time(),
        "answer": "",
        "raw": "",
        "thinking": "",
        "error": "",
    }
    dbg(
        "job id created "
        + json.dumps(
            {
                "id": request_id,
                "status": "running",
                "started_at": state["jobs"][request_id]["started_at"],
                "prompt_len": len(prompt),
            }
        )
    )
    save_session(session_id, state)

    def model_worker_async():
        try:
            deadline = time.monotonic() + SEARCH_TIME_BUDGET
            search_context, web_context, timed_out, search_error = gather_context(
                prompt, "", deadline
            )
            set_debug("search_error", search_error)
            if search_error:
                add_error(search_error)

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

            generate_url, headers, model = get_ollama_endpoint()
            dbg(f"Async request to model={model} url={generate_url}")
            acc_parts: List[str] = []
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
                    if data.get("done"):
                        break

            acc = "".join(acc_parts)
            thinking, answer, has_thinking = split_thinking(acc)
            if has_thinking:
                set_debug("model_thinking", thinking)
            state["history"].append(("assistant", acc))
            state["pending_requests"].pop(request_id, None)
            state["jobs"][request_id]["status"] = "done"
            state["jobs"][request_id]["raw"] = acc
            state["jobs"][request_id]["thinking"] = thinking
            state["jobs"][request_id]["answer"] = answer if has_thinking else acc
            state["jobs"][request_id]["updated_at"] = time.time()
            dbg(
                "job id task ended "
                + json.dumps(
                    {
                        "id": request_id,
                        "status": "done",
                        "updated_at": state["jobs"][request_id]["updated_at"],
                        "answer_len": len(state["jobs"][request_id]["answer"] or ""),
                        "raw_len": len(state["jobs"][request_id]["raw"] or ""),
                        "thinking_len": len(state["jobs"][request_id]["thinking"] or ""),
                    }
                )
            )
            save_session(session_id, state)
        except Exception as e:  # noqa: BLE001
            add_error(str(e))
            state["pending_requests"].pop(request_id, None)
            state["jobs"][request_id]["status"] = "error"
            state["jobs"][request_id]["error"] = str(e)
            state["jobs"][request_id]["updated_at"] = time.time()
            dbg(
                "job id task ended "
                + json.dumps(
                    {
                        "id": request_id,
                        "status": "error",
                        "updated_at": state["jobs"][request_id]["updated_at"],
                        "error": str(e),
                    }
                )
            )
            save_session(session_id, state)

    threading.Thread(target=model_worker_async, daemon=True).start()
    return {"job_id": request_id}


@router.get("/api/jobs/{job_id}")
async def get_job(job_id: str, session_id: str):
    state = get_state(session_id)
    attach_state(state)
    job = state.get("jobs", {}).get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    return job
