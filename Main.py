import asyncio
import json
import threading
import time
import uuid
from pathlib import Path
from typing import Dict, List

import requests
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse

from Prompt import build_prompt, build_chat_context
from Debug import (
    init_debug,
    add_timing,
    set_prompt,
    status,
    attach_state,
)
from Model import OLLAMA_URL, MODEL, SEARCH_TIME_BUDGET
from Config import apply_defaults
from logic import split_thinking, gather_context

app = FastAPI()

# Simple in-memory session storage; keyed by client-provided session_id.
STATE: Dict[str, dict] = {}


def get_state(session_id: str) -> dict:
    if not session_id:
        raise HTTPException(status_code=400, detail="session_id is required")
    state = STATE.setdefault(session_id, {})
    apply_defaults(state)
    return state


HTML_TEMPLATE = Path(__file__).with_name("index.html")


@app.get("/", response_class=HTMLResponse)
async def index() -> HTMLResponse:
    """Serve the lightweight HTML shell."""
    if not HTML_TEMPLATE.exists():
        build_html()
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


def build_html():
    """
    Generate a single-page HTML with hand-rolled layout and streaming client.
    Stored separately so the user can tweak styles freely.
    """
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Local Chat</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600&display=swap" rel="stylesheet">
  <style>
    :root {{
      --bg: #0d1117;
      --panel: #111827;
      --accent: #16a34a;
      --muted: #9ca3af;
      --border: #1f2937;
      --text: #e5e7eb;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: 'Space Grotesk', sans-serif;
      background: radial-gradient(circle at 20% 20%, #0b1220, #05080f 40%), var(--bg);
      color: var(--text);
      min-height: 100vh;
      display: flex;
      flex-direction: column;
    }}
    header {{
      padding: 18px 24px;
      border-bottom: 1px solid var(--border);
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      background: rgba(17, 24, 39, 0.7);
      backdrop-filter: blur(8px);
      position: sticky;
      top: 0;
      z-index: 2;
    }}
    .brand {{
      font-weight: 600;
      letter-spacing: 0.01em;
      display: flex;
      align-items: center;
      gap: 10px;
    }}
    .brand span {{
      padding: 6px 10px;
      border: 1px solid var(--border);
      border-radius: 999px;
      background: #0b1324;
      font-size: 12px;
      color: var(--muted);
    }}
    .controls {{
      display: flex;
      align-items: center;
      gap: 12px;
    }}
    .toggle {{
      display: inline-flex;
      align-items: center;
      gap: 8px;
      font-size: 14px;
      color: var(--muted);
      cursor: pointer;
    }}
    .toggle input {{ accent-color: var(--accent); width: 18px; height: 18px; }}
    .badge {{
      font-size: 12px;
      padding: 6px 10px;
      border-radius: 999px;
      border: 1px solid var(--border);
      color: var(--muted);
    }}
    main {{
      flex: 1;
      max-width: 960px;
      width: 100%;
      margin: 0 auto;
      padding: 24px;
      display: flex;
      flex-direction: column;
      gap: 16px;
    }}
    .panel {{
      background: rgba(17, 24, 39, 0.75);
      border: 1px solid var(--border);
      border-radius: 18px;
      padding: 16px;
      box-shadow: 0 20px 60px rgba(0,0,0,0.35);
    }}
    .upload {{
      border: 1px dashed var(--border);
      padding: 14px;
      border-radius: 14px;
      background: rgba(255,255,255,0.01);
      color: var(--muted);
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
    }}
    #history {{
      display: flex;
      flex-direction: column;
      gap: 12px;
      max-height: calc(100vh - 280px);
      overflow-y: auto;
      padding-right: 4px;
    }}
    .msg {{
      padding: 14px 16px;
      border-radius: 14px;
      line-height: 1.55;
      white-space: pre-wrap;
      border: 1px solid var(--border);
    }}
    .msg.user {{ background: #0b1324; border-color: #172033; }}
    .msg.assistant {{ background: #0f172a; border-color: #1e293b; }}
    .label {{ font-size: 12px; color: var(--muted); margin-bottom: 4px; }}
    .input-area {{
      display: grid;
      grid-template-columns: 1fr auto;
      gap: 10px;
      align-items: end;
    }}
    textarea {{
      width: 100%;
      resize: none;
      background: #0b1324;
      color: var(--text);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 12px 14px;
      font-size: 15px;
      line-height: 1.4;
      min-height: 80px;
    }}
    button {{
      background: linear-gradient(120deg, #16a34a, #14b8a6);
      color: white;
      border: none;
      border-radius: 12px;
      padding: 12px 18px;
      font-weight: 600;
      cursor: pointer;
      box-shadow: 0 10px 30px rgba(20,184,166,0.25);
      transition: transform 120ms ease, box-shadow 120ms ease;
    }}
    button:active {{ transform: translateY(1px); box-shadow: 0 6px 18px rgba(20,184,166,0.2); }}
    .toast {{
      position: fixed;
      bottom: 18px;
      right: 18px;
      background: #111827;
      border: 1px solid var(--border);
      color: var(--text);
      padding: 10px 14px;
      border-radius: 10px;
      box-shadow: 0 10px 30px rgba(0,0,0,0.35);
      opacity: 0;
      transform: translateY(10px);
      transition: all 160ms ease;
      z-index: 5;
    }}
    .toast.show {{ opacity: 1; transform: translateY(0); }}
    @media (max-width: 700px) {{
      main {{ padding: 16px; }}
      header {{ flex-direction: column; align-items: flex-start; }}
      .input-area {{ grid-template-columns: 1fr; }}
      button {{ width: 100%; }}
    }}
  </style>
</head>
<body>
  <header>
    <div class="brand">
      Local Chat
      <span>FastAPI + custom HTML</span>
    </div>
    <div class="controls">
      <label class="toggle">
        <input id="search-toggle" type="checkbox" checked />
        Enable search
      </label>
      <div id="file-counter" class="badge">No files</div>
    </div>
  </header>

  <main>
    <section class="panel upload">
      <div>
        <div class="label">Context files</div>
        <small>Add txt/pdf/docx/etc. They are concatenated into the prompt.</small>
      </div>
      <input id="file-input" type="file" multiple />
    </section>

    <section id="history" class="panel"></section>

    <section class="panel input-area">
      <textarea id="prompt" placeholder="Ask anything…" rows="3"></textarea>
      <button id="send">Send</button>
    </section>
  </main>

  <div id="toast" class="toast"></div>

  <script>
    const sessionId = localStorage.getItem("localchat_session") || crypto.randomUUID();
    localStorage.setItem("localchat_session", sessionId);

    const historyEl = document.getElementById("history");
    const promptEl = document.getElementById("prompt");
    const sendBtn = document.getElementById("send");
    const toastEl = document.getElementById("toast");
    const fileInput = document.getElementById("file-input");
    const fileCounter = document.getElementById("file-counter");
    const searchToggle = document.getElementById("search-toggle");

    let assistantBubble = null;

    function showToast(text) {{
      toastEl.textContent = text;
      toastEl.classList.add("show");
      setTimeout(() => toastEl.classList.remove("show"), 3200);
    }}

    function addMessage(role, text) {{
      const wrap = document.createElement("div");
      wrap.className = "msg " + role;
      wrap.innerText = text;
      historyEl.appendChild(wrap);
      historyEl.scrollTop = historyEl.scrollHeight;
      return wrap;
    }}

    function renderAssistant(text) {{
      if (!assistantBubble) assistantBubble = addMessage("assistant", "");
      assistantBubble.innerText = text;
      historyEl.scrollTop = historyEl.scrollHeight;
    }}

    function renderFinal(msg) {{
      assistantBubble = null;
      if (msg.thinking) {{
        addMessage("assistant", "Reasoning:\\n" + msg.thinking);
      }}
      addMessage("assistant", msg.answer);
    }}

    async function sendMessage() {{
      const prompt = promptEl.value.trim();
      if (!prompt) return;
      addMessage("user", prompt);
      promptEl.value = "";
      assistantBubble = null;
      sendBtn.disabled = true;
      promptEl.disabled = true;

      const resp = await fetch("/api/send", {{
        method: "POST",
        headers: {{ "Content-Type": "application/json" }},
        body: JSON.stringify({{
          prompt,
          session_id: sessionId,
          use_search: searchToggle.checked
        }}),
      }});

      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let aborted = false;

      while (true) {{
        const {{ value, done }} = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, {{ stream: true }});
        const lines = buffer.split("\\n");
        buffer = lines.pop();
        for (const line of lines) {{
          if (!line.trim()) continue;
          const msg = JSON.parse(line);
          if (msg.type === "token") {{
            renderAssistant((assistantBubble?.innerText || "") + msg.text);
          }} else if (msg.type === "notice") {{
            showToast(msg.text);
          }} else if (msg.type === "error") {{
            showToast("Model error: " + msg.text);
            aborted = true;
          }} else if (msg.type === "final") {{
            renderFinal(msg);
          }}
        }}
        if (aborted) break;
      }}

      sendBtn.disabled = false;
      promptEl.disabled = false;
      promptEl.focus();
    }}

    sendBtn.addEventListener("click", sendMessage);
    promptEl.addEventListener("keydown", (e) => {{
      if (e.key === "Enter" && !e.shiftKey) {{
        e.preventDefault();
        sendMessage();
      }}
    }});

    fileInput.addEventListener("change", async (e) => {{
      const files = Array.from(e.target.files);
      if (!files.length) return;
      const form = new FormData();
      form.append("session_id", sessionId);
      for (const f of files) form.append("files", f, f.name);
      const resp = await fetch("/api/upload", {{
        method: "POST",
        body: form,
      }});
      const data = await resp.json();
      fileCounter.textContent = data.total_files
        ? `${{data.total_files}} file(s) loaded`
        : "No files";
      showToast(`Attached ${{data.loaded_files}} file(s)`);
      fileInput.value = "";
    }});

    // Load existing history on first paint
    (async () => {{
      const resp = await fetch(`/api/history?session_id=${{sessionId}}`);
      const data = await resp.json();
      for (const [role, text] of data.history) {{
        addMessage(role, text);
      }}
    }})();
  </script>
</body>
</html>
"""
    HTML_TEMPLATE.write_text(html, encoding="utf-8")


if not HTML_TEMPLATE.exists():
    build_html()


if __name__ in {"__main__", "__mp_main__"}:
    import uvicorn  # type: ignore

    uvicorn.run(app, host="0.0.0.0", port=7860)
