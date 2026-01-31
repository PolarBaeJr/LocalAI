FORMAT_HINT = (
    "Use the SEARCH RESULT and WEB PAGE lines only as background context. "
    "Do NOT repeat, list, or quote the raw search results or URLs; synthesize the answer in your own words. "
    "Keep the response concise and user-facing; skip reasoning steps and metadata."
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
