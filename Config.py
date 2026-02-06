USE_SEARCH_DEFAULT = True
USE_URL_FETCH_DEFAULT = False
AUTO_FETCH_TOP_RESULT_DEFAULT = True


def apply_defaults(state: dict):
    """
    Populate a mutable mapping with default keys expected by the app.
    Works with NiceGUI's app.storage.user dict.
    """
    state.setdefault("history", [])
    state.setdefault("use_search", USE_SEARCH_DEFAULT)
    state.setdefault("use_url_fetch", USE_URL_FETCH_DEFAULT)
    state.setdefault("auto_fetch_top_result", AUTO_FETCH_TOP_RESULT_DEFAULT)
    state.setdefault("file_context", "")
    state.setdefault("user_location", None)
