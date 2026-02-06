"""
Ollama endpoint selection: prefer explicit host, then local daemon, then cloud.
"""

import os
import time
from typing import Any, Dict, Tuple

import requests

try:
    from Debug import dbg, set_debug, add_error
except Exception:  # pragma: no cover - fallback when Debug import fails
    def dbg(message: str) -> None:
        return None

    def set_debug(key: str, value: Any) -> None:
        return None

    def add_error(message: str) -> None:
        return None

# Prefer a local APIkeys.py (gitignored) for secrets; fall back to env var.
try:
    from APIkeys import OLLAMA_API_KEY as _OLLAMA_API_KEY_FILE  # type: ignore
except Exception:
    _OLLAMA_API_KEY_FILE = None
OLLAMA_API_KEY = _OLLAMA_API_KEY_FILE or os.environ.get("OLLAMA_API_KEY", "")

try:
    import DebugSettings  # type: ignore
except Exception:
    DebugSettings = None

try:
    from Debug import debug_settings_enabled, get_forced_model_env
except Exception:  # pragma: no cover - during early import
    def debug_settings_enabled() -> bool:
        return False

    def get_forced_model_env() -> str | None:
        return None

LOCAL_MODEL = "deepseek-r1:14b"
CLOUD_MODEL = "deepseek-v3.2:cloud"
SEARCH_TIME_BUDGET = 180  # seconds max for all search activity per message

DEFAULT_LOCAL_BASE = os.environ.get("OLLAMA_LOCAL_BASE", "http://localhost:11434")
DEFAULT_CLOUD_BASE = os.environ.get("OLLAMA_CLOUD_BASE", "https://ollama.com")
LOCAL_STARTUP_GRACE_S = float(os.environ.get("OLLAMA_LOCAL_WAIT_SECONDS", "8"))


def _normalize_base(host: str) -> str:
    host = host.strip()
    if not host.startswith(("http://", "https://")):
        host = f"http://{host}"
    return host.rstrip("/")


def _generate_url(base: str) -> str:
    base = _normalize_base(base)
    if base.endswith("/api/generate"):
        return base
    if base.endswith("/api"):
        return f"{base}/generate"
    return f"{base}/api/generate"


def _version_url(base: str) -> str:
    base = _normalize_base(base)
    if base.endswith("/api/version"):
        return base
    if base.endswith("/api"):
        return f"{base}/version"
    if base.endswith("/api/generate"):
        return base.rsplit("/", 1)[0] + "/version"
    return f"{base}/api/version"


def _is_up(base: str, timeout: float = 0.8) -> bool:
    try:
        resp = requests.get(_version_url(base), timeout=timeout)
        return resp.ok
    except Exception:
        return False


def _auth_headers(base: str, require_key: bool = False) -> Dict[str, str]:
    # Cloud endpoints require a bearer token; local usually does not.
    needs_key = (
        require_key
        or "ollama.com" in base
        or base.startswith("https://api.ollama.")
    )
    if needs_key:
        if not OLLAMA_API_KEY:
            raise RuntimeError(
                "OLLAMA_API_KEY is required for the configured Ollama cloud endpoint."
            )
        return {"Authorization": f"Bearer {OLLAMA_API_KEY}"}
    return {}


def _is_local_base(base: str) -> bool:
    host = base.replace("http://", "").replace("https://", "").split("/")[0]
    return host.startswith("localhost") or host.startswith("127.0.0.1")


def _debug_force_model() -> str | None:
    """
    Determine a forced model, respecting:
    1) env var DEBUG_FORCE_MODEL (set by Debug.enable_debug_settings)
    2) DebugSettings.py FORCE_MODEL when ENABLE_DEBUG_SETTINGS or env flag is on
    """
    env_force = get_forced_model_env()
    if env_force:
        return env_force

    if not debug_settings_enabled():
        return None

    if DebugSettings and getattr(DebugSettings, "ENABLE_DEBUG_SETTINGS", False):
        return getattr(DebugSettings, "FORCE_MODEL", None)
    return None


