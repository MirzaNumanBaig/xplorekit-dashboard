"""Enrichment: give agents the facts they would otherwise have to guess.
GitHub candidates get a README excerpt (install steps, what it does) and any Chrome Web Store links found in it.
Only raw.githubusercontent.com is read (an official raw-file host); each repo costs one request.
"""
import re

from xplorekit.common import host_of, http_get, normalize_url, settings, strip_html

STORE = re.compile(r"https?://(?:chromewebstore\.google\.com|chrome\.google\.com/webstore)/detail/[A-Za-z0-9%._~-]+(?:/[a-p]{32})?", re.I)
GH_REPO = re.compile(r"^https://github\.com/([\w.-]+)/([\w.-]+)/?$")
GH_ANY = re.compile(r"^https://github\.com/([\w.-]+)/([\w.-]+?)(?:\.git)?(?:/.*)?$")
README_NAMES = ("README.md", "readme.md", "README.MD", "README.rst", "README")


def github_repo(url):
    """(owner, repo) for any github.com repo URL (root, /blob/..., /tree/...), else None."""
    m = GH_ANY.match(url.split("#")[0].split("?")[0])
    return m.groups() if m and m.group(1) not in ("orgs", "topics", "sponsors", "settings", "marketplace") else None


def store_links(text):
    """Chrome Web Store detail URLs found in text, normalised to the current host and without query strings."""
    out = []
    for u in STORE.findall(text or ""):
        u = u.replace("chrome.google.com/webstore/detail", "chromewebstore.google.com/detail").replace("http://", "https://")
        n = normalize_url(u)
        if n not in out:
            out.append(n)
    return out


def relevant(cand, section):
    kws = settings().get("relevance_keywords", {}).get(section)
    if not kws:
        return True
    blob = " ".join([cand.get("title", ""), cand.get("snippet", ""), cand.get("details", ""), cand.get("url", "")]).lower()
    return any(k in blob for k in kws)


def readme(owner, repo):
    """README text from GitHub's raw-file host, or '' when the repo has none (or the network fails)."""
    for name in README_NAMES:
        try:
            code, body = http_get(f"https://raw.githubusercontent.com/{owner}/{repo}/HEAD/{name}", max_bytes=200_000)
        except Exception:
            return ""
        if code == 200:
            return body
    return ""


def readme_plain(owner, repo, limit=20000):
    text = readme(owner, repo)
    return re.sub(r"\s+", " ", re.sub(r"!\[[^\]]*\]\([^)]*\)|<[^>]+>", " ", text))[:limit]


def enrich(cands, section, limit=None):
    """Mutates and returns cands: adds `details` (README excerpt) and `store_urls` for GitHub repos, for the first `limit` only."""
    limit = limit or settings().get("enrich_max", 12)
    done = 0
    for c in cands:
        m = GH_REPO.match(c["url"])
        if not m or done >= limit:
            continue
        text = readme(*m.groups())
        done += 1
        if not text:
            continue
        c["store_urls"] = store_links(text)
        plain = re.sub(r"!\[[^\]]*\]\([^)]*\)|<[^>]+>", " ", text)  # drop badges and html
        c["details"] = re.sub(r"\s+", " ", plain)[:2500]
    return cands
