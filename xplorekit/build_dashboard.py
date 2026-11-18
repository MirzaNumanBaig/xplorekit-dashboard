"""Build the dashboard: one self-contained page (docs/index.html) from this repo's own data. No server, no external libraries.

  python -m xplorekit.build_dashboard [--data-dir data] [--out docs]

Reads data/<section>/*.json, data/rejected/*.json, data/runs.json and xplorekit/config/*.json. GitHub Pages serves docs/.
The data is embedded in the page, so it also opens straight from disk.
"""
import argparse
import json
import re
import sys
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

from xplorekit.common import ROOT, days_between, load_json, publish_mode, settings, sources, today

TEMPLATE = Path(__file__).with_name("dashboard_template.html")
SECTION_NAMES = {"money": "Make Money with AI", "prompts": "Prompts", "extensions": "Chrome Extensions", "skills": "Claude Skills"}


def extra(section, e):
    """The one or two section-specific facts worth showing in a table row."""
    if section == "money":
        inc = e.get("income", {})
        figure = "no figure stated" if not inc.get("stated_in_source") else f"{inc.get('low')}-{inc.get('high')} {inc.get('currency')}/{inc.get('period')} (per source)"
        return {"detail": f"{e.get('difficulty', '?')} · {figure}"}
    if section == "prompts":
        return {"detail": f"{e.get('use_case', '')} · {', '.join(e.get('models', []))}"}
    if section == "extensions":
        return {"detail": f"{e.get('pricing', '?')}{' · AI' if e.get('ai_related') else ''} · updated {e.get('extension_last_updated', 'unknown')}", "link2": e.get("store_url")}
    return {"detail": f"{e.get('skill_type', '')}", "link2": e.get("repo_url")}


def section_data(root, section, cfg, day):
    d = root / section
    entries = [load_json(p) for p in sorted(d.glob("*.json")) if p.name != "index.json"] if d.exists() else []
    entries = [e for e in entries if e]
    week_start = (date.fromisoformat(day) - timedelta(days=6)).isoformat()
    rej = load_json(root / "rejected" / f"{section}.json", [])
    rej7 = [r for r in rej if r.get("date", "") >= week_start]
    scores = [e["quality_score"] for e in entries]
    rows = [{"id": e["id"], "title": e.get("title") or e.get("name"), "summary": e.get("summary") or e.get("example_output_summary") or "", "url": e["source_url"],
             "score": e["quality_score"], "verified": e["verified"], "first_seen": e["first_seen"], "last_checked": e["last_checked"], "status": e["status"], **extra(section, e)}
            for e in sorted(entries, key=lambda e: (e["first_seen"], e["quality_score"]), reverse=True)]
    return {"key": section, "name": SECTION_NAMES.get(section, section), "entries": rows,
            "stats": {"total": len(entries), "active": sum(e["status"] == "active" for e in entries), "stale": sum(e["status"] == "stale" for e in entries),
                      "today": sum(e["first_seen"] == day for e in entries), "week": sum(e["first_seen"] >= week_start for e in entries),
                      "avg_score": round(sum(scores) / len(scores)) if scores else None, "rules_only": sum("rules_only" in e["verified"] for e in entries),
                      "rejected_week": len(rej7), "reasons_week": dict(Counter(r["reason"] for r in rej7))},
            "caps": {"daily": cfg["caps"]["daily"][section], "weekly": cfg["caps"]["weekly"][section]},
            "floor": cfg["min_quality_score"][section], "stale_after": cfg["stale_after_days"][section]}, [{**r, "section": section} for r in rej]


SECTION_PAGES = {"money": "/make-money-with-ai/", "prompts": "/prompts/", "skills": "/skills-directory/", "extensions": "/extensions-directory/"}
STATES = ("published", "pending", "draft", "stale", "rejected")
HIDDEN_FIELDS = {"id", "section", "source_url", "source_urls", "first_seen", "last_checked", "status", "quality_score", "verified", "title", "name"}
MAX_POSTS, MAX_REJECTED_POSTS = 400, 150


