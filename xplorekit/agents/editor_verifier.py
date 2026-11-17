"""Editor / Verifier: the shared quality gate. Turns agent drafts into accepted entries or logged rejections.

Order of checks (cheapest first): schema -> duplicate (accepted, live site, this batch) -> source link alive -> section rules
(extension store link, income and hype gate for money) -> verbatim-copy check -> fact check (model or manual verdicts) -> score.
Everything that can be decided by code is decided by code; the model is only used for the judgement calls.
"""
import hashlib
import re

from xplorekit import llm
from xplorekit.enrich import github_repo, readme_plain
from xplorekit.common import (ROOT, host_of, http_get, normalize_url, readable_text, settings, slugify, today)
from xplorekit.verify import dedupe, links, rules
from xplorekit.verify.schema import load_schema, validate

META = ("id", "section", "first_seen", "last_checked", "status", "quality_score", "verified")
MONTHS = ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"]


class Context:
    """Everything the review needs, injectable so tests need no network and no model."""

    def __init__(self, existing=None, site_known=None, snippets=None, link_check=None, fetch_text=None, fact_check=None, fact_check_name="llm"):
        self.existing = existing or []          # accepted entries of this section already on disk
        self.site_known = site_known or []      # [{title, urls, where}] already on the live site
        self.snippets = snippets or {}          # normalized url -> text collected earlier
        self.link_check = link_check or links.check
        self.fetch_text = fetch_text or default_fetch_text
        self.fact_check = fact_check            # callable(section, entry, source_text) -> {supported, score, issues} or None
        self.fact_check_name = fact_check_name
        self.link_cache = {}
        self.text_cache = {}


def default_fetch_text(url):
    gh = github_repo(url)
    if gh:
        return readme_plain(*gh)
    try:
        code, body = http_get(url, max_bytes=1_500_000)  # Chrome Web Store pages are large; the "Updated" date sits late in the HTML
    except Exception:
        return ""
    return readable_text(body)[:20000] if code == 200 else ""


def llm_fact_check(section, entry, source_text):
    """Ask the model to verify the draft against the source text. Returns a verdict dict, or None when no model is configured.
    When a model IS configured, an unreadable answer is retried once and then raised: it must never silently become 'no fact-check'."""
    if not llm.available():
        return None
    import json
    prompt = (ROOT / "xplorekit" / "prompts" / "editor_verifier.md").read_text("utf-8")
    prompt = prompt.replace("{{section}}", section).replace("{{draft}}", json.dumps({k: v for k, v in entry.items() if k not in META}, ensure_ascii=False, indent=1)).replace("{{source}}", source_text[:6000] or "(empty)")
    last = None
    for _ in range(2):
        try:
            v = llm.extract_json(llm.complete(prompt), expect="object")
        except llm.LLMError as e:
            last = e
            continue
        if isinstance(v, dict) and isinstance(v.get("supported"), bool) and isinstance(v.get("score"), (int, float)):
            return v
        last = llm.LLMError("fact-check answer is missing 'supported' or 'score'")
    raise llm.LLMError(f"fact-check unreadable after a retry: {last}")


def make_id(entry):
    title = entry.get("title") or entry.get("name") or "item"
    h = hashlib.sha1(normalize_url(entry["source_url"]).encode()).hexdigest()[:6]
    return f"{slugify(title, 60)}-{h}"


def finalize(section, draft):
    """Strip anything the schema does not allow, then add the Editor-owned fields."""
    props = load_schema(section)["properties"]
    e = {k: v for k, v in draft.items() if k in props and k not in META}
    urls = [u for u in e.get("source_urls", []) if isinstance(u, str)]
    if isinstance(e.get("source_url"), str) and e["source_url"] not in urls:
        urls.insert(0, e["source_url"])
    e["source_urls"] = urls
    e.update({"section": section, "first_seen": today(), "last_checked": today(), "status": "active", "quality_score": 0, "verified": []})
    if isinstance(e.get("source_url"), str):
        e["id"] = make_id(e)
    return e


def source_text(entry, ctx):
    """Text the claims are checked against: the collector's snippet (README, teaser) PLUS the fetched full page, for every source URL.
    A collector snippet is only a teaser, so the page itself is always read too; GitHub URLs read the README (see default_fetch_text)."""
    texts = []
    for u in dict.fromkeys(entry["source_urls"] + [entry.get(f) for f in ("store_url", "repo_url") if entry.get(f)]):
        n = normalize_url(u)
        if n not in ctx.text_cache:
            ctx.text_cache[n] = ctx.fetch_text(u)
        texts += [ctx.snippets.get(n, ""), ctx.text_cache[n]]
    return "\n".join(t for t in texts if t)


def check_link(url, ctx):
    n = normalize_url(url)
    if n not in ctx.link_cache:
        ctx.link_cache[n] = ctx.link_check(url)
    return ctx.link_cache[n]


