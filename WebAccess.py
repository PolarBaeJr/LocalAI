import requests

DEFAULT_USER_AGENT = "LocalChat/1.0"


def fetch_url(url: str, max_bytes: int = 8000, timeout: int = 10):
    """
    Fetch a URL and return a (text, error) tuple. Text is truncated to max_bytes.
    """
    if not url:
        return "", "No URL provided"
    try:
        resp = requests.get(
            url,
            headers={"User-Agent": DEFAULT_USER_AGENT},
            timeout=timeout,
        )
        resp.raise_for_status()
        content = resp.text
        if len(content.encode("utf-8")) > max_bytes:
            # Trim to byte limit while keeping utf-8 decodeable
            trimmed = content.encode("utf-8")[:max_bytes]
            content = trimmed.decode("utf-8", errors="ignore")
        return content.strip(), None
    except Exception as e:
        return "", str(e)