def fact_checked(e):
    return any(str(v).startswith("fact_check:") for v in e.get("verified", []))


def post_state(e, published):
    """published = delivered to the site and merged; pending = fact-checked, waiting for the next delivery; draft = saved but never
    fact-checked, so never delivered; stale = withdrawn (dead link or too old)."""
    if e.get("status") == "stale":
        return "stale"
    if not fact_checked(e):
        return "draft"
    rec = published.get(e["id"])
    return "published" if rec and not rec.get("withdrawn_at") else "pending"


REASONS = {"duplicate": "Already covered: the same thing is on the site or was accepted earlier.",
           "fact_check": "The AI fact-check found claims the source does not support.",
           "fact_check_failed": "The AI check could not run (an outage, not a content problem); it is retried.",
           "dead_link": "The source link did not open.", "money_gate": "Income claim not backed by the source.",
           "schema": "The entry was incomplete or malformed.", "low_quality": "Quality score below the minimum.",
           "copied_text": "Too much text copied from the source.", "hype": "Hype wording (guarantees, passive income, ...).",
           "ungrounded": "Not enough in the source to write it honestly.", "error": "A technical error while checking; retried."}


def reason_text(code):
    """Plain-English version of a rejection code (reverify_* = the same finding made on an older saved entry)."""
    code = code or ""
    base = code[len("reverify_"):] if code.startswith("reverify_") else code
    return REASONS.get(base, base.replace("_", " ") or "rejected")


def posts_data(root, cfg, published, rejected, site_url):
    """One row per saved entry plus recent rejections, each with everything the detail view shows."""
    posts = []
    for section in cfg["sections"]:
        d = root / section
        for p in sorted(d.glob("*.json")) if d.exists() else []:
            e = load_json(p) if p.name != "index.json" else None
            if not e:
                continue
            state = post_state(e, published)
            rec = published.get(e["id"]) or {}
            posts.append({"id": e["id"], "section": section, "section_name": SECTION_NAMES.get(section, section), "title": e.get("title") or e.get("name") or e["id"], "state": state,
                          "score": e["quality_score"], "first_seen": e["first_seen"], "last_checked": e["last_checked"],
                          "published_at": rec.get("published_at") if state == "published" else None, "pr": rec.get("pr") if state == "published" else None,
                          "source_url": e["source_url"], "source_urls": e.get("source_urls", []), "verified": e["verified"],
                          "live_url": f"{site_url}{SECTION_PAGES.get(section, '/')}#feed-{e['id']}" if state == "published" else None,
                          "summary": e.get("summary") or e.get("example_output_summary") or "",
                          "fields": {k: v for k, v in e.items() if k not in HIDDEN_FIELDS and v not in (None, "", [])}})
    posts.sort(key=lambda x: (x["published_at"] or x["first_seen"], x["score"]), reverse=True)
    posts = posts[:MAX_POSTS]
    for i, r in enumerate(sorted(rejected, key=lambda r: r.get("date", ""), reverse=True)[:MAX_REJECTED_POSTS]):
        posts.append({"id": f"rejected-{i}", "section": r["section"], "section_name": SECTION_NAMES.get(r["section"], r["section"]), "title": r.get("title") or r.get("url") or "(untitled)",
                      "state": "rejected", "score": None, "first_seen": r.get("date", ""), "last_checked": r.get("date", ""), "published_at": None, "pr": None, "source_url": r.get("url", ""),
                      "source_urls": [], "verified": [], "live_url": None, "summary": reason_text(r.get("reason")), "fields": {"why it was rejected": reason_text(r.get("reason")), "code": r.get("reason", ""), "detail": r.get("detail", "")}})
    return posts


