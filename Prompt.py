import os

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


FORMAT_HINT = (
    "Use the SEARCH RESULT and WEB PAGE lines only as background context. "
    "Do NOT repeat, list, or quote the raw search results or URLs; synthesize the answer in your own words. "
    "Keep the response concise and user-facing; skip reasoning steps and metadata."
)

if _show_thinking():
    FORMAT_HINT = (
        "Use the SEARCH RESULT and WEB PAGE lines only as background context. "
        "Do NOT repeat, list, or quote the raw search results or URLs; synthesize the answer in your own words. "
        "If you include reasoning, wrap it in <think>...</think> and place the final answer after the tags. "
        "Keep the final answer concise and user-facing."
    )


def build_chat_context(history, limit=10):
    return "\n".join([f"{r.upper()}: {t}" for r, t in history[-limit:]])


def build_prompt(file_ctx: str, search_ctx: str, web_ctx: str, chat_ctx: str):
    sections = [
        section
        for section in [file_ctx, search_ctx, web_ctx, FORMAT_HINT, chat_ctx]
        if section
    ]
    return "\n\n".join(sections) + "\nASSISTANT:"