def date_supported(date, text):
    """An extension 'last updated' date is kept only when the source text shows that year and month."""
    m = re.match(r"(\d{4})-(\d{2})-\d{2}$", date or "")
    if not m or not text:
        return False
    y, mo = m.group(1), int(m.group(2))
    low = text.lower()
    return y in low and (f"{y}-{mo:02d}" in low or MONTHS[mo - 1] in low or MONTHS[mo - 1][:3] in low)


def review_one(section, draft, ctx, batch_known):
    """Return ('accepted', entry) or ('rejected', {reason, detail, title, url})."""
    cfg = settings()
    entry = finalize(section, draft)
    title = entry.get("title") or entry.get("name") or ""
    rej = lambda reason, detail="": ("rejected", {"reason": reason, "detail": detail, "title": title, "url": entry.get("source_url", "")})

    errs = validate(entry, load_schema(section))
    if errs:
        return rej("schema", "; ".join(errs[:4]))
    verified = ["schema"]

    dup = dedupe.find_duplicate(entry, dedupe.known_from_entries(ctx.existing, "accepted entry") + ctx.site_known + batch_known,
                                by_url=section in cfg.get("url_dedupe_sections", []))
    if dup:
        return rej("duplicate", dup)
    verified.append("not_duplicate")

    # source link must be alive; for extensions the Chrome Web Store link must be alive too
    statuses = {u: check_link(u, ctx) for u in entry["source_urls"]}
    if entry.get("store_url"):
        st = check_link(entry["store_url"], ctx)
        if not links.usable(st[0]):
            return rej("dead_link", f"store link: {st[0]} {st[1] or ''}")
        verified.append("store_link_live")
    best = [s for s, _ in statuses.values() if links.usable(s)]
    if not best:
        return rej("dead_link", "; ".join(f"{u} -> {s} {c or ''}" for u, (s, c) in statuses.items()))
    verified.append("link_live" if "ok" in best else "link_live_bot_blocked")

    text = source_text(entry, ctx)
    if section == "extensions" and entry.get("extension_last_updated", "unknown") != "unknown" and not date_supported(entry["extension_last_updated"], text):
        entry["extension_last_updated"] = "unknown"
        verified.append("last_updated_unverified_set_unknown")

    if section == "money":
        probs = rules.hype_problems(entry) + rules.income_problems(entry, text)
        if probs:
            return rej("money_gate", "; ".join(probs))
        verified.append("income_grounded" if entry["income"]["stated_in_source"] else "no_income_figure")
    else:
        probs = rules.hype_problems(entry)
        if probs:
            return rej("hype", "; ".join(probs))

    probs = rules.copy_problems(entry, text)
    if probs:
        return rej("copied_text", "; ".join(probs))
    verified.append("no_verbatim_copy")

    ratio = rules.grounding_ratio(entry, text) if text else 0.0
    if text and ratio < 0.04 and section != "prompts":  # prompts are original writing, so low overlap with a source is expected
        return rej("ungrounded", f"only {ratio:.0%} of its wording relates to the source")

    # rule-based score out of 100
    score = 40 + (15 if "ok" in best else 8)
    score += 10 if host_of(entry["source_url"]) in set(cfg.get("trusted_hosts", [])) else 0
    score += min(20, int(ratio * 60)) if section != "prompts" else 12
    score += 10 if len(rules.text_of(entry)) >= 300 else 0

    try:
        verdict = ctx.fact_check(section, entry, text) if ctx.fact_check else None
    except llm.LLMError as e:  # the model was there but its check failed: reject, never publish unchecked
        return rej("fact_check_failed", str(e)[:200])
    if verdict:
        if not verdict.get("supported", False):
            return rej("fact_check", "; ".join(map(str, verdict.get("issues", []))) or "not supported by the source")
        score = min(score, int(verdict.get("score", 0)))
        verified.append(f"fact_check:{ctx.fact_check_name}")
    else:
        score = min(score, 79)  # nothing independent checked the claims: stays below the Money bar (80)
        verified.append("rules_only")

    entry["quality_score"] = max(0, min(100, score))
    entry["verified"] = verified
    floor = cfg.get("min_quality_score", {}).get(section, 70)
    if entry["quality_score"] < floor:
        return rej("low_quality", f"score {entry['quality_score']} below {floor}" + ("" if verdict else " (no fact-check ran)"))
    return "accepted", entry


def review(section, drafts, ctx):
    accepted, rejected, batch_known = [], [], []
    for d in drafts:
        try:
            status, res = review_one(section, d, ctx, batch_known)
        except Exception as e:  # one broken draft must not stop the batch
            status, res = "rejected", {"reason": "error", "detail": f"{type(e).__name__}: {e}"[:200], "title": str(d.get("title") or d.get("name") or ""), "url": str(d.get("source_url", ""))}
        if status == "accepted":
            accepted.append(res)
            batch_known += dedupe.known_from_entries([res], "another entry in this batch")
        else:
            rejected.append(res)
    return accepted, rejected
