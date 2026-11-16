"""Build the three public library pages (prompts, skills, extensions) from data/<section>/*.json into docs/<section>/index.html.

  python -m xplorekit.build_libraries [--data-dir data] [--out docs]

Self-contained static pages (search, filter, copy). The data is embedded, so no server is needed. GitHub Pages serves them
next to the dashboard; the same files can be copied into the site repo.
"""
import argparse
import json
import sys
from pathlib import Path

from xplorekit.common import ROOT, load_json, settings

TEMPLATE = Path(__file__).with_name("library_template.html")
LIBRARIES = {
    "prompts": ("Prompt Library", "Ready-to-use AI prompts grouped by job."),
    "skills": ("Claude Skills Library", "Skills you can install for Claude, with steps."),
    "extensions": ("Chrome Extension Library", "Chrome extensions with pros, cons and pricing."),
}


def load(data_dir, section):
    d = Path(data_dir) / section
    items = [load_json(p) for p in sorted(d.glob("*.json")) if p.name != "index.json"] if d.exists() else []
    return [e for e in items if e and e.get("status", "active") != "stale"]


def render(section, entries):
    title, desc = LIBRARIES[section]
    pages = [{"id": "dashboard", "name": "Dashboard", "href": "../"}] + [
        {"id": s, "name": t, "href": f"../{s}/"} for s, (t, _) in LIBRARIES.items()]
    data = json.dumps(entries, ensure_ascii=False).replace("</", "<\\/")
    html = TEMPLATE.read_text("utf-8")
    for k, v in {"__TITLE__": title, "__DESC__": desc, "__SECTION__": section, "__DATA__": data, "__PAGES__": json.dumps(pages)}.items():
        html = html.replace(k, v)
    return html


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data-dir", default=str(ROOT / settings().get("data_dir", "data")))
    ap.add_argument("--out", default=str(ROOT / "docs"))
    a = ap.parse_args(argv)
    for section in LIBRARIES:
        out = Path(a.out) / section
        out.mkdir(parents=True, exist_ok=True)
        entries = load(a.data_dir, section)
        (out / "index.html").write_text(render(section, entries), "utf-8")
        print(f"wrote {out / 'index.html'} ({len(entries)} entries)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
