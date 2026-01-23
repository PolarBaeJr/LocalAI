import streamlit as st


def render_history(history):
    for role, text in history:
        with st.chat_message(role):
            st.markdown(text)

_style_injected = False


def _inject_chatbar_style():
    global _style_injected
    if _style_injected:
        return
    st.markdown(
        """
        <style>
        /* Chat bar styling */
        [data-testid="stChatInput"] textarea, [data-testid="stChatInput"] input {
            background: #1e1e1e;
            border-radius: 16px;
            padding: 14px 16px;
            border: 1px solid #2c2c2c;
            color: #f4f4f4;
            font-size: 15px;
        }
        [data-testid="stChatInput"] label {
            color: #c4c4c4 !important;
            font-weight: 500;
        }
        .chatbar-shell {
            background: #0f0f0f;
            border-radius: 18px;
            padding: 10px 14px 4px;
            border: 1px solid #2c2c2c;
            box-shadow: 0 8px 24px rgba(0,0,0,0.35);
        }
        .chatbar-icons {
            display: flex;
            align-items: center;
            gap: 12px;
            padding: 8px 4px 2px;
            color: #c4c4c4;
            font-size: 18px;
        }
        .chatbar-icons .primary {
            background: #1f4fff;
            color: #f7f7ff;
            padding: 4px 10px;
            border-radius: 12px;
            font-weight: 600;
            font-size: 14px;
        }
        .chatbar-actions [data-testid="column"] {
            padding-left: 2px !important;
            padding-right: 2px !important;
        }
        .chatbar-actions .stButton button {
            padding: 4px 8px;
            font-size: 12px;
            min-width: 0;
        }
        .chatbar-wrapper {
            position: fixed !important;
            left: 0;
            right: 0;
            bottom: 0;
            padding: 10px 16px 14px;
            background: linear-gradient(180deg, rgba(0,0,0,0) 0%, rgba(12,12,12,0.75) 35%, rgba(12,12,12,0.92) 100%);
            backdrop-filter: blur(8px);
            z-index: 9999;
        }
        .chatbar-wrapper .chatbar-shell {
            max-width: 1200px;
            width: calc(100% - 32px);
            margin: 0 auto;
        }
        /* Add bottom padding so content isn't covered by fixed bar */
        .block-container {
            padding-bottom: 260px !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    _style_injected = True


def render_tools_sidebar(state):
    st.sidebar.markdown("### Tools")
    st.sidebar.checkbox(
        "Enable search (auto top result)",
        value=state.use_search,
        key="use_search",
        help="When enabled, your prompt will be sent to search and top results added as context.",
    )
    # Keep auto-fetch in sync with search toggle
    st.session_state.auto_fetch_top_result = st.session_state.use_search
    return ""


def render_file_uploader():
    uploaded = st.file_uploader(
        "Add context files (txt,rtf,docx,doc,pdf,jpg)", type=["txt,rtf,docx,doc,pdf,jpg"], accept_multiple_files=True
    )
    snippets = []
    if uploaded:
        for f in uploaded:
            try:
                text = f.read().decode("utf-8")
                snippets.append(f"FILE {f.name}:\n{text.strip()}")
            except Exception as e:
                st.warning(f"Could not read {f.name}: {e}")
    return "\n\n".join(snippets)


def render_chat_input():
    return st.chat_input("Type a message...")


def render_file_and_chat():
    """
    Show the file uploader immediately above the chat input and return (file_context, prompt).
    Also renders a row of clickable toggles beneath the input for quick actions.
    """
    _inject_chatbar_style()
    with st.container():
        st.markdown('<div id="chatbar-wrapper" class="chatbar-wrapper"><div class="chatbar-shell">', unsafe_allow_html=True)
        file_context = render_file_uploader()
        prompt = render_chat_input()

        st.markdown('<div class="chatbar-actions">', unsafe_allow_html=True)
        cols = st.columns([1])

        # Single toggle: search + auto-fetch together
        use_search = st.session_state.get("use_search", False)
        if cols[0].button(
            f"🌐 Search {'On' if use_search else 'Off'}",
            key="toggle_search_btn",
        ):
            st.session_state.use_search = not use_search
            st.session_state.auto_fetch_top_result = st.session_state.use_search

        st.markdown("</div></div>", unsafe_allow_html=True)
        st.markdown(
            """
            <script>
            const el = document.getElementById("chatbar-wrapper");
            if (el && el.parentElement !== document.body) {
              document.body.appendChild(el);
            }
            </script>
            """,
            unsafe_allow_html=True,
        )

    return file_context, prompt
