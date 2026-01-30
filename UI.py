from nicegui import ui


def render_history(history):
    """
    Render an existing chat history into a column and return the column so
    callers can append future messages.
    """
    column = ui.column().classes("gap-3 w-full")
    for role, text in history:
        with ui.chat_message(role):
            ui.markdown(text)
    return column


def render_tools_sidebar(state):
    """
    Simple left drawer with a search toggle. Returns the drawer instance.
    """
    with ui.left_drawer(bordered=True, value=False) as drawer:
        ui.label("Tools").classes("text-lg font-semibold mb-2")
        def on_switch(value):
            state["use_search"] = value
            state["auto_fetch_top_result"] = value
        ui.switch(
            "Enable search (auto top result)",
            value=state.get("use_search", False),
            on_change=lambda e: on_switch(e.value),
        )
    return drawer


def render_file_uploader(state, on_files):
    """
    Render file uploader; on_files gets an UploadEvent per file.
    """
    ui.upload(
        label="Add context files (txt, rtf, docx, doc, pdf, jpg)",
        auto_upload=True,
        multiple=True,
        max_file_size=25 * 1024 * 1024,
        on_upload=on_files,
    ).classes("w-full")


def render_chat_input(on_send):
    """
    Render a text box + send button pinned at the bottom; calls on_send(text).
    """
    with ui.footer().classes("bg-slate-950 text-white"):
        with ui.row().classes("w-full max-w-5xl mx-auto items-end gap-3 p-4"):
            prompt_box = ui.textarea(
                placeholder="Type a message...",
                min_rows=1,
                max_rows=4,
            ).props("autogrow").classes("flex-1")
            def trigger_send():
                on_send(prompt_box.value)
                prompt_box.value = ""
            prompt_box.on("keydown.enter", lambda e: trigger_send())
            ui.button("Send", color="primary", on_click=lambda: trigger_send())
    return prompt_box


def render_search_error(error_message: str | None):
    if error_message:
        ui.notification(f"Search unavailable: {error_message}", color="orange", position="top")
