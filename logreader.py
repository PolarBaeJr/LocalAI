import os
import asyncio
import time
from pathlib import Path
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse

app = FastAPI()

ROOT = Path(__file__).parent
LOG_DIR = ROOT / "Logs" / "run_active"


def _read_log(path: Path, max_lines: int = 500) -> str:
    if not path.exists():
        return ""
    try:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        return "\n".join(lines[-max_lines:])
    except Exception:
        return ""


def _resolve_log_path(name: str) -> Path:
    name = name.lower()
    if name not in {"localchat", "ollama", "cloudflared"}:
        return Path()
    path = LOG_DIR / f"{name}.log"
    return path


@app.get("/", response_class=HTMLResponse)
async def index() -> HTMLResponse:
    html = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Log Reader</title>
  <style>
    :root {
      --bg: #0b0f17;
      --panel: #0f172a;
      --border: #1f2937;
      --text: #e5e7eb;
      --muted: #9ca3af;
      --accent: #16a34a;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace;
      background: var(--bg);
      color: var(--text);
      min-height: 100vh;
      display: grid;
      grid-template-columns: 280px 1fr;
      gap: 16px;
      padding: 16px;
    }
    .sidebar {
      background: var(--panel);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 12px;
      display: flex;
      flex-direction: column;
      gap: 8px;
      height: calc(100vh - 32px);
      position: sticky;
      top: 16px;
    }
    .log-btn {
      border: 1px solid var(--border);
      background: #0b1324;
      color: var(--text);
      padding: 8px 10px;
      border-radius: 8px;
      text-align: left;
      cursor: pointer;
    }
    .log-btn.active {
      border-color: var(--accent);
      box-shadow: 0 0 0 1px rgba(22,163,74,0.2);
    }
    .viewer {
      background: var(--panel);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 12px;
      display: flex;
      flex-direction: column;
      gap: 8px;
      height: calc(100vh - 32px);
    }
    .toolbar {
      display: flex;
      align-items: center;
      gap: 12px;
      color: var(--muted);
      font-size: 12px;
    }
    .content {
      flex: 1;
      overflow: auto;
      white-space: pre-wrap;
      background: #0b1324;
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 10px;
      font-size: 12px;
    }
    input[type="checkbox"] { accent-color: var(--accent); }
  </style>
</head>
<body>
  <aside class="sidebar">
    <div style="font-size:14px;color:var(--muted);margin-bottom:6px;">Logs</div>
    <button class="log-btn" data-log="localchat">localchat.log</button>
    <button class="log-btn" data-log="ollama">ollama.log</button>
    <button class="log-btn" data-log="cloudflared">cloudflared.log</button>
  </aside>
  <section class="viewer">
    <div class="toolbar">
      <div id="status">Idle</div>
      <label><input id="autorefresh" type="checkbox" checked /> Auto refresh (2s)</label>
    </div>
    <div id="content" class="content">Select a log…</div>
  </section>
  <script>
    const buttons = document.querySelectorAll(".log-btn");
    const content = document.getElementById("content");
    const status = document.getElementById("status");
    const auto = document.getElementById("autorefresh");
    let current = "localchat";

    function setActive(name) {
      current = name;
      buttons.forEach((b) => b.classList.toggle("active", b.dataset.log === name));
      fetchLog();
    }

    async function fetchLog() {
      status.textContent = "Loading…";
      try {
        const base = window.location.pathname.replace(/\/$/, "");
        const resp = await fetch(`${base}/api/logs/${current}`);
        const data = await resp.json();
        content.textContent = data.text || "";
        status.textContent = data.path ? `Loaded ${data.path}` : "Loaded";
      } catch (e) {
        status.textContent = "Failed to load";
      }
    }

    buttons.forEach((b) => b.addEventListener("click", () => setActive(b.dataset.log)));
    setActive("localchat");

    let watcher = null;
    function startWatcher() {
      if (!auto.checked) return;
      if (watcher) watcher.close();
      const base = window.location.pathname.replace(/\/$/, "");
      watcher = new EventSource(`${base}/api/logs_watch/${current}`);
      watcher.onmessage = () => fetchLog();
      watcher.onerror = () => {
        watcher.close();
        watcher = null;
        setTimeout(startWatcher, 1000);
      };
    }

    auto.addEventListener("change", () => {
      if (auto.checked) {
        startWatcher();
      } else if (watcher) {
        watcher.close();
        watcher = null;
      }
    });

    startWatcher();
  </script>
</body>
</html>
"""
    return HTMLResponse(html)


@app.get("/api/logs/{name}")
async def read_log(name: str) -> JSONResponse:
    name = name.lower()
    if name not in {"localchat", "ollama", "cloudflared"}:
        return JSONResponse({"text": "", "path": ""})
    path = _resolve_log_path(name)
    text = _read_log(path)
    return JSONResponse({"text": text, "path": str(path)})


@app.get("/api/logs_watch/{name}")
async def watch_log(name: str) -> StreamingResponse:
    name = name.lower()

    async def event_stream():
        path = _resolve_log_path(name)
        last_mtime = 0.0
        last_emit = 0.0
        while True:
            try:
                mtime = path.stat().st_mtime if path and path.exists() else 0.0
                if not last_mtime:
                    last_mtime = mtime
                elif mtime and mtime > last_mtime:
                    now = time.monotonic()
                    if now - last_emit >= 1.0:
                        last_mtime = mtime
                        last_emit = now
                        yield "data: {}\n\n"
                await asyncio.sleep(0.5)
            except Exception:
                await asyncio.sleep(1.0)

    if name not in {"localchat", "ollama", "cloudflared"}:
        return StreamingResponse(iter(()), media_type="text/event-stream")
    return StreamingResponse(event_stream(), media_type="text/event-stream")


if __name__ == "__main__":
    import uvicorn  # type: ignore

    host = os.environ.get("LOGREADER_HOST", "0.0.0.0")
    port = int(os.environ.get("LOGREADER_PORT", "7861"))
    uvicorn.run(app, host=host, port=port)
