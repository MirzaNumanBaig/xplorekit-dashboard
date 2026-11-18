"""Shared helpers: config, dates, slugs, polite HTTP with robots.txt, URL and title normalisation. Standard library only."""
import difflib
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CFG = ROOT / "xplorekit" / "config"
API_HOSTS = {"hn.algolia.com", "api.github.com", "www.googleapis.com", "oauth.reddit.com"}  # official APIs: robots.txt does not apply

_settings = None
_last_hit = {}
_robots = {}


def load_json(path, default=None):
    try:
        return json.loads(Path(path).read_text("utf-8"))
    except (OSError, ValueError):
        return default


def save_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", "utf-8")


def settings():
    global _settings
    if _settings is None:
        _settings = load_json(CFG / "settings.json", {})
    return _settings


def sources():
    return load_json(CFG / "sources.json", {})


def today():
    return os.environ.get("XK_TODAY") or datetime.now(timezone.utc).strftime("%Y-%m-%d")


def days_between(a, b):
    try:
        return (date.fromisoformat(b) - date.fromisoformat(a)).days
    except (ValueError, TypeError):
        return None


def slugify(text, maxlen=70):
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s[:maxlen].strip("-") or "item"


TRACKING = re.compile(r"^(utm_|ref$|ref_|fbclid|gclid|mc_|source$)", re.I)


def normalize_url(url):
    """Lower-case host, drop www, fragments, tracking params and trailing slashes so equal pages compare equal."""
    try:
        u = urllib.parse.urlsplit(url.strip())
    except ValueError:
        return url
    host = u.netloc.lower().removeprefix("www.")
    q = [(k, v) for k, v in urllib.parse.parse_qsl(u.query) if not TRACKING.match(k)]
    path = u.path.rstrip("/") or ""
    return urllib.parse.urlunsplit((u.scheme.lower(), host, path, urllib.parse.urlencode(sorted(q)), ""))


def host_of(url):
    return urllib.parse.urlsplit(url).netloc.lower().removeprefix("www.")


def norm_title(t):
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]+", " ", t.lower())).strip()


def title_similarity(a, b):
    return difflib.SequenceMatcher(None, norm_title(a), norm_title(b)).ratio()


def user_agent():
    ua = settings().get("http", {}).get("user_agent", "ContentResearchBot/1.0")
    contact = os.environ.get("XK_CONTACT", "").strip()
    return f"{ua} (+{contact})" if contact else ua


def _throttle(host):
    delay = settings().get("http", {}).get("delay_seconds", 1.0)
    wait = _last_hit.get(host, 0) + delay - time.time()
    if wait > 0:
        time.sleep(wait)
    _last_hit[host] = time.time()


def robots_allowed(url):
    """True when robots.txt allows our user agent to fetch url. Unknown/unreachable robots.txt = allowed; a robots.txt that blocks us = not allowed."""
    u = urllib.parse.urlsplit(url)
    host = u.netloc.lower()
    if host in API_HOSTS:
        return True
    base = f"{u.scheme}://{u.netloc}"
    rp = _robots.get(base)
    if rp is None:
        rp = urllib.robotparser.RobotFileParser()
        try:
            _throttle(host)
            req = urllib.request.Request(base + "/robots.txt", headers={"User-Agent": user_agent()})
            with urllib.request.urlopen(req, timeout=15) as r:
                rp.parse(r.read().decode("utf-8", "replace").splitlines())
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                rp.disallow_all = True
            else:
                rp.allow_all = True
        except Exception:
            rp.allow_all = True
        _robots[base] = rp
    return rp.can_fetch(user_agent(), url) and rp.can_fetch("*", url)


class Blocked(Exception):
    """robots.txt forbids this URL."""


def http_get(url, headers=None, data=None, method=None, check_robots=True, max_bytes=1_500_000):
    """GET (or POST/HEAD) with our user agent, a per-host delay and robots.txt. Returns (status, text). Raises Blocked or URLError."""
    if check_robots and not robots_allowed(url):
        raise Blocked(url)
    _throttle(urllib.parse.urlsplit(url).netloc.lower())
    req = urllib.request.Request(url, data=data, method=method, headers={"User-Agent": user_agent(), "Accept": "*/*", **(headers or {})})
    timeout = settings().get("http", {}).get("timeout_seconds", 20)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = b"" if method == "HEAD" else r.read(max_bytes)
            return r.status, body.decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, ""


def strip_html(text):
    text = re.sub(r"(?is)<(script|style|noscript).*?</\1>", " ", text)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    import html
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def readable_text(html_text):
    """Page text without site chrome: the <main> or <article> element when there is one, else the whole page."""
    for tag in ("main", "article"):
        m = re.search(rf"(?is)<{tag}\b[^>]*>(.*)</{tag}>", html_text)
        if m and len(m.group(1)) > 400:
            return strip_html(m.group(1))
    return strip_html(html_text)


_GH = re.compile(r"https?://(?:www\.)?github\.com/([\w.-]+)/([\w.-]+?)(?:\.git)?(?:[/#?].*)?$", re.I)
_CWS = re.compile(r"(?:chromewebstore\.google\.com|chrome\.google\.com/webstore)/detail/(?:[^/?#]+/)?([a-p]{32})")


def canon_key(url):
    """One identity per thing, however its URL is spelled: a GitHub repo, a Chrome Web Store extension id, else the cleaned URL."""
    url = (url or "").strip()
    m = _GH.match(url)
    if m:
        return f"github:{m.group(1).lower()}/{m.group(2).lower()}"
    m = _CWS.search(url)
    if m:
        return f"cws:{m.group(1)}"
    n = normalize_url(url)
    return "url:" + re.sub(r"^https?://", "", n.lower())


def tokens(text):
    return {w for w in norm_title(text).split() if len(w) > 2}


def jaccard(a, b):
    ta, tb = tokens(a), tokens(b)
    return len(ta & tb) / len(ta | tb) if ta and tb else 0.0


PUBLISH_MODES = ("publish", "pending", "draft")


def publish_mode():
    """Where new posts go. publish = delivered and merged by itself (live); pending = a pull request opens and a person merges it;
    draft = research only, nothing is sent to the site. Old settings files with auto_merge_site still work.
    Anything unrecognised or missing falls back to the SAFE side (pending: a person merges), never to publishing."""
    s = settings()
    mode = s.get("publish_mode")
    if mode in PUBLISH_MODES:
        return mode
    return "publish" if s.get("auto_merge_site") is True else "pending"
