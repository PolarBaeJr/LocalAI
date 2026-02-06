import os
import shutil
import threading
import time
from typing import Optional

from Model import CLOUD_MODEL, get_ollama_endpoint


def start_tunnel(port: int) -> Optional[str]:
    """
    Start a public tunnel using Cloudflare quick tunnel.
    Env toggle:
      USE_CLOUDFLARE=1 -> use cloudflared quick tunnel if installed.
      CLOUDFLARE_HOSTNAME=<your.domain.com> -> bind to that hostname (requires cloudflared login + DNS in Cloudflare).
    Returns the public URL or None.
    """
    use_cf = os.environ.get("USE_CLOUDFLARE", "1") == "1"
    hostname = os.environ.get("CLOUDFLARE_HOSTNAME", "app.polardev.org")

    if use_cf and shutil.which("cloudflared"):
        log_path = "/tmp/cloudflared.log"
        cmd = f"cloudflared tunnel --url http://localhost:{port} --no-autoupdate"
        if hostname:
            cmd += f" --hostname {hostname}"
        threading.Thread(
            target=lambda: os.system(f"{cmd} > {log_path} 2>&1"),
            daemon=True,
        ).start()
        # Poll the log for the assigned URL (trycloudflare.com)
        for _ in range(30):
            try:
                with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
                    for line in f.readlines():
                        if hostname and hostname in line:
                            return f"https://{hostname}"
                        if "trycloudflare.com" in line:
                            return line.strip().split()[-1]
            except Exception:
                pass
            time.sleep(1)
        print("cloudflared started but no public URL found (check /tmp/cloudflared.log)")

    return None


def print_endpoints(port: int, public_url: Optional[str]) -> None:
    desired_public = "https://app.polardev.org"
    print("=== Local Chat endpoints ===")
    print(f"Local:  http://localhost:{port}")
    if public_url:
        print(f"Public: {desired_public}")
    else:
        print(f"Public: {desired_public} (cloudflared not detected; ensure tunnel is running)")
    print("============================")


def print_model_route() -> None:
    try:
        generate_url, _, selected_model = get_ollama_endpoint()
        print(f"-- Model route: {selected_model} -> {generate_url}")
        if selected_model == CLOUD_MODEL:
            print("-- Debug Cloud model activated")
    except Exception as e:
        print(f"-- Model resolution error: {e}")
