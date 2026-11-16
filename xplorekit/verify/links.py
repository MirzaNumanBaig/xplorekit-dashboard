"""Link liveness. Never hammers a site: HEAD first, one GET only when HEAD is refused; robots.txt is respected."""
import urllib.error

from xplorekit.common import Blocked, http_get, robots_allowed

# status words: ok | blocked (reachable, but the site refuses bots: 401/403/429) | dead (404/410/DNS/connection) | error (5xx) | robots (we may not fetch it)


def check(url):
    """Return (status_word, http_code_or_None)."""
    try:
        if not robots_allowed(url):
            return "robots", None
        code, _ = http_get(url, method="HEAD", check_robots=False)
        if code in (405, 501) or code >= 400 and code not in (404, 410):
            code, _ = http_get(url, check_robots=False, max_bytes=20_000)
    except Blocked:
        return "robots", None
    except (urllib.error.URLError, TimeoutError, ConnectionError, OSError):
        return "dead", None
    if 200 <= code < 400:
        return "ok", code
    if code in (401, 403, 429):
        return "blocked", code
    if code in (404, 410):
        return "dead", code
    return "error", code


def usable(status):
    """A link counts as verified when it answered, or answered 'no bots' (the page exists, we are just not allowed in)."""
    return status in ("ok", "blocked")
