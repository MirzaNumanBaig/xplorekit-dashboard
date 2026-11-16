"""Hacker News via the official Algolia search API (no key)."""
import json
import time
import urllib.parse

from xplorekit.common import http_get

API = "https://hn.algolia.com/api/v1/search"


def collect(src, days=30):
    out, since = [], int(time.time()) - days * 86400
    for q in src.get("queries", []):
        params = {"query": q, "tags": "story", "hitsPerPage": 10, "numericFilters": f"points>{src.get('min_points', 20)},created_at_i>{since}"}
        status, body = http_get(f"{API}?{urllib.parse.urlencode(params)}")
        if status != 200:
            continue
        for h in json.loads(body).get("hits", []):
            hn = f"https://news.ycombinator.com/item?id={h['objectID']}"
            out.append({"title": h.get("title") or "", "url": h.get("url") or hn, "discussion_url": hn,
                        "snippet": (h.get("story_text") or "")[:600], "date": (h.get("created_at") or "")[:10],
                        "score": h.get("points", 0), "extra": {"comments": h.get("num_comments", 0)}})
    return out
