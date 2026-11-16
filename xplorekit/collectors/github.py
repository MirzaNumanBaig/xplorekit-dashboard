"""GitHub repository search through the official API. GITHUB_TOKEN is optional (raises the rate limit)."""
import json
import os
import urllib.parse

from xplorekit.common import http_get

API = "https://api.github.com/search/repositories"


def collect(src):
    headers = {"Accept": "application/vnd.github+json"}
    if os.environ.get("GITHUB_TOKEN"):
        headers["Authorization"] = f"Bearer {os.environ['GITHUB_TOKEN']}"
    out = []
    for q in src.get("queries", []):
        status, body = http_get(f"{API}?{urllib.parse.urlencode({'q': q, 'sort': 'stars', 'order': 'desc', 'per_page': 10})}", headers)
        if status != 200:
            continue
        for r in json.loads(body).get("items", []):
            if r.get("archived") or r.get("fork"):
                continue
            out.append({"title": r["full_name"], "url": r["html_url"], "snippet": (r.get("description") or "")[:500],
                        "date": (r.get("pushed_at") or "")[:10], "score": r.get("stargazers_count", 0),
                        "extra": {"license": (r.get("license") or {}).get("spdx_id"), "topics": r.get("topics", [])[:8], "homepage": r.get("homepage")}})
    return out
