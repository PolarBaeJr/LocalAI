FORMAT_HINT = (
    "Use provided SEARCH RESULT and WEB PAGE lines as your only external knowledge. "
    "you do have internet use it to search online"
    "Prefer WEB PAGE content when available; cite URLs in the answer. "
    "Show the whole process that you are reasoning"
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
