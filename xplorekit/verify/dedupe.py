"""Dedupe by one identity per thing (GitHub repo, Chrome Web Store id, URL), by title similarity, and for prompts by wording overlap.
Checked against everything accepted, the rest of the batch, the other sections, and everything already on the live site."""
from xplorekit.common import canon_key, jaccard, settings, title_similarity

URL_FIELDS = ("source_url", "store_url", "repo_url")


def entry_urls(entry):
    urls = {canon_key(u) for u in entry.get("source_urls", [])}
    for f in URL_FIELDS:
        if entry.get(f):
            urls.add(canon_key(entry[f]))
    return urls


def entry_title(entry):
    return entry.get("title") or entry.get("name") or ""


def find_duplicate(entry, known, by_url=True):
    """known: list of {title, urls:set of canon keys, where, text?, url_only?}. Returns a reason string or None."""
    cfg = settings()
    threshold = cfg.get("title_similarity_threshold", 0.85)
    nd = cfg.get("near_duplicate", {})
    urls = entry_urls(entry)
    title = entry_title(entry)
    is_prompt = "prompt" in entry
    for k in known:
        if by_url and urls & k["urls"]:
            return f"same URL as {k['where']}"
        if k.get("url_only"):
            continue
        if title and k["title"]:
            if title_similarity(title, k["title"]) >= threshold:
                return f"title too similar to {k['where']} ('{k['title'][:50]}')"
            # Extensions and skills have a unique identity (store id / repo), so shared generic words ("summary", "ChatGPT") prove nothing.
            if (is_prompt or "income" in entry) and jaccard(title, k["title"]) >= nd.get("prompt_title_jaccard" if is_prompt else "title_jaccard", 0.5):
                return f"same words in the title as {k['where']} ('{k['title'][:50]}')"
        if is_prompt and k.get("text") and jaccard(entry["prompt"], k["text"]) >= nd.get("prompt_text_jaccard", 0.33):
            return f"prompt wording overlaps {k['where']} ('{k['title'][:50]}')"
    return None


def known_from_entries(entries, where="accepted entry", url_only=False):
    return [{"title": entry_title(e), "urls": entry_urls(e), "where": where, "text": e.get("prompt"), "url_only": url_only} for e in entries]
