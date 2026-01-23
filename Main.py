import json
import requests
import streamlit as st
import time

from Prompt import build_prompt, build_chat_context
from UI import render_history, render_tools_sidebar, render_file_and_chat
from Debug import init_debug, add_timing, set_prompt, status
from Model import OLLAMA_URL, MODEL, SEARCH_TIME_BUDGET
from Config import apply_defaults
from logic import split_thinking, gather_context

st.set_page_config(page_title="Local Chat", page_icon="")
st.title("Local Chat")
init_debug()

apply_defaults(st.session_state)


# Render history
render_history(st.session_state.history)

file_context, prompt = render_file_and_chat()

# Tools sidebar (after bottom toggles to avoid session_state conflicts)
web_url = render_tools_sidebar(st.session_state)
if prompt:
    st.session_state.history.append(("user", prompt))
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        deadline = time.monotonic() + SEARCH_TIME_BUDGET
        placeholder = st.empty()
        acc = ""
        with status("Search + fetch"):
            search_context, web_context, timed_out = gather_context(
                prompt, web_url, deadline
            )

        if timed_out:
            st.warning(
                f"Search/fetch capped at {SEARCH_TIME_BUDGET // 60} minute(s); continuing with available context."
            )

        # (Optional) simple “chat” by packing history into one prompt
        # For a more robust chat, use /api/chat or /v1/chat/completions if you prefer.
        chat_context = build_chat_context(st.session_state.history)
        full_prompt = build_prompt(file_context, search_context, web_context, chat_context)
        set_prompt(full_prompt)
        _t_model = time.perf_counter()

        with requests.post(
            OLLAMA_URL,
            json={"model": MODEL, "prompt": full_prompt, "stream": True},
            stream=True,
            timeout=300,
        ) as r:
            r.raise_for_status()
            for line in r.iter_lines(decode_unicode=True):
                if not line:
                    continue
                data = json.loads(line)
                acc += data.get("response", "")
                placeholder.markdown(acc)

                if data.get("done"):
                    break

        add_timing("model", time.perf_counter() - _t_model)

        thinking, answer, has_thinking = split_thinking(acc)
        if has_thinking:
            placeholder.empty()
            if thinking:
                st.markdown("**Reasoning**")
                st.code(thinking, language="text")
            if answer:
                st.markdown("**Answer**")
                st.markdown(answer)
        else:
            placeholder.markdown(acc)

        st.session_state.history.append(("assistant", acc))
