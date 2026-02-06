import os
from pathlib import Path
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse

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

    setInterval(() => {
      if (auto.checked) fetchLog();
    }, 2000);
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
    path = Path("/tmp") / f"{name}.log"
    # Prefer /tmp; if missing, fall back to Logs/run_active
    if not path.exists():
        path = LOG_DIR / f"{name}.log"
    text = _read_log(path)
    return JSONResponse({"text": text, "path": str(path)})


if __name__ == "__main__":
    import uvicorn  # type: ignore

    host = os.environ.get("LOGREADER_HOST", "0.0.0.0")
    port = int(os.environ.get("LOGREADER_PORT", "7861"))
    uvicorn.run(app, host=host, port=port)
