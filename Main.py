import asyncio
import json
import time
import requests
from nicegui import ui, app

from Prompt import build_prompt, build_chat_context
from UI import render_history, render_tools_sidebar, render_file_uploader, render_chat_input
from Debug import init_debug, add_timing, set_prompt, status
from Model import OLLAMA_URL, MODEL, SEARCH_TIME_BUDGET
from Config import apply_defaults
from logic import split_thinking, gather_context


def _state() -> dict:
    return app.storage.user


def main():
    state = _state()
    apply_defaults(state)
    init_debug()

    ui.markdown("## Local Chat").classes("text-3xl font-semibold mt-4")

    # Tools drawer
    render_tools_sidebar(state)

    # History area
    history_column = render_history(state["history"])
    history_column.classes("max-w-5xl mx-auto pt-2")

    # File uploader + status
    with ui.card().classes("max-w-5xl mx-auto w-full"):
        ui.label("Context files").classes("text-sm text-gray-500")
        file_status = ui.markdown("").classes("text-xs text-gray-400")

        def on_files(e):
            content = e.content.read()
            text = content.decode("utf-8", errors="ignore")
            state["file_context"] += f"FILE {e.name}:\n{text.strip()}\n\n"
            count = len([chunk for chunk in state["file_context"].split("FILE ") if chunk.strip()])
            file_status.set_content(f"Loaded {count} file(s)")

        render_file_uploader(state, on_files)

    assistant_placeholder = ui.markdown("").classes("max-w-5xl mx-auto w-full")

    async def send(prompt: str):
        if not prompt.strip():
            return
        state["history"].append(("user", prompt))
        with history_column:
            with ui.chat_message("user"):
                ui.markdown(prompt)

        deadline = time.monotonic() + SEARCH_TIME_BUDGET
        acc = ""
        with status("Search + fetch"):
            search_context, web_context, timed_out = gather_context(
                prompt, "", deadline
            )

        if timed_out:
            ui.notification(
                f"Search/fetch capped at {SEARCH_TIME_BUDGET // 60} minute(s); continuing with available context.",
                color="orange",
            )

        chat_context = build_chat_context(state["history"])
        full_prompt = build_prompt(state.get("file_context", ""), search_context, web_context, chat_context)
        set_prompt(full_prompt)

        _t_model = time.perf_counter()
        with history_column:
            with ui.chat_message("assistant"):
                holder = ui.markdown("")
                # Run blocking stream in thread to avoid blocking UI
                def stream_model():
                    nonlocal acc
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
                            ui.run_later(lambda text=acc: holder.set_content(text), 0)
                            if data.get("done"):
                                break
                await asyncio.to_thread(stream_model)

        add_timing("model", time.perf_counter() - _t_model)

        thinking, answer, has_thinking = split_thinking(acc)
        if has_thinking:
            holder.set_content("")
            with history_column:
                if thinking:
                    ui.markdown("**Reasoning**")
                    ui.code(thinking, language="text")
                if answer:
                    ui.markdown("**Answer**")
                    ui.markdown(answer)
        else:
            holder.set_content(acc)

        state["history"].append(("assistant", acc))

    render_chat_input(lambda text: asyncio.create_task(send(text)))


@ui.page("/")
def index_page():
    main()


if __name__ in {"__main__", "__mp_main__"}:
    ui.run(title="Local Chat", reload=False)
