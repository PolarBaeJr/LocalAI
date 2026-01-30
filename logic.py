import time
from nicegui import app

from Search import perform_search
from WebAccess import fetch_url
from UI import render_search_error
from Debug import dbg, set_debug, add_error, add_timing, add_fetch, set_evidence


def split_thinking(text: str):
    start = text.find("<think>")
    end = text.find("</think>")
    if start != -1 and end != -1 and end > start:
        thinking = text[start + len("<think>") : end].strip()
        answer = (text[:start] + text[end + len("</think>") :]).strip()
        return thinking, answer, True
    return None, text.strip(), False


def gather_context(prompt: str, web_url: str, deadline: float):
    """
    Run search and return search_context, web_context, timed_out.
    Also records debug info and sets evidence for downstream use.
    """
    state = app.storage.user
    search_results = []
    search_error = None
    timed_out = False
    web_context = ""  # URL fetch removed

    use_search = state.get("use_search", False)
    if use_search:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            timed_out = True
            search_error = "Search time budget exceeded before starting."
        else:
            _t_search = time.perf_counter()
            dbg("Searching the web…")
            search_results, search_error = perform_search(
                prompt, max_results=10, timeout=min(30, int(remaining))
            )
            add_timing("search", time.perf_counter() - _t_search)
            set_debug("search", {"results": search_results, "error": search_error})
            if search_error:
                add_error(str(search_error))
            dbg(f"Search returned {len(search_results)} result(s)")
    render_search_error(search_error)

    search_context_lines = []
    for i, res in enumerate(search_results):
        title = res.get("title", "").strip()
        url = res.get("url", "").strip()
        snippet = res.get("snippet", "").strip() or title
        display = snippet if not url else f"{snippet} ({url})"
        search_context_lines.append(f"SEARCH RESULT {i+1}: {display}")
    search_context = "\n".join(search_context_lines)

    evidence_text = search_context.strip()
    set_evidence(evidence_text)

    return search_context, web_context, timed_out