def schedule_info():
    """The research schedule, read from the workflow file so the dashboard can never disagree with it: {minute, every_hours} or None."""
    try:
        text = (ROOT / ".github" / "workflows" / "research.yml").read_text("utf-8")
    except OSError:
        return None
    m = re.search(r'cron:\s*"(\d+)\s+\*/(\d+)\s+\*\s+\*\s+\*"', text)
    return {"minute": int(m.group(1)), "every_hours": int(m.group(2))} if m else None


def control_info(cfg):
    """What the dashboard's control bar shows and can change (the changing itself happens in the browser, through the GitHub API)."""
    return {"paused": bool(cfg.get("paused")), "publish_mode": publish_mode(), "schedule": schedule_info(), "repo": cfg["repo"], "workflow": "research.yml",
            "settings_path": "xplorekit/config/settings.json", "branch": "main"}


def health(runs, secs, day, site_pr=None):
    """Plain-language status lines, worst first."""
    out = []
    mode = publish_mode()
    if mode == "draft":
        out.append({"level": "warn", "text": "Publish mode is 'draft': research keeps running and saving, but nothing is sent to the site. Switch it to 'Published' in the bar above to go live."})
    elif mode == "pending":
        out.append({"level": "warn", "text": "Publish mode is 'pending': every delivery opens a pull request and waits for a person to merge it. Switch to 'Published' in the bar above to let it go live by itself."})
    if settings().get("paused"):
        out.append({"level": "warn", "text": "Research is paused: settings.json has \"paused\": true. Set it to false to resume."})
    research = [r for r in runs if r.get("type") == "research" and not r.get("dry_run")]
    if not research:
        out.append({"level": "warn", "text": "No research run recorded yet. Run it once from the Actions tab (Research, with dry_run first)."})
    else:
        last = research[-1]
        age = days_between(last["date"], day)
        if age is not None and age >= 3:
            out.append({"level": "bad", "text": f"The last research run was {age} days ago ({last['date']}). The daily schedule may be disabled or failing."})
        if last.get("provider") in (None, "none"):
            out.append({"level": "bad", "text": "The last run had no AI model configured, so no entries were written. Add CLAUDE_CODE_OAUTH_TOKEN (see Setup)."})
        failed = [k for k, v in last.get("sections", {}).items() if v.get("status") == "agent_failed"]
        if failed:
            out.append({"level": "bad", "text": f"The AI step failed in: {', '.join(failed)}. A token may be out of usage or expired."})
        llm = last.get("llm", {})
        if llm.get("failures"):
            out.append({"level": "warn", "text": f"{llm['failures']} AI call(s) failed in the last run; Claude token slot(s) used: {', '.join(map(str, llm.get('token_slots_used', []))) or 'none'}."})
    if site_pr:
        if site_pr.get("state") == "error":
            out.append({"level": "bad", "text": f"The last delivery to the site failed: {site_pr.get('reason', '')}"})
        elif site_pr.get("state") == "open_for_review":
            out.append({"level": "warn", "text": f"The last site update was NOT merged automatically (PR #{site_pr.get('pr')}): {site_pr.get('reason', '')}. A human needs to look."})
    for s in secs:
        if s["stats"]["rules_only"]:
            out.append({"level": "warn", "text": f"{s['name']}: {s['stats']['rules_only']} entr{'y' if s['stats']['rules_only'] == 1 else 'ies'} had no independent fact-check (rules_only). Read them before merging."})
        if s["stats"]["stale"]:
            out.append({"level": "warn", "text": f"{s['name']}: {s['stats']['stale']} stale entr{'y' if s['stats']['stale'] == 1 else 'ies'} (dead link or too old)."})
    if not out:
        out.append({"level": "ok", "text": "All good: the last run finished, the AI step worked and nothing needs attention."})
    order = {"bad": 0, "warn": 1, "ok": 2}
    return sorted(out, key=lambda x: order[x["level"]])


