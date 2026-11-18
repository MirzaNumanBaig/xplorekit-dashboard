"""Rule-based quality gate: income claims, hype wording, verbatim copying, grounding in the source, staleness."""
import re
from difflib import SequenceMatcher

from xplorekit.common import days_between, settings, today

# Hype and guarantee wording that never belongs on a realistic "make money with AI" page.
BANNED = re.compile(
    r"get rich quick|guaranteed (income|profit|results|money)|passive income (on autopilot|while you sleep)|risk[- ]free|"
    r"no (work|effort|skills?) (needed|required)|quit your (9[- ]?to[- ]?5|job)|overnight (success|millionaire)|"
    r"\$\s?\d[\d,]*\s?k?\s?(a|per|/)\s?(day|week)\b|financial freedom|secret (method|formula)|100% (profit|success|automated)|become a millionaire",
    re.I)
NUM = re.compile(r"\d[\d,]*(?:\.\d+)?")
STOP = set("the and for with that this from your are you can will have has use using into more than about what when which their they them also each only other".split())


def text_of(entry, skip=("id", "section", "source_url", "source_urls", "first_seen", "last_checked", "status", "quality_score", "verified",
                         "store_url", "repo_url", "extension_last_updated", "income", "models", "difficulty", "pricing", "skill_type", "use_case", "ai_related")):
    parts = []
    for k, v in entry.items():
        if k in skip:
            continue
        if isinstance(v, str):
            parts.append(v)
        elif isinstance(v, list):
            parts += [x for x in v if isinstance(x, str)]
    return " \n".join(parts)


def hype_problems(entry):
    m = BANNED.search(text_of(entry))
    return [f"hype or guarantee wording: '{m.group(0)}'"] if m else []


def _numbers(text):
    out = set()
    for m in NUM.findall(text.replace("$", " ")):
        try:
            out.add(float(m.replace(",", "")))
        except ValueError:
            pass
    return out


def _monthly(inc, value):
    """Rough monthly figure for the cap check (hour -> 10 h/week part-time)."""
    return value * 40 if inc["period"] == "hour" else value


def income_problems(entry, source_text):
    """No invented numbers: a figure is allowed only when the source states it, and it must be in the source text."""
    inc = entry.get("income")
    if not inc:
        return []
    probs = []
    lo, hi = inc.get("low"), inc.get("high")
    if not inc.get("stated_in_source"):
        if lo is not None or hi is not None:
            probs.append("income numbers given but stated_in_source is false (invented number)")
        return probs
    if lo is None and hi is None:
        probs.append("stated_in_source is true but no numbers given")
        return probs
    if lo is not None and hi is not None and lo > hi:
        probs.append("income low is above high")
    if not source_text:
        probs.append("income figure cannot be verified: source text unavailable")
    else:
        found = _numbers(source_text)
        for label, v in (("low", lo), ("high", hi)):
            if v is not None and v not in found and not any(abs(v - f) < 0.5 for f in found):
                probs.append(f"income {label} ({v:g}) not found in the source text")
    cap = settings().get("max_realistic_monthly_income", 10000)
    for v in (lo, hi):
        if v is not None and inc.get("period") in ("month", "hour") and _monthly(inc, v) > cap:
            probs.append(f"income figure ({v:g}/{inc['period']}) above the realistic cap ({cap}/month)")
            break
    return probs


def longest_overlap(a, b, limit=20000):
    a, b = re.sub(r"\s+", " ", a.lower())[:limit], re.sub(r"\s+", " ", b.lower())[:limit]
    if not a or not b:
        return 0
    return SequenceMatcher(None, a, b, autojunk=False).find_longest_match(0, len(a), 0, len(b)).size


def copy_problems(entry, source_text):
    cap = settings().get("max_verbatim_overlap_chars", 120)
    n = longest_overlap(text_of(entry), source_text)
    return [f"{n} characters copied verbatim from the source (limit {cap})"] if n > cap else []


def _tokens(text):
    return {w for w in re.findall(r"[a-z][a-z0-9+#.-]{3,}", text.lower()) if w not in STOP}


def grounding_ratio(entry, source_text):
    """Share of the entry's distinctive words that also appear in the source: a crude 'is this about the source' check."""
    mine, theirs = _tokens(text_of(entry)), _tokens(source_text)
    return len(mine & theirs) / len(mine) if mine and theirs else 0.0


def relevant_excerpt(entry, source, limit=14000, chunk=500, head=1500):
    """For the fact-checker: the source in full when it fits, otherwise the start (what it is) plus the passages that mention the most words
    the draft's claims use (install commands, prices, steps), so a claim from deep in a long README can actually be checked.
    Excerpts are joined by ' ... '; neighbouring slices are joined seamlessly."""
    source = source or ""
    if len(source) <= limit:
        return source
    claim = _tokens(text_of(entry))
    parts = [source[i:i + chunk] for i in range(head // chunk * 0, len(source), chunk)]
    start = (head + chunk - 1) // chunk
    ranked = sorted(range(start, len(parts)), key=lambda i: len(claim & _tokens(parts[i])), reverse=True)
    budget = max(1, (limit - head) // chunk)
    keep = {i for i in ranked[: max(1, budget // 2)] if claim & _tokens(parts[i])}
    for i in list(keep):
        for j in (i - 1, i + 1):
            if start <= j < len(parts) and len(keep) < budget:
                keep.add(j)
    out, prev = "".join(parts[:start]), start - 1
    for i in sorted(keep):
        out += (parts[i] if i == prev + 1 else " ... " + parts[i])
        prev = i
    return out[:limit]


def age_days(entry):
    return days_between(entry.get("last_checked", today()), today())


def is_stale(section, entry):
    limit = settings().get("stale_after_days", {}).get(section, 120)
    age = age_days(entry)
    return age is not None and age > limit
