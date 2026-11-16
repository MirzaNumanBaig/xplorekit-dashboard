"""Single public pages (docs, README files). One polite GET each, robots.txt respected. Only a short snippet is kept."""
import re

from xplorekit.common import http_get, readable_text, strip_html


def collect(src):
    out = []
    for url in src.get("urls", []):
        status, body = http_get(url)
        if status != 200:
            continue
        m = re.search(r"(?is)<title[^>]*>(.*?)</title>", body)
        title = strip_html(m.group(1)) if m else url.rsplit("/", 1)[-1]
        text = body if url.endswith((".md", ".txt")) else readable_text(body)
        out.append({"title": title, "url": url, "snippet": re.sub(r"\s+", " ", text)[:1500], "date": "", "score": 0, "extra": {}})
    return out
