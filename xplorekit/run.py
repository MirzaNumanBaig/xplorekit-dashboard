"""Entry point.

  python -m xplorekit.run --section money --dry-run             collect + agent + Editor, write to .dryrun/ only
  python -m xplorekit.run --section all                          the scheduled run: writes data/<section>/*.json
  python -m xplorekit.run --section skills --drafts-file d.json  skip the agent; run the Editor on drafts you wrote
  python -m xplorekit.run --recheck                              re-check links of saved entries, mark stale ones
Options: --limit N (max new entries per section), --site-dir PATH (checkout of the site repo, for 'already on the site' dedupe),
         --verdicts-file F (manual fact-check verdicts, JSON), --use-cache, --collect-only, --out DIR
"""
import argparse
import json
import sys
from datetime import date, timedelta

from xplorekit import agents, enrich, llm, site_known
from xplorekit.agents import editor_verifier as editor
from xplorekit.collectors import collect_section
from xplorekit.common import ROOT, load_json, normalize_url, save_json, settings, today
from xplorekit.verify import dedupe, links, rules

CACHE = ROOT / ".cache" / "candidates"


def data_root(out):
    return (ROOT / out) if out else ROOT / settings().get("data_dir", "data")


def load_entries(root, section):
    d = root / section
    return [load_json(p) for p in sorted(d.glob("*.json")) if p.name != "index.json"] if d.exists() else []


def cap_room(section, existing, limit=None):
    caps = settings()["caps"]
    t = today()
    week_start = (date.fromisoformat(t) - timedelta(days=6)).isoformat()
    day_n = sum(1 for e in existing if e.get("first_seen") == t)
    week_n = sum(1 for e in existing if e.get("first_seen", "") >= week_start)
    room = min(caps["daily"][section] - day_n, caps["weekly"][section] - week_n)
    return max(0, min(room, limit) if limit else max(0, room))


def diversify(cands):
    """Rank inside each source, then interleave sources, so one huge source (GitHub stars) cannot crowd out the rest."""
    by = {}
    for c in cands:
        by.setdefault(c.get("source_id", ""), []).append(c)
    for v in by.values():
        v.sort(key=lambda c: (c.get("score", 0), c.get("date", "")), reverse=True)
    out = []
    while any(by.values()):
        for k in list(by):
            if by[k]:
                out.append(by[k].pop(0))
    return out


def prefilter(cands, section, existing, known, rejected):
    seen = set()
    if section in settings().get("url_dedupe_sections", []):  # prompts may legitimately share one source page
        seen = {normalize_url(u) for e in existing for u in dedupe.entry_urls(e)} | {u for k in known for u in k["urls"]}
    seen |= {normalize_url(r["url"]) for r in rejected if r.get("url") and r.get("date", "") >= (date.fromisoformat(today()) - timedelta(days=30)).isoformat()}
    out, got = [], set()
    for c in cands:
        n = normalize_url(c["url"])
        if not c["url"].startswith("http") or n in seen or n in got:
            continue
        got.add(n)
        out.append(c)
    return out


def save(root, section, accepted, rejected, dry=False):
    d = root / section
    for e in accepted:
        save_json(d / f"{e['id']}.json", e)
    entries = load_entries(root, section)
    entries.sort(key=lambda e: (e["first_seen"], e["quality_score"]), reverse=True)
    save_json(d / "index.json", {"section": section, "generated_at": today(), "items": [
        {"id": e["id"], "title": e.get("title") or e.get("name"), "summary": e.get("summary") or e.get("example_output_summary") or e.get("use_case", ""),
         "url": e["source_url"], "first_seen": e["first_seen"], "last_checked": e["last_checked"], "status": e["status"], "quality_score": e["quality_score"]} for e in entries]})
    if rejected:
        rp = root / "rejected" / f"{section}.json"
        log = load_json(rp, [])
        log = (log + [{**r, "date": today()} for r in rejected])[-500:]
        save_json(rp, log)


def make_fact_checker(verdicts_file):
    if verdicts_file:
        verdicts = load_json(verdicts_file, {})
        def manual(section, entry, text):
            return verdicts.get(normalize_url(entry["source_url"])) or verdicts.get(entry["id"]) or verdicts.get(entry["source_url"])
        return manual, "manual"
    return editor.llm_fact_check, "llm"