def usage(runs, day):
    """Claude token totals for today / 7 days / 30 days from the runs recorded in runs.json (real runs only)."""
    from datetime import date, timedelta
    d0 = date.fromisoformat(day)
    out = {k: {"input": 0, "output": 0, "cache_read": 0, "cache_creation": 0, "turns": 0, "cost_usd": 0.0, "runs": 0} for k in ("today", "7d", "30d")}
    for r in runs:
        t = (r.get("llm") or {}).get("tokens") or {}
        if r.get("dry_run") or not t:
            continue
        try:
            age = (d0 - date.fromisoformat(r["date"])).days
        except (KeyError, ValueError):
            continue
        for k, lim in (("today", 0), ("7d", 6), ("30d", 29)):
            if 0 <= age <= lim:
                o = out[k]
                o["runs"] += 1
                for f in ("input", "output", "cache_read", "cache_creation", "turns"):
                    o[f] += t.get(f, 0)
                o["cost_usd"] = round(o["cost_usd"] + t.get("cost_usd", 0), 4)
    return out


def build_dataset(data_dir):
    root, cfg, day = Path(data_dir), settings(), today()
    secs, rejected = [], []
    for s in cfg["sections"]:
        sd, rj = section_data(root, s, cfg, day)
        secs.append(sd)
        rejected += rj
    runs = load_json(root / "runs.json", [])
    published = load_json(root / "published.json", {})
    posts = posts_data(root, cfg, published, rejected, cfg["site_url"])
    for s in secs:
        s["stats"]["published"] = sum(1 for x in posts if x["section"] == s["key"] and x["state"] == "published")
        s["stats"]["pending"] = sum(1 for x in posts if x["section"] == s["key"] and x["state"] == "pending")
    last_src = {}
    for r in runs:
        for s, v in r.get("sections", {}).items():
            if v.get("sources"):
                last_src[s] = {x["id"]: x for x in v["sources"]}
    src = []
    for s, items in sources().items():
        if s.startswith("_"):
            continue
        for it in items:
            seen = last_src.get(s, {}).get(it["id"])
            src.append({"section": s, "id": it["id"], "type": it["type"], "enabled": it.get("enabled", True), "requires_key": it.get("requires_key", ""),
                        "last_status": seen["status"] if seen else None, "last_count": seen["count"] if seen else None})
    return {"generated_at": day, "repo": cfg["repo"], "site_repo": cfg["site_repo"], "site_url": cfg["site_url"], "sections": secs, "posts": posts, "post_counts": {st: sum(1 for x in posts if x["state"] == st) for st in STATES}, "health": health(runs, secs, day, load_json(root / "site_pr.json", None)), "site_pr": load_json(root / "site_pr.json", None), "usage": usage(runs, day),
            "rejected": sorted(rejected, key=lambda r: r.get("date", ""), reverse=True)[:200], "runs": runs[-30:][::-1], "sources": src,
            "settings": {k: cfg[k] for k in ("caps", "min_quality_score", "stale_after_days", "title_similarity_threshold", "max_verbatim_overlap_chars", "max_realistic_monthly_income")},
            "model": cfg.get("llm", {}).get("model"), "control": control_info(cfg)}


def render(dataset):
    blob = json.dumps(dataset, ensure_ascii=False).replace("<", "\\u003c")  # no "<" in the embedded JSON at all: nothing in the data can open or close a tag
    return TEMPLATE.read_text("utf-8").replace("/*__DATA__*/null", blob)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data-dir", default=str(ROOT / settings().get("data_dir", "data")))
    ap.add_argument("--out", default=str(ROOT / "docs"))
    a = ap.parse_args(argv)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "index.html").write_text(render(build_dataset(a.data_dir)), "utf-8")
    (out / ".nojekyll").write_text("")
    print(f"wrote {out / 'index.html'}")
    from xplorekit import build_libraries
    return build_libraries.main(["--data-dir", a.data_dir, "--out", a.out])


if __name__ == "__main__":
    sys.exit(main())
