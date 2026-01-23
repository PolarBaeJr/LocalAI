import streamlit as st


def render_search_error(error_message: str | None):
    if error_message:
        st.info(f"Search unavailable: {error_message}")
