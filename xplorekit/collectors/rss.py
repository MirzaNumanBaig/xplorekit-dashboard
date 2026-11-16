"""RSS/Atom feeds (official blogs, newsletters, Product Hunt's public feed). robots.txt is checked by http_get."""
import re
import xml.etree.ElementTree as ET

from xplorekit.common import http_get, strip_html


def _text(el, *names):
    for n in names:
        for child in el.iter():
            if child.tag.split("}")[-1] == n and (child.text or child.attrib.get("href")):
                return (child.text or "").strip() or child.attrib.get("href", "")
    return ""


def _items(xml_text, limit):
    """Parse the whole document; if it is truncated or malformed, salvage the complete <item>/<entry> blocks."""
    try:
        root = ET.fromstring(xml_text)
        return [e for e in root.iter() if e.tag.split("}")[-1] in ("item", "entry")][:limit]
    except ET.ParseError:
        out = []
        for m in re.finditer(r"<(item|entry)\b.*?</\1>", xml_text, re.S):
            block = re.sub(r"<(/?)[\w.-]+:", r"<\1", m.group(0))  # drop namespace prefixes so each block parses alone
            block = re.sub(r"\s[\w.-]+:[\w.-]+=(\"[^\"]*\"|'[^']*')", "", block)
            try:
                out.append(ET.fromstring(block))
            except ET.ParseError:
                continue
            if len(out) >= limit:
                break
        return out


def parse(xml_text, limit=15):
    out = []
    for item in _items(xml_text, limit):
        link = ""
        for child in item:
            if child.tag.split("}")[-1] == "link":
                link = child.attrib.get("href") or (child.text or "").strip()
                if link:
                    break
        title = _text(item, "title")
        body = _text(item, "description", "summary", "content", "encoded")
        date = re.search(r"\d{4}-\d{2}-\d{2}", _text(item, "published", "updated", "pubDate", "date"))
        out.append({"title": strip_html(title), "url": link, "snippet": strip_html(body)[:500], "date": date.group(0) if date else "", "score": 0, "extra": {}})
    return [o for o in out if o["title"] and o["url"]]


def collect(src):
    status, body = http_get(src["url"])
    if status != 200:
        raise RuntimeError(f"HTTP {status}")
    return parse(body, src.get("limit", 15))
