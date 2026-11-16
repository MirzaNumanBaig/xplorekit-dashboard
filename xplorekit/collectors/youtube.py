"""YouTube Data API v3 search. Needs YOUTUBE_API_KEY; skipped otherwise."""
import json
import os
import urllib.parse

from xplorekit.common import http_get

API = "https://www.googleapis.com/youtube/v3/search"


def collect(src):
    out = []
    for q in src.get("queries", []):
        params = {"part": "snippet", "q": q, "type": "video", "maxResults": 8, "order": "viewCount", "key": os.environ["YOUTUBE_API_KEY"]}
        status, body = http_get(f"{API}?{urllib.parse.urlencode(params)}")
        if status != 200:
            continue
        for it in json.loads(body).get("items", []):
            sn = it["snippet"]
            out.append({"title": sn["title"], "url": f"https://www.youtube.com/watch?v={it['id']['videoId']}", "snippet": sn.get("description", "")[:500],
                        "date": sn.get("publishedAt", "")[:10], "score": 0, "extra": {"channel": sn.get("channelTitle")}})
    return out