def get_ollama_endpoint(timeout: float = 0.8) -> Tuple[str, Dict[str, str], str]:
    """
    Returns (generate_url, headers, model) using this priority:
    1) Explicit OLLAMA_HOST env override.
    2) Reachable local daemon.
    3) Cloud endpoint (requires OLLAMA_API_KEY in APIkeys.py or env).
    """
    forced_model = _debug_force_model()
    set_debug("forced_model", forced_model)

    explicit_host = os.environ.get("OLLAMA_HOST")
    if explicit_host:
        base = _normalize_base(explicit_host)
        is_cloud = "ollama.com" in base and not _is_local_base(base)
        model = forced_model or (CLOUD_MODEL if is_cloud else LOCAL_MODEL)
        dbg(f"Using explicit OLLAMA_HOST={base} model={model}")
        return _generate_url(base), _auth_headers(base, require_key=is_cloud), model

    if forced_model:
        # If the override looks like "cloud" choose the cloud base; otherwise assume local.
        if forced_model.lower() == "cloud" or forced_model == CLOUD_MODEL:
            base = _normalize_base(DEFAULT_CLOUD_BASE)
            dbg(f"Forced model -> cloud via {base}")
            return _generate_url(base), _auth_headers(base, require_key=True), CLOUD_MODEL
        if forced_model.lower() == "local" or forced_model == LOCAL_MODEL:
            base = _normalize_base(DEFAULT_LOCAL_BASE)
            dbg(f"Forced model -> local via {base}")
            return _generate_url(base), {}, LOCAL_MODEL
        # Custom tag: prefer local if reachable, else cloud with auth.
        base_local = _normalize_base(DEFAULT_LOCAL_BASE)
        if _is_up(base_local, timeout=timeout):
            dbg(f"Forced custom model={forced_model}; local up at {base_local}")
            return _generate_url(base_local), {}, forced_model
        base_cloud = _normalize_base(DEFAULT_CLOUD_BASE)
        dbg(f"Forced custom model={forced_model}; falling back to cloud {base_cloud}")
        return _generate_url(base_cloud), _auth_headers(base_cloud, require_key=True), forced_model

    if _is_up(DEFAULT_LOCAL_BASE, timeout=timeout):
        base = _normalize_base(DEFAULT_LOCAL_BASE)
        set_debug("endpoint_reason", "local_reachable")
        dbg(f"Selected reachable local Ollama at {base}")
        return _generate_url(base), {}, LOCAL_MODEL
    if LOCAL_STARTUP_GRACE_S > 0:
        set_debug("endpoint_reason", "local_wait")
        wait_msg = f"Local Ollama not reachable; waiting up to {LOCAL_STARTUP_GRACE_S:.0f}s"
        dbg(wait_msg)
        print(wait_msg)
        start = time.monotonic()
        while time.monotonic() - start < LOCAL_STARTUP_GRACE_S:
            remaining = int(LOCAL_STARTUP_GRACE_S - (time.monotonic() - start))
            tick_msg = f"Waiting for local Ollama... {max(0, remaining)}s"
            dbg(tick_msg)
            print(tick_msg)
            time.sleep(1)
            if _is_up(DEFAULT_LOCAL_BASE, timeout=timeout):
                base = _normalize_base(DEFAULT_LOCAL_BASE)
                set_debug("endpoint_reason", "local_recovered")
                dbg(f"Local Ollama became reachable at {base}")
                return _generate_url(base), {}, LOCAL_MODEL

    cloud_base = _normalize_base(DEFAULT_CLOUD_BASE)
    if _is_up(cloud_base, timeout=timeout):
        set_debug("endpoint_reason", "cloud_fallback")
        dbg(f"Defaulting to cloud Ollama at {cloud_base}")
        return _generate_url(cloud_base), _auth_headers(cloud_base, require_key=True), CLOUD_MODEL

    set_debug("endpoint_reason", "no_endpoint")
    add_error("No reachable Ollama endpoint (local or cloud).")
    raise RuntimeError("No reachable Ollama endpoint (local or cloud).")


# Default fallback so existing imports still work; will be overridden at runtime.
OLLAMA_URL, OLLAMA_HEADERS, MODEL = get_ollama_endpoint()
