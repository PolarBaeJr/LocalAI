import os
import requests

DEFAULT_USER_AGENT = "LocalChat/1.0"
BRAVE_ENDPOINT = os.environ.get(
    "BRAVE_SEARCH_ENDPOINT", "https://api.search.brave.com/res/v1/web/search"
)

# Prefer a local APIkeys.py (ignored by git) for secrets; fall back to env var.
try:
    from APIkeys import BRAVE_API_KEY as _BRAVE_API_KEY_FILE  # type: ignore
except Exception:
    _BRAVE_API_KEY_FILE = None
BRAVE_API_KEY = _BRAVE_API_KEY_FILE or os.environ.get("BRAVE_API_KEY")


def bravery_search(query: str, max_results: int = 5, timeout: int = 10):
    """
    Query Brave Search and return (results, error).
    Each result: {"title": str, "url": str, "snippet": str}
    """
    if not query:
        return [], "No query provided"
    if not BRAVE_API_KEY:
        return [], "BRAVE_API_KEY is not set (env or APIkeys.py)"

    headers = {
        "Accept": "application/json",
        "User-Agent": DEFAULT_USER_AGENT,
        "X-Subscription-Token": BRAVE_API_KEY,
    }
    params = {"q": query, "count": max_results}

    try:
        resp = requests.get(
            BRAVE_ENDPOINT,
            headers=headers,
            params=params,
            timeout=timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        results = []
        for item in data.get("web", {}).get("results", []):
            results.append(
                {
                    "title": item.get("title", "").strip(),
                    "url": item.get("url", "").strip(),
                    "snippet": item.get("description", "").strip(),
                }
            )
            if len(results) >= max_results:
                break
        if not results:
            return [], "Brave Search returned no results"
        return results, None
    except Exception as e:
        return [], str(e)


# Alias to match the "braviary" wording the user uses.
braviary_search = bravery_search
