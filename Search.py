import os
import time
import requests

from Debug import dbg, add_error, add_timing, set_debug

DEFAULT_SEARCH_URL = os.environ.get("SEARCH_URL", "https://api.duckduckgo.com/")
GOOGLE_CSE_ID = os.environ.get("GOOGLE_CSE_ID")
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")


def _duckduckgo_search(query: str, max_results: int, url: str, timeout: int):
    dbg(f"DDG search start query='{query}' url='{url}'")
    resp = requests.get(
        url,
        params={"q": query, "format": "json", "no_redirect": 1, "no_html": 1},
        timeout=timeout,
    )
    resp.raise_for_status()
    data = resp.json()
    results = []
    for item in data.get("RelatedTopics", []):
        if isinstance(item, dict) and "Text" in item and "FirstURL" in item:
            results.append(
                {
                    "title": item.get("Text", ""),
                    "url": item.get("FirstURL", "").strip(),
                    "snippet": item.get("Text", ""),
                }
            )
        if len(results) >= max_results:
            break
    if not results and data.get("AbstractText"):
        results.append(
            {
                "title": data.get("Heading", "") or data.get("AbstractText", ""),
                "url": data.get("AbstractURL", "").strip(),
                "snippet": data.get("AbstractText", ""),
            }
        )
    return results


def _google_search(query: str, max_results: int, timeout: int):
    dbg(f"Google CSE search start query='{query}'")
    resp = requests.get(
        "https://www.googleapis.com/customsearch/v1",
        params={
            "q": query,
            "key": GOOGLE_API_KEY,
            "cx": GOOGLE_CSE_ID,
            "num": min(max_results, 10),
        },
        timeout=timeout,
    )
    resp.raise_for_status()
    data = resp.json()
    results = []
    for item in data.get("items", []):
        results.append(
            {
                "title": item.get("title", ""),
                "url": item.get("link", "").strip(),
                "snippet": item.get("snippet", ""),
            }
        )
        if len(results) >= max_results:
            break
    return results


def perform_search(
    query: str, max_results: int = 3, search_url: str | None = None, timeout: int = 30
):
    """
    Execute a web search and return a list of result dicts:
    {"title": str, "url": str, "snippet": str}
    Prefers Google CSE when GOOGLE_CSE_ID and GOOGLE_API_KEY are set; otherwise falls back to DuckDuckGo.
    """
    if not query:
        dbg("perform_search: empty query, skipping")
        return [], None

    errors = []
    use_google = bool(GOOGLE_CSE_ID and GOOGLE_API_KEY)

    if use_google:
        try:
            _t = time.perf_counter()
            google_results = _google_search(query, max_results, timeout)
            add_timing("search_google", time.perf_counter() - _t)
            if google_results:
                dbg(f"Google search returned {len(google_results)} results")
                return google_results[:max_results], None
            errors.append("Google search returned no results.")
        except Exception as e:
            errors.append(f"Google search failed: {e}")
            add_error(str(e))

    url = search_url or DEFAULT_SEARCH_URL
    try:
        _t = time.perf_counter()
        ddg_results = _duckduckgo_search(query, max_results, url, timeout)
        add_timing("search_ddg", time.perf_counter() - _t)
        if ddg_results:
            dbg(f"DDG search returned {len(ddg_results)} results")
            return ddg_results[:max_results], None
        return ddg_results, "; ".join(errors) if errors else None
    except Exception as e:
        errors.append(str(e))
        add_error(str(e))
        return [], "; ".join(errors) if errors else str(e)
