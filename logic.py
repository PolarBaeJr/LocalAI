import re
import time

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

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


# ---------------- Dynamic routing ("thinking") ----------------

@dataclass
class Signals:
    ambiguity: float
    needs_search: float
    needs_tool: float
    tool_name: Optional[str] = None


def compute_signals(prompt: str) -> Signals:
    """Compute lightweight signals that help decide what to do next."""
    t = prompt.strip().lower()

    # Ambiguity: short / vague requests tend to need clarification
    vague_markers = [
        "this",
        "that",
        "it",
        "wrong",
        "fix",
        "help",
        "why",
        "how",
        "explain",
        "doesn't work",
        "not working",
    ]
    ambiguity = 0.0
    if len(t.split()) <= 6:
        ambiguity += 0.35
    if any(v in t for v in vague_markers):
        ambiguity += 0.35
    if "?" not in t and any(v in t for v in ["wrong", "fix", "not working"]):
        ambiguity += 0.2
    ambiguity = min(1.0, ambiguity)

    # Tool detection (extend as you add tools)
    needs_tool = 0.0
    tool_name: Optional[str] = None

    # very simple calculator detection
    if re.search(r"\b(calc|calculate|what is)\b", t) and re.search(r"\d", t):
        needs_tool = 0.9
        tool_name = "calculator"

    # time/date detection
    if re.search(r"\b(time|date)\b", t):
        needs_tool = max(needs_tool, 0.9)
        tool_name = "time"

    # Search likelihood (reuse your existing heuristic)
    needs_search = 1.0 if _needs_search(prompt) else 0.0

    return Signals(
        ambiguity=ambiguity,
        needs_search=needs_search,
        needs_tool=needs_tool,
        tool_name=tool_name,
    )


@dataclass
class Step:
    action: str  # "clarify" | "tool" | "search" | "respond"
    args: Dict[str, str] = field(default_factory=dict)


def make_dynamic_plan(prompt: str) -> List[Step]:
    """Create a small plan. This is what makes the bot feel more "dynamic"."""
    s = compute_signals(prompt)

    # 1) If the prompt is too ambiguous, ask a clarifying question first.
    if s.ambiguity >= 0.7 and s.needs_tool < 0.75 and s.needs_search < 0.5:
        return [Step("clarify")]

    # 2) Tools have highest priority when strongly detected.
    if s.needs_tool >= 0.75 and s.tool_name:
        return [Step("tool", {"tool": s.tool_name, "input": prompt}), Step("respond")]

    # 3) Otherwise consider searching when the heuristic says it would help.
    if s.needs_search >= 0.5:
        return [Step("search"), Step("respond")]

    # 4) Default: respond directly.
    return [Step("respond")]


def render_clarifying_question(prompt: str) -> str:
    """Ask for the minimum info needed to proceed."""
    return (
        "I can help — quick clarifier so I don’t guess:\n"
        "1) What’s your goal / expected output?\n"
        "2) What’s the exact input (paste it)?\n"
        "3) What did you get instead (error/output)?\n"
        "If this is about your local model, paste the last 20–40 lines of logs too."
    )


def run_tool(tool: str, user_input: str) -> Tuple[str, Optional[str]]:
    """Run a small built-in tool and return (result, error). Extend freely."""
    tool = tool.lower().strip()

    if tool == "time":
        return time.strftime("%Y-%m-%d %H:%M:%S"), None

    if tool == "calculator":
        # Extract a basic arithmetic expression after common prefixes.
        # This is intentionally conservative.
        m = re.search(r"(?:calc|calculate|what is)\s+(.+)", user_input, re.IGNORECASE)
        expr = (m.group(1) if m else user_input).strip()
        if not re.fullmatch(r"[0-9\.\+\-\*\/\(\)\s]+", expr):
            return "I can only evaluate basic arithmetic (numbers and + - * / parentheses).", None
        try:
            val = eval(expr, {"__builtins__": {}}, {})
            return str(val), None
        except Exception as e:
            return "I couldn't evaluate that expression.", str(e)

    return "Unknown tool.", f"Unknown tool: {tool}"


def dynamic_think_and_gather(prompt: str, web_url: str, deadline: float):
    """High-level decision layer.

    Returns (mode, search_context, web_context, timed_out, error, tool_result)
    where mode is one of: "clarify" | "tool" | "direct" | "search"
    """
    plan = make_dynamic_plan(prompt)
    set_debug("dynamic_plan", [s.action for s in plan])

    tool_result: Optional[str] = None
    error: Optional[str] = None

    # Execute a tiny multi-step plan. This is where you can expand later.
    for step in plan:
        if step.action == "clarify":
            return "clarify", "", "", False, None, None

        if step.action == "tool":
            _t = time.perf_counter()
            tool_name = step.args.get("tool", "")
            tool_result, err = run_tool(tool_name, step.args.get("input", ""))
            add_timing(f"tool:{tool_name}", time.perf_counter() - _t)
            if err:
                add_error(err)
                error = err
            set_debug("tool", {"tool": tool_name, "result": tool_result, "error": err})

        if step.action == "search":
            # Defer to existing search machinery
            search_context, web_context, timed_out, search_error = gather_context(
                prompt, web_url, deadline
            )
            # If gather_context already timed out or errored, bubble it up
            if search_error:
                error = str(search_error)
            mode = "search" if search_context else "direct"
            return mode, search_context, web_context, timed_out, error, tool_result

    # If we got here, we're either tool-only or direct.
    return ("tool" if tool_result is not None else "direct"), "", "", False, error, tool_result


def gather_context(prompt: str, web_url: str, deadline: float):
    """Search-only context gatherer.
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


def decide_next_action(prompt: str, web_url: str = "", budget_s: float = 30.0):
    """Convenience wrapper: decide whether to clarify, run a tool, search, or answer directly.

    Returns a dict with keys:
      - mode: "clarify" | "tool" | "direct" | "search"
      - tool_result: optional string
      - search_context: optional string
      - web_context: optional string
      - timed_out: bool
      - error: optional string
    """
    deadline = time.monotonic() + float(budget_s)
    mode, search_context, web_context, timed_out, error, tool_result = dynamic_think_and_gather(
        prompt=prompt,
        web_url=web_url,
        deadline=deadline,
    )
    if mode == "clarify":
        return {
            "mode": mode,
            "message": render_clarifying_question(prompt),
            "tool_result": None,
            "search_context": "",
            "web_context": "",
            "timed_out": False,
            "error": None,
        }

    return {
        "mode": mode,
        "message": "",
        "tool_result": tool_result,
        "search_context": search_context,
        "web_context": web_context,
        "timed_out": timed_out,
        "error": error,
    }
