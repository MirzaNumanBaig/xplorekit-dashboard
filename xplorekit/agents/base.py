"""Shared agent runner: shared rules + the agent's own prompt + the schema fields + candidates -> the model -> draft entries."""
import json

from xplorekit import llm
from xplorekit.common import ROOT, today
from xplorekit.verify.schema import load_schema

PROMPTS = ROOT / "xplorekit" / "prompts"
META = {"id", "section", "first_seen", "last_checked", "status", "quality_score", "verified"}


def field_help(section):
    """The writable fields of a section, as a compact list for the prompt (the schema is the single source of truth)."""
    sc = load_schema(section)
    return json.dumps({k: v for k, v in sc["properties"].items() if k not in META}, indent=1)


def candidate_block(cands, max_items=16):
    rows = []
    for i, c in enumerate(cands[:max_items], 1):
        rows.append({"n": i, "title": c["title"], "url": c["url"], "discussion_url": c.get("discussion_url"),
                     "snippet": c.get("snippet", ""), "details": (c.get("details") or "")[:4500] or None,
                     "chrome_web_store_links_found": c.get("store_urls") or None, "published": c.get("date", ""), "found_via": c.get("source_id", "")})
    return json.dumps(rows, indent=1, ensure_ascii=False)


def build_prompt(prompt_file, section, cands, n):
    shared = (PROMPTS / "_shared_rules.md").read_text("utf-8").replace("{{today}}", today())
    body = (PROMPTS / prompt_file).read_text("utf-8")
    return (f"{shared}\n\n{body}\n\n## Fields (JSON Schema)\n{field_help(section)}\n\n"
            f"## Task\nWrite up to {n} entries from these candidates. Fewer is fine; `[]` is fine.\n\n## Candidates\n{candidate_block(cands)}\n")


def run(prompt_file, section, cands, n):
    if not cands or n <= 0:
        return []
    reply = llm.complete(build_prompt(prompt_file, section, cands, n))
    out = llm.extract_json(reply, expect="array")
    if isinstance(out, dict):
        out = out.get("entries", [out])
    return [d for d in out if isinstance(d, dict)][:n]
