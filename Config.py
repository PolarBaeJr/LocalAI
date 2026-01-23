USE_SEARCH_DEFAULT = True
USE_URL_FETCH_DEFAULT = False
AUTO_FETCH_TOP_RESULT_DEFAULT = True


def apply_defaults(session_state):
    if "history" not in session_state:
        session_state.history = []
    if "use_search" not in session_state:
        session_state.use_search = USE_SEARCH_DEFAULT
    if "use_url_fetch" not in session_state:
        session_state.use_url_fetch = USE_URL_FETCH_DEFAULT
    if "auto_fetch_top_result" not in session_state:
        session_state.auto_fetch_top_result = AUTO_FETCH_TOP_RESULT_DEFAULT
