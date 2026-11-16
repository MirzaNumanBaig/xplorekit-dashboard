"""Reddit through the OFFICIAL OAuth API only (reddit.com's robots.txt disallows crawling). Needs REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET."""
import base64
import json
import os
import urllib.parse

from xplorekit.common import http_get, user_agent


def collect(src):
    auth = base64.b64encode(f"{os.environ['REDDIT_CLIENT_ID']}:{os.environ['REDDIT_CLIENT_SECRET']}".encode()).decode()
    status, body = http_get("https://www.reddit.com/api/v1/access_token", method="POST", data=b"grant_type=client_credentials",
                            headers={"Authorization": f"Basic {auth}", "Content-Type": "application/x-www-form-urlencoded"}, check_robots=False)
    if status != 200:
        raise RuntimeError(f"Reddit auth HTTP {status}")
    token = json.loads(body)["access_token"]
    out = []
    for sub in src.get("subreddits", []):
        url = f"https://oauth.reddit.com/r/{sub}/top?{urllib.parse.urlencode({'t': src.get('window', 'week'), 'limit': 15})}"
        status, body = http_get(url, {"Authorization": f"Bearer {token}"})
        if status != 200:
            continue
        for c in json.loads(body)["data"]["children"]:
            d = c["data"]
            out.append({"title": d["title"], "url": d.get("url_overridden_by_dest") or f"https://www.reddit.com{d['permalink']}",
                        "discussion_url": f"https://www.reddit.com{d['permalink']}", "snippet": (d.get("selftext") or "")[:500],
                        "date": "", "score": d.get("score", 0), "extra": {"subreddit": sub}})
    return out
