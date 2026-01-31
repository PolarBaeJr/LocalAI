from __future__ import annotations

import time
from contextlib import contextmanager

_current_state: dict | None = None


def attach_state(state: dict):
    """Point debug helpers at the active session state."""
    global _current_state
    _current_state = state


def get_state() -> dict:
    if _current_state is None:
        raise RuntimeError("Debug state is not attached")
    return _current_state


def init_debug(state: dict):
    attach_state(state)
    state.setdefault("dbg_log", [])
    state.setdefault("dbg_timings", [])
    state.setdefault("dbg_errors", [])
    state.setdefault("dbg_fetches", [])
    state.setdefault("dbg_evidence", "")
    state.setdefault("dbg_prompt", "")
    state.setdefault("dbg_data", {})


def dbg(message: str):
    get_state()["dbg_log"].append(message)


def set_debug(key: str, value):
    get_state()["dbg_data"][key] = value


def add_error(message: str):
    get_state()["dbg_errors"].append(message)


def add_timing(label: str, seconds: float):
    get_state()["dbg_timings"].append({"label": label, "seconds": seconds})


def add_fetch(url: str, error: str | None):
    get_state()["dbg_fetches"].append({"url": url, "error": error})


def set_evidence(text: str):
    get_state()["dbg_evidence"] = text


def set_prompt(text: str):
    get_state()["dbg_prompt"] = text


@contextmanager
def status(label: str):
    """Lightweight status context that records duration."""
    start = time.perf_counter()
    try:
        yield
    finally:
        elapsed = time.perf_counter() - start
        add_timing(label, elapsed)
