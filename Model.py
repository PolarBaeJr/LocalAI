"""
Ollama endpoint selection: prefer explicit host, then local daemon, then cloud.
"""

import os
from typing import Dict, Tuple

import requests

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

    def get_forced_model_env():
        return None

LOCAL_MODEL = "deepseek-r1:14b"
CLOUD_MODEL = "deepseek-v3.2:cloud"
SEARCH_TIME_BUDGET = 180  # seconds max for all search activity per message

DEFAULT_LOCAL_BASE = os.environ.get("OLLAMA_LOCAL_BASE", "http://localhost:11434")
DEFAULT_CLOUD_BASE = os.environ.get("OLLAMA_CLOUD_BASE", "https://ollama.com")


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

    explicit_host = os.environ.get("OLLAMA_HOST")
    if explicit_host:
        base = _normalize_base(explicit_host)
        is_cloud = "ollama.com" in base and not _is_local_base(base)
        model = forced_model or (CLOUD_MODEL if is_cloud else LOCAL_MODEL)
        return _generate_url(base), _auth_headers(base, require_key=is_cloud), model

    if forced_model:
        # If the override looks like "cloud" choose the cloud base; otherwise assume local.
        if forced_model.lower() == "cloud" or forced_model == CLOUD_MODEL:
            base = _normalize_base(DEFAULT_CLOUD_BASE)
            return _generate_url(base), _auth_headers(base, require_key=True), CLOUD_MODEL
        if forced_model.lower() == "local" or forced_model == LOCAL_MODEL:
            base = _normalize_base(DEFAULT_LOCAL_BASE)
            return _generate_url(base), {}, LOCAL_MODEL
        # Custom tag: prefer local if reachable, else cloud with auth.
        base_local = _normalize_base(DEFAULT_LOCAL_BASE)
        if _is_up(base_local, timeout=timeout):
            return _generate_url(base_local), {}, forced_model
        base_cloud = _normalize_base(DEFAULT_CLOUD_BASE)
        return _generate_url(base_cloud), _auth_headers(base_cloud, require_key=True), forced_model

    if _is_up(DEFAULT_LOCAL_BASE, timeout=timeout):
        base = _normalize_base(DEFAULT_LOCAL_BASE)
        return _generate_url(base), {}, LOCAL_MODEL

    cloud_base = _normalize_base(DEFAULT_CLOUD_BASE)
    return _generate_url(cloud_base), _auth_headers(cloud_base, require_key=True), CLOUD_MODEL


# Default fallback so existing imports still work; will be overridden at runtime.
OLLAMA_URL, OLLAMA_HEADERS, MODEL = get_ollama_endpoint()
