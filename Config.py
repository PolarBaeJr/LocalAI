from __future__ import annotations

from pathlib import Path

USE_SEARCH_DEFAULT = True
USE_URL_FETCH_DEFAULT = False
AUTO_FETCH_TOP_RESULT_DEFAULT = True

# Paths
BASE_DIR = Path(__file__).parent
LOG_ROOT = BASE_DIR / "Logs"
CRASH_ROOT = BASE_DIR / "Crashlog"
ACTIVE_LOG_DIR = LOG_ROOT / "run_active"
UPLOADS_DIR = BASE_DIR / "uploads"
SESSIONS_DIR = BASE_DIR / "sessions"
ARCHIVE_DIR = BASE_DIR / "Deleted_Data"
UPLOAD_ARCHIVE_DIR = ARCHIVE_DIR / "uploads"
HTML_TEMPLATE = BASE_DIR / "index.html"

# Debug flags and colors
DEBUG_STDOUT_FLAG = "DEBUG_TO_STDOUT"
DEBUG_ENV_FLAG = "USE_DEBUG_SETTINGS"
DEBUG_FORCE_MODEL_KEY = "DEBUG_FORCE_MODEL"
DEBUG_COLORS = {
    "DATA": "\033[32m",  # green
    "FLAGS": "\033[32m",  # green
    "LOG": "\033[33m",  # yellow
    "ERROR": "\033[31m",  # red
    "TIME": "\033[36m",  # cyan
    "FETCH": "\033[35m",  # magenta
    "PROMPT": "\033[34m",  # blue
    "EVIDENCE": "\033[34m",  # blue
}

# Ollama / model defaults
LOCAL_MODEL = "qwen3-vl:32b"
CLOUD_MODEL = "deepseek-v3.2:cloud"
SEARCH_TIME_BUDGET = 180  # seconds max for all search activity per message
DEFAULT_LOCAL_BASE = "http://localhost:11434"
DEFAULT_CLOUD_BASE = "https://ollama.com"
LOCAL_STARTUP_GRACE_S = 8.0

# Search / web defaults
DEFAULT_USER_AGENT = "LocalChat/1.0"
DEFAULT_BRAVE_ENDPOINT = "https://api.search.brave.com/res/v1/web/search"
DEFAULT_SEARCH_URL = "https://api.duckduckgo.com/"

# Log reader defaults
LOGREADER_ALLOWED = {"localchat", "ollama", "cloudflared"}
LOGREADER_MAX_LINES = 1000

# Prompt defaults
FORMAT_HINT_BASE = (
    "Use the SEARCH RESULT and WEB PAGE lines only as background context. "
    "Do NOT repeat, list, or quote the raw search results or URLs; synthesize the answer in your own words. "
    "Keep the response concise and user-facing; skip reasoning steps and metadata."
)
FORMAT_HINT_THINKING = (
    "Use the SEARCH RESULT and WEB PAGE lines only as background context. "
    "Do NOT repeat, list, or quote the raw search results or URLs; synthesize the answer in your own words. "
    "If you include reasoning, wrap it in <think>...</think> and place the final answer after the tags. "
    "Keep the final answer concise and user-facing."
)

# Debug settings defaults
ENABLE_DEBUG_SETTINGS = True
FORCE_MODEL: str | None = None
SHOW_THINKING = True

# Data retention defaults
RETENTION_DAYS = 30
UPLOAD_RETENTION_DAYS = 1


def apply_defaults(state: dict):
    """
    Populate a mutable mapping with default keys expected by the app.
    Works with NiceGUI's app.storage.user dict.
    """
    state.setdefault("history", [])
    state.setdefault("use_search", USE_SEARCH_DEFAULT)
    state.setdefault("use_url_fetch", USE_URL_FETCH_DEFAULT)
    state.setdefault("auto_fetch_top_result", AUTO_FETCH_TOP_RESULT_DEFAULT)
    state.setdefault("file_context", "")
    state.setdefault("user_location", None)
    state.setdefault("search_history", [])
