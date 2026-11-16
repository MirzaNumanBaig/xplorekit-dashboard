"""Link liveness. Never hammers a site: HEAD first, one GET only when HEAD is refused; robots.txt is respected."""
import urllib.error

from xplorekit.common import Blocked, http_get, robots_allowed
from xplorekit.enrich import README_NAMES, github_repo

# status words: ok | blocked (reachable, but the site refuses bots: 401/403/429) | dead (404/410/DNS/connection) | error (5xx) | robots (we may not fetch it)


def check_github(owner, repo):
    """A GitHub repo is live when its README is served by raw.githubusercontent.com (official raw host: no HTML scraping)."""
    for name in README_NAMES:
        try:
            code, _ = http_get(f"https://raw.githubusercontent.com/{owner}/{repo}/HEAD/{name}", method="HEAD", check_robots=False)
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError):
            return "dead", None
        if code == 200:
            return "ok", 200
    return "dead", 404


def check(url):
    """Return (status_word, http_code_or_None)."""
    gh = github_repo(url)
    if gh:
        return check_github(*gh)
    try:
        if not robots_allowed(url):
            return "robots", None
        code, _ = http_get(url, method="HEAD", check_robots=False)
        if code >= 400:  # some servers answer HEAD with 404/405/403 but serve GET fine: only a failing GET counts
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
