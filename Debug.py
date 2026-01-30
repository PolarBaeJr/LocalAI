from __future__ import annotations

import time
from contextlib import contextmanager
from nicegui import ui, app


def _state() -> dict:
    return app.storage.user


def init_debug():
    state = _state()
    state.setdefault("dbg_log", [])
    state.setdefault("dbg_timings", [])
    state.setdefault("dbg_errors", [])
    state.setdefault("dbg_fetches", [])
    state.setdefault("dbg_evidence", "")
    state.setdefault("dbg_prompt", "")
    state.setdefault("dbg_data", {})


def dbg(message: str):
    _state()["dbg_log"].append(message)


def set_debug(key: str, value):
    _state()["dbg_data"][key] = value


def add_error(message: str):
    _state()["dbg_errors"].append(message)


def add_timing(label: str, seconds: float):
    _state()["dbg_timings"].append({"label": label, "seconds": seconds})


def add_fetch(url: str, error: str | None):
    _state()["dbg_fetches"].append({"url": url, "error": error})


def set_evidence(text: str):
    _state()["dbg_evidence"] = text


def set_prompt(text: str):
    _state()["dbg_prompt"] = text


@contextmanager
def status(label: str):
    """Lightweight status context so Main.py can wrap blocks."""
    badge = ui.badge(label).props("color=blue").classes("self-start")
    start = time.perf_counter()
    try:
        yield
    finally:
        elapsed = time.perf_counter() - start
        badge.text = f"{label} (done in {elapsed:.1f}s)"
