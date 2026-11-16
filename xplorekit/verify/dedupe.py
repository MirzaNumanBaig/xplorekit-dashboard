"""Dedupe by normalised URL and by title similarity, against what is already accepted AND what the live site already has."""
from xplorekit.common import normalize_url, settings, title_similarity

URL_FIELDS = ("source_url", "store_url", "repo_url")


def entry_urls(entry):
    urls = {normalize_url(u) for u in entry.get("source_urls", [])}
    for f in URL_FIELDS:
        if entry.get(f):
            urls.add(normalize_url(entry[f]))
    return urls


def entry_title(entry):
    return entry.get("title") or entry.get("name") or ""


def find_duplicate(entry, known):
    """known: list of dicts {title, urls:set, where}. Returns a reason string or None."""
    threshold = settings().get("title_similarity_threshold", 0.85)
    urls = entry_urls(entry)
    title = entry_title(entry)
    for k in known:
        if urls & k["urls"]:
            return f"same URL as {k['where']}"
        if title and k["title"] and title_similarity(title, k["title"]) >= threshold:
            return f"title too similar to {k['where']} ('{k['title'][:50]}')"
    return None


def known_from_entries(entries, where="accepted entry"):
    return [{"title": entry_title(e), "urls": entry_urls(e), "where": where} for e in entries]
