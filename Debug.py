from __future__ import annotations

import time
from contextlib import contextmanager
import streamlit as st


def init_debug():
    if "dbg_log" not in st.session_state:
        st.session_state.dbg_log = []
    if "dbg_timings" not in st.session_state:
        st.session_state.dbg_timings = []
    if "dbg_errors" not in st.session_state:
        st.session_state.dbg_errors = []
    if "dbg_fetches" not in st.session_state:
        st.session_state.dbg_fetches = []
    if "dbg_evidence" not in st.session_state:
        st.session_state.dbg_evidence = ""
    if "dbg_prompt" not in st.session_state:
        st.session_state.dbg_prompt = ""
    if "dbg_data" not in st.session_state:
        st.session_state.dbg_data = {}


def dbg(message: str):
    st.session_state.dbg_log.append(message)


def set_debug(key: str, value):
    st.session_state.dbg_data[key] = value


def add_error(message: str):
    st.session_state.dbg_errors.append(message)


def add_timing(label: str, seconds: float):
    st.session_state.dbg_timings.append({"label": label, "seconds": seconds})


def add_fetch(url: str, error: str | None):
    st.session_state.dbg_fetches.append({"url": url, "error": error})


def set_evidence(text: str):
    st.session_state.dbg_evidence = text


def set_prompt(text: str):
    st.session_state.dbg_prompt = text


@contextmanager
def status(label: str):
    """Lightweight status context so App.py can wrap blocks."""
    placeholder = st.empty()
    placeholder.info(label)
    start = time.perf_counter()
    try:
        yield
    finally:
        elapsed = time.perf_counter() - start
        placeholder.info(f"{label} (done in {elapsed:.1f}s)")
