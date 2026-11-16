"""Collectors turn one configured source into raw candidates: {source_id, title, url, snippet, date, score, extra}.
They use official APIs, RSS and public pages (robots.txt respected). Text is kept only as a short snippet for reading and
fact-checking; it is never published or saved to data/.
"""
import os

from xplorekit.common import sources


def missing_key(src):
    keys = [k for k in src.get("requires_key", "").split(",") if k]
    return [k for k in keys if not os.environ.get(k)]


def registry():
    from . import github, hackernews, reddit, rss, webpage, youtube
    return {"hn": hackernews.collect, "github": github.collect, "rss": rss.collect, "producthunt_rss": rss.collect,
            "reddit": reddit.collect, "youtube": youtube.collect, "webpage": webpage.collect}


def collect_section(section, log=print):
    """Run every enabled source of a section. A failing or key-less source is reported and skipped, never fatal."""
    out, report = [], []
    reg = registry()
    for src in sources().get(section, []):
        sid = src["id"]
        if not src.get("enabled", True):
            report.append((sid, "disabled", 0))
            continue
        miss = missing_key(src)
        if miss:
            report.append((sid, f"skipped, missing {','.join(miss)}", 0))
            continue
        fn = reg.get(src["type"])
        if not fn:
            report.append((sid, f"unknown type {src['type']}", 0))
            continue
        try:
            items = fn(src)
            for it in items:
                it["source_id"] = sid
            out += items
            report.append((sid, "ok", len(items)))
        except Exception as e:  # one broken source must not stop the run
            report.append((sid, f"error: {type(e).__name__}: {str(e)[:80]}", 0))
    for sid, status, n in report:
        log(f"  [{section}] {sid}: {status} ({n})")
    return out, report
