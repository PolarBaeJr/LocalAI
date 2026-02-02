import re
import time

from Search import perform_search
from WebAccess import bravery_search
from Debug import dbg, set_debug, add_error, add_timing, set_evidence, get_state


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
    state = get_state()
    search_results = []
    search_error = None
    timed_out = False
    web_context = ""  # URL fetch removed

    use_search = state.get("use_search", False)
    should_search = use_search and _needs_search(prompt)
    set_debug(
        "search_decision",
        {
            "requested": use_search,
            "performed": should_search,
        },
    )

    if should_search:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            timed_out = True
            search_error = "Search time budget exceeded before starting."
        else:
            _t_search = time.perf_counter()
            dbg("Searching the web (Bravery)…")
            search_results, search_error = bravery_search(
                prompt, max_results=10, timeout=min(30, int(remaining))
            )
            # fallback to legacy search if Brave isn't configured
            if search_error and not search_results:
                fallback_results, fallback_error = perform_search(
                    prompt, max_results=10, timeout=min(30, int(remaining))
                )
                if fallback_results:
                    search_results = fallback_results
                    search_error = None
                elif fallback_error:
                    search_error = f"{search_error}; {fallback_error}"
            add_timing("search", time.perf_counter() - _t_search)
            set_debug("search", {"results": search_results, "error": search_error})
            if search_error:
                add_error(str(search_error))
            dbg(f"Search returned {len(search_results)} result(s)")
    elif use_search:
        dbg("Search skipped: heuristic judged prompt answerable without web search.")

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

    return search_context, web_context, timed_out, search_error


def _needs_search(prompt: str) -> bool:
    """Lightweight heuristic to decide if web search is helpful."""
    text = prompt.lower()

    # Topics that usually need fresh data
    fresh_keywords = [
        "today",
        "latest",
        "current",
        "breaking",
        "news",
        "price",
        "prices",
        "stock",
        "stocks",
        "weather",
        "forecast",
        "score",
        "scores",
        "schedule",
        "release date",
        "who is",
        "ceo",
    ]

    if any(k in text for k in fresh_keywords):
        return True

    # Mentions of a specific year often imply recency questions
    if re.search(r"\b202[3-9]\b", text):
        return True

    # URLs or explicit web references imply needing external context
    if "http://" in text or "https://" in text:
        return True

    return False
