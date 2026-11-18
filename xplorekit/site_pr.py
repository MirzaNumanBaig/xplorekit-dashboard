"""Deliver the research feed to the private site repo and, when every safety check passes, publish it.

  python -m xplorekit.site_pr --site-dir site --body pr.md      env: GH_TOKEN (site repo token), SITE_REPO (owner/name)

Order: (1) the site's own scripts/build-feed.py renders the cards into its hub pages; (2) only the allowed paths are staged on ONE rolling
branch (feed/xplorekit-research); (3) safety checks; (4) commit, push, open or update the pull request; (5) if settings.publish_mode is
"publish" AND every check passed, squash-merge it (the site deploys on merge to main); otherwise the PR stays open for a human with the reason in
its description. The outcome is written to data/site_pr.json for the dashboard.
"""
import argparse
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from xplorekit.common import ROOT, load_json, publish_mode, save_json, settings, today

BRANCH = "feed/xplorekit-research"
SITEMAP = "public/sitemap.xml"  # may change only inside its feed block
HUB_PAGES = {"public/make-money-with-ai/index.html", "public/prompts/index.html", "public/skills-directory/index.html", "public/extensions-directory/index.html"}
BLOCK = re.compile(r"<!-- feed:\w+:start.*?<!-- feed:\w+:end -->", re.S)
FORBIDDEN_KEYS = {"stars", "star_count", "users", "user_count", "downloads", "download_count", "ratings", "rating", "reviews", "review_count"}


def git(site, *args, check=True):
    r = subprocess.run(["git", "-c", "user.name=xplorekit-research-bot", "-c", "user.email=xplorekit-research-bot@users.noreply.github.com", *args],
                       cwd=site, capture_output=True, text=True)
    if check and r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args[:2])} failed: {r.stderr.strip()[:200]}")
    return r.stdout


def git_ok(site, *args):
    return subprocess.run(["git", "-c", "user.name=xplorekit-research-bot", "-c", "user.email=xplorekit-research-bot@users.noreply.github.com", *args], cwd=site, capture_output=True).returncode == 0


def api(method, path, body=None):
    """GitHub REST call with the site-repo token. Returns (status, parsed_json_or_None)."""
    req = urllib.request.Request(f"https://api.github.com{path}", method=method, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Authorization": f"Bearer {os.environ['GH_TOKEN']}", "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "xplorekit-research-bot"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            raw = r.read()
            return r.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read() or b"null")
        except ValueError:
            return e.code, None


# ---- safety checks: each returns None (ok) or a short reason ----------------------------------------------------------------------------
def check_paths(files):
    bad = [f for f in files if not (f.startswith(("public/data/", "public/research/")) or f in HUB_PAGES or f == SITEMAP)]
    return f"unexpected files changed: {', '.join(bad[:4])}" if bad else None


def check_size(files):
    limit = settings().get("auto_merge_max_files", 120)
    return f"{len(files)} files changed (limit {limit})" if len(files) > limit else None


def check_pages_outside_blocks(site, files):
    """The hub pages may change only inside the generated feed blocks. Compare the text outside them with main's version."""
    squash = lambda t: re.sub(r"\s+", "", BLOCK.sub("", t))
    for f in files:
        if f in HUB_PAGES or f == SITEMAP:
            try:
                old = git(site, "show", f"origin/main:{f}")
            except RuntimeError:
                return f"{f} could not be read from main"
            if squash(old) != squash((Path(site) / f).read_text("utf-8")):
                return f"{f} changed outside the generated feed block"
    return None


def check_data(site, files):
    for f in files:
        if f.startswith("public/data/") and f.endswith(".json") and Path(site, f).exists() and not f.endswith("/index.json") and f != "public/data/index.json":
            try:
                e = json.loads(Path(site, f).read_text("utf-8"))
            except ValueError:
                return f"{f} is not valid JSON"
            if not any(str(v).startswith("fact_check:") for v in e.get("verified", [])):
                return f"{f} has no fact-check"
            if FORBIDDEN_KEYS & {k.lower() for k in e}:
                return f"{f} contains a popularity-count field"
    return None


def check_build(site):
    r = subprocess.run([sys.executable, "scripts/build-feed.py", "--check"], cwd=site, capture_output=True, text=True)
    return None if r.returncode == 0 else "the site's build-feed.py --check failed: " + (r.stdout + r.stderr).strip()[-160:]


def run_checks(site, files):
    results = [("only the data folder and the four hub pages changed", check_paths(files)), ("change size is normal", check_size(files)),
               ("nothing outside the generated blocks moved", check_pages_outside_blocks(site, files)),
               ("every entry carries a fact-check and no popularity counts", check_data(site, files)),
               ("the site's own page check passes", check_build(site))]
    return results


# ---- the flow ----------------------------------------------------------------------------------------------------------------------------
def checks_text(results):
    return "\n".join(f"- {'PASS' if why is None else 'FAIL'}: {name}" + ("" if why is None else f" ({why})") for name, why in results)


def entries_in(changes, kinds):
    """[{section, id}] for the entry files (public/data/<section>/<id>.json) whose change kind is in `kinds`."""
    out = []
    for path, kind in changes.items():
        m = re.match(r"public/data/(\w+)/([^/]+)\.json$", path)
        if kind in kinds and m and m.group(2) != "index":
            out.append({"section": m.group(1), "id": m.group(2)})
    return out


