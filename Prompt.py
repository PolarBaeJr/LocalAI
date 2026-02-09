import os

from Config import FORMAT_HINT_BASE, FORMAT_HINT_THINKING

try:
    import DebugSettings  # type: ignore
except Exception:
    DebugSettings = None


def _show_thinking() -> bool:
    env_flag = os.environ.get("SHOW_THINKING", "").strip().lower()
    if env_flag in {"1", "true", "yes", "y", "on"}:
        return True
    if DebugSettings and getattr(DebugSettings, "ENABLE_DEBUG_SETTINGS", False):
        return bool(getattr(DebugSettings, "SHOW_THINKING", False))
    return False


FORMAT_HINT = FORMAT_HINT_BASE

if _show_thinking():
    FORMAT_HINT = FORMAT_HINT_THINKING


def build_chat_context(history, limit=10):
    return "\n".join([f"{r.upper()}: {t}" for r, t in history[-limit:]])


def build_prompt(file_ctx: str, search_ctx: str, web_ctx: str, chat_ctx: str):
    sections = [
        section
        for section in [file_ctx, search_ctx, web_ctx, FORMAT_HINT, chat_ctx]
        if section
    ]
    return "\n\n".join(sections) + "\nASSISTANT:"