def process_section(section, args, log=print):
    root = data_root(args.out)
    existing = load_entries(root, section)
    rejected_log = load_json(root / "rejected" / f"{section}.json", [])
    known = site_known.load(args.site_dir)[section] if args.site_dir else []
    snippets, cands = {}, []

    if args.drafts_file:
        drafts = [d for d in load_json(args.drafts_file, []) if d.get("section", section) == section or "section" not in d]
        cached = load_json(CACHE / f"{section}.json", []) + load_json(CACHE / f"{section}.enriched.json", [])
        for c in cached:  # later (enriched) rows add their README text to the earlier snippet
            n = normalize_url(c["url"])
            snippets[n] = (snippets.get(n, "") + " " + c.get("snippet", "") + " " + c.get("details", "")).strip()
    else:
        room = cap_room(section, existing, args.limit)
        if room == 0:
            log(f"[{section}] cap reached for today/this week: nothing to do")
            return 0, 0
        if args.use_cache and (CACHE / f"{section}.json").exists():
            cands = load_json(CACHE / f"{section}.json")
        else:
            cands, _ = collect_section(section, log)
            save_json(CACHE / f"{section}.json", cands)
        if args.collect_only:
            log(f"[{section}] collected {len(cands)} candidates (cached)")
            return 0, 0
        cands = diversify([c for c in prefilter(cands, section, existing, known, rejected_log) if enrich.relevant(c, section)])
        cands = enrich.enrich(cands, section)
        save_json(CACHE / f"{section}.enriched.json", cands)  # lets a later --drafts-file run verify against the same text
        snippets = {normalize_url(c["url"]): (c.get("snippet", "") + " " + c.get("details", "")).strip() for c in cands}
        log(f"[{section}] {len(cands)} relevant fresh candidates, room for {room} new entries")
        if not llm.available():
            log(f"[{section}] no language model configured (set CLAUDE_CODE_OAUTH_TOKEN or ANTHROPIC_API_KEY): agent skipped")
            return 0, 0
        drafts = agents.AGENTS[section].run(cands, room)
        log(f"[{section}] {agents.AGENTS[section].NAME} wrote {len(drafts)} draft(s)")

    fact, fact_name = make_fact_checker(args.verdicts_file)
    ctx = editor.Context(existing=existing, site_known=known, snippets=snippets, fact_check=fact, fact_check_name=fact_name)
    accepted, rejected = editor.review(section, drafts, ctx)
    room = cap_room(section, existing, args.limit) if not args.drafts_file else len(accepted)
    if len(accepted) > room:  # best first, the rest wait for tomorrow
        accepted.sort(key=lambda e: e["quality_score"], reverse=True)
        accepted = accepted[:room]
    save(data_root(args.out), section, accepted, rejected)
    for e in accepted:
        log(f"  + {e['quality_score']:>3}  {(e.get('title') or e.get('name'))[:70]}  [{', '.join(e['verified'])}]")
    for r in rejected:
        log(f"  - REJECTED ({r['reason']}): {r['title'][:50]}  {r['detail'][:110]}")
    return len(accepted), len(rejected)


def recheck(args, log=print):
    """Re-check every saved entry: refresh last_checked when its source still answers, mark it stale when dead or too old."""
    root = data_root(args.out)
    for section in settings()["sections"]:
        changed = False
        for e in load_entries(root, section):
            st, _ = links.check(e["source_url"])
            if links.usable(st):
                e["last_checked"] = today()
                e["status"] = "stale" if rules.is_stale(section, {**e, "last_checked": e["first_seen"]}) else "active"
            else:
                e["status"] = "stale"
            save_json(root / section / f"{e['id']}.json", e)
            changed = True
            log(f"  [{section}] {e['id']}: {st} -> {e['status']}")
        if changed:
            save(root, section, [], [])


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--section", default="all")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--dry-run", action="store_true", help="write to .dryrun/ instead of data/ (unless --out is given)")
    ap.add_argument("--out")
    ap.add_argument("--site-dir")
    ap.add_argument("--drafts-file")
    ap.add_argument("--verdicts-file")
    ap.add_argument("--use-cache", action="store_true")
    ap.add_argument("--collect-only", action="store_true")
    ap.add_argument("--recheck", action="store_true")
    args = ap.parse_args(argv)
    if args.dry_run and not args.out:
        args.out = ".dryrun"
    if args.recheck:
        recheck(args)
        return 0
    sections = settings()["sections"] if args.section == "all" else [args.section]
    total_a = total_r = 0
    for s in sections:
        if s not in agents.AGENTS:
            print(f"unknown section '{s}'", file=sys.stderr)
            return 2
        a, r = process_section(s, args)
        total_a += a
        total_r += r
    print(f"done: {total_a} accepted, {total_r} rejected" + (f" (written to {args.out}/)" if args.out else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
