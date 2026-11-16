"""What the live site already has, read from a checkout of the private site repo, so the pipeline never re-discovers it.
Reads: public/extensions-directory/index.json + */*.html, public/skills-directory/*/*.html, public/make-money-with-ai/*.html and
public/data/<section>/*.json (items the pipeline delivered earlier). Titles come from each page's H1, URLs from its outbound links.
"""
import re
from pathlib import Path

from xplorekit.common import host_of, load_json, normalize_url, strip_html

CHROME_HOSTS = {"fonts.googleapis.com", "fonts.gstatic.com", "linkedin.com", "xplorekit.online", "googletagmanager.com", "schema.org", "w3.org"}
SECTION_DIRS = {"extensions": ["extensions-directory/*/*.html"], "skills": ["skills-directory/*/*.html", "codex/index.html"],
                "money": ["make-money-with-ai/*.html"], "prompts": ["prompts/index.html"]}


def _page(path):
    html = path.read_text("utf-8", "replace")
    m = re.search(r"(?is)<h1[^>]*>(.*?)</h1>", html)
    title = strip_html(m.group(1)) if m else ""
    urls = {normalize_url(u) for u in re.findall(r'href="(https?://[^"#]+)"', html) if host_of(u) not in CHROME_HOSTS}
    return title, urls


def load(site_dir):
    """Return {section: [{title, urls:set, where}]}. Missing folders simply give empty lists."""
    pub = Path(site_dir) / "public"
    out = {s: [] for s in SECTION_DIRS}
    for section, globs in SECTION_DIRS.items():
        for g in globs:
            for p in sorted(pub.glob(g)):
                if p.name == "index.html" and section in ("extensions", "money"):
                    continue
                title, urls = _page(p)
                out[section].append({"title": title, "urls": urls, "where": f"site page {p.relative_to(pub)}"})
    idx = load_json(pub / "extensions-directory" / "index.json", {})
    for e in idx.get("extensions", []):
        out["extensions"].append({"title": e.get("name", ""), "urls": set(), "where": f"site extension {e.get('url', '')}"})
    return out