def record_published(out_dir, outcome):
    """Keep data/published.json: which entries went live on the site, when, and in which pull request. Only a merged delivery counts."""
    if outcome.get("state") != "merged":
        return
    path = Path(out_dir) / "published.json"
    book = load_json(path, {})
    for e in outcome.get("delivered", []):
        rec = book.get(e["id"]) or {}
        book[e["id"]] = {"section": e["section"], "published_at": rec.get("published_at") or outcome["date"], "pr": rec.get("pr") or outcome.get("pr"), "withdrawn_at": None}
    for e in outcome.get("withdrawn", []):
        if e["id"] in book:
            book[e["id"]]["withdrawn_at"] = outcome["date"]
    save_json(path, book)


def deliver(site, body_path, repo):
    """Returns the outcome dict. Never raises for an expected failure: it records why a human is needed."""
    out = {"date": today(), "time": datetime.now(timezone.utc).isoformat(timespec="seconds"), "state": "error", "reason": "", "pr": None, "files": 0}
    mode = publish_mode()
    if mode == "draft":  # research only: the site repo is not touched at all
        out.update(state="held_as_draft", reason="publish mode is 'draft': nothing is sent to the site")
        return out
    build = subprocess.run([sys.executable, "scripts/build-feed.py"], cwd=site, capture_output=True, text=True)
    if build.returncode != 0:
        out["reason"] = "the site's build-feed.py failed: " + (build.stdout + build.stderr).strip()[-160:]
        return out
    git(site, "checkout", "-B", BRANCH, "origin/main")
    git(site, "add", "-A", *[x for x in ("public/data", "public/research", SITEMAP, *sorted(HUB_PAGES)) if (Path(site) / x).exists()])
    changes = {}  # path -> A / M / D
    for line in git(site, "diff", "--cached", "--name-status").splitlines():
        status, _, path = line.partition("\t")
        if path:
            changes[path] = status[:1]
    files = list(changes)
    out["files"] = len(files)
    if not files:
        out.update(state="nothing_new", reason="nothing new for the site")
        return out
    results = run_checks(site, files)
    failed = [why for _, why in results if why]
    body = Path(body_path).read_text("utf-8") if Path(body_path).exists() else "Automated research update."
    will_merge = mode == "publish" and not failed
    note = ("This pull request merges itself because every safety check passed." if will_merge else
            "**This pull request was NOT merged automatically** " + ("(publish mode is 'pending': a person merges)." if not failed else "because a safety check failed. A human needs to look.") + "\n")
    body = f"{body}\n\n### Safety checks\n{checks_text(results)}\n\n{note}"
    git(site, "commit", "-q", "-m", f"Research feed: update verified entries ({today()})")
    if not git_ok(site, "push", "-q", "--force-with-lease", "origin", BRANCH):  # the rolling branch is ours alone, so a plain force is the fallback
        git(site, "push", "-q", "--force", "origin", BRANCH)
    st, prs = api("GET", f"/repos/{repo}/pulls?state=open&head={repo.split('/')[0]}:{BRANCH}")
    if st == 200 and prs:
        number = prs[0]["number"]
        api("PATCH", f"/repos/{repo}/pulls/{number}", {"body": body})
    else:
        st, pr = api("POST", f"/repos/{repo}/pulls", {"title": "Research feed: new verified entries", "head": BRANCH, "base": "main", "body": body})
        if st not in (200, 201):
            out["reason"] = f"could not open the pull request (HTTP {st})"
            return out
        number = pr["number"]
    out["pr"] = number
    if failed:
        out.update(state="open_for_review", reason="; ".join(failed))
        return out
    if not will_merge:
        out.update(state="open_for_review", reason="publish mode is 'pending': a person merges it")
        return out
    st, res = api("PUT", f"/repos/{repo}/pulls/{number}/merge", {"merge_method": "squash", "commit_title": f"Research feed: verified entries ({today()})"})
    if st == 200 and (res or {}).get("merged"):
        api("DELETE", f"/repos/{repo}/git/refs/heads/{BRANCH}")  # the rolling branch is recreated by the next run
        out.update(state="merged", reason="", delivered=entries_in(changes, ("A", "M")), withdrawn=entries_in(changes, ("D",)))
    else:
        out.update(state="open_for_review", reason=f"merge refused (HTTP {st}): {((res or {}).get('message') or '')[:120]}")
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--site-dir", required=True)
    ap.add_argument("--body", default="pr.md")
    ap.add_argument("--repo", default=os.environ.get("SITE_REPO") or settings()["site_repo"])
    ap.add_argument("--out", default=str(ROOT / settings().get("data_dir", "data")))
    a = ap.parse_args(argv)
    out = deliver(a.site_dir, a.body, a.repo)
    save_json(Path(a.out) / "site_pr.json", {k: v for k, v in out.items() if k not in ("delivered", "withdrawn")})
    record_published(a.out, out)
    print(json.dumps(out))
    return 1 if out["state"] == "error" else 0


if __name__ == "__main__":
    sys.exit(main())
