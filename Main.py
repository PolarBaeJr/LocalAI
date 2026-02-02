import asyncio
import os
import shutil
import threading
import time
from typing import Optional

import requests
from fastapi import FastAPI

from routes import router
from Model import get_ollama_endpoint, CLOUD_MODEL

app = FastAPI()
app.include_router(router)


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

    try:
        generate_url, _, selected_model = get_ollama_endpoint()
        print(f"-- Model route: {selected_model} -> {generate_url}")
        if selected_model == CLOUD_MODEL:
            print("-- Debug Cloud model activated")
    except Exception as e:
        print(f"-- Model resolution error: {e}")

    uvicorn.run(app, host=host, port=port)
