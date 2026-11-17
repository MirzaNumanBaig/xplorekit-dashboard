"""Build the dashboard: one self-contained page (docs/index.html) from this repo's own data. No server, no external libraries.

  python -m xplorekit.build_dashboard [--data-dir data] [--out docs]

Reads data/<section>/*.json, data/rejected/*.json, data/runs.json and xplorekit/config/*.json. GitHub Pages serves docs/.
The data is embedded in the page, so it also opens straight from disk.
"""
import argparse
import json
import sys
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

from xplorekit.common import ROOT, days_between, load_json, settings, sources, today

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


def health(runs, secs, day, site_pr=None):
    """Plain-language status lines, worst first."""
    out = []
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
    return {"generated_at": day, "repo": cfg["repo"], "site_repo": cfg["site_repo"], "site_url": cfg["site_url"], "sections": secs, "health": health(runs, secs, day, load_json(root / "site_pr.json", None)), "site_pr": load_json(root / "site_pr.json", None), "usage": usage(runs, day),
            "rejected": sorted(rejected, key=lambda r: r.get("date", ""), reverse=True)[:200], "runs": runs[-30:][::-1], "sources": src,
            "settings": {k: cfg[k] for k in ("caps", "min_quality_score", "stale_after_days", "title_similarity_threshold", "max_verbatim_overlap_chars", "max_realistic_monthly_income")},
            "model": cfg.get("llm", {}).get("model")}


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
