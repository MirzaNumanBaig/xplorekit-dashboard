# AGENTS.md: Xplorekit research pipeline (single source of truth)

Everything needed to run, change and extend this system is in this repository. There is no chat memory, no personal Claude account,
no MCP server and no other tool it depends on. Claude is used **only as the AI worker inside GitHub Actions**, through repository
secrets. Any person or AI tool can continue the work by reading this file. `CLAUDE.md` only imports it.

## What it does
Finds, verifies and rewrites content for four sections of the Xplorekit site (private repo `MirzaNumanBaig/xplorekit`, live at
xplorekit.online): **Make Money with AI** (highest priority), **Prompts**, **Chrome Extensions**, **Claude Skills**. Output is JSON in
`data/<section>/`; each run opens one rolling pull request on the site repo (`public/data/...`); a human merges it.

```
collectors -> prefilter (already on the site / already rejected / relevant) -> enrich (README, Web Store links)
  -> section agent (Claude writes drafts) -> Editor/Verifier -> data/ -> dashboard (docs/) + PR on the site repo
```

## Project goal and scope (updated)
The site's front end is to become three data-driven libraries, each filled by this pipeline: a **Prompt library** (grouped by job: marketing,
SEO, QA, web development and so on), a **Claude Skills library** and a **Chrome Extension library**. "Make Money with AI" stays a fourth section.
- Libraries are for the site visitor. Pages read `public/data/<section>/index.json` in the private site repo; no page may invent data.
- Done when: all three library pages are live on the site, show merged data, and the dashboard shows entries and Claude token usage.
- Open-source images are optional: use one only when its licence is clear and it is stored with the entry's source. Skipping is fine.
- Rollout: the owner checks the pages after the **first real run**; scheduled automatic runs are turned on only after that.
- `Researcher-agents` (celebrity news) is a workflow reference only. Never copy its data, names or sources.
- Status (2026-11-17): **built and proven end to end once.** Two real manual runs on 2026-11-16 used the Claude CLI with the OAuth token (token slot 1,
  0 AI failures) and saved real entries; the hand-off opened PR #76 on the site repo (open, not yet merged); the dashboard and the library pages are
  deployed on GitHub Pages and CI is green. Still pending: the owner's review and merge of PR #76, the three library pages on the private site, and
  turning on scheduled runs (see Known gaps).

## Where things are
| What | Where |
|---|---|
| Sources (all of them, no URLs in code) | `xplorekit/config/sources.json` |
| Caps, score floors, stale limits, income cap, pause switch, model | `xplorekit/config/settings.json` |
| Fields of each section | `xplorekit/schemas/<section>.schema.json` |
| What each AI agent is told | `xplorekit/prompts/*.md` (`_shared_rules.md` applies to all) |
| Collectors (HN, GitHub, RSS, Reddit API, YouTube, plain pages) | `xplorekit/collectors/` |
| Verifier rules (links, dedupe, income, hype, copy, schema) | `xplorekit/verify/`, `xplorekit/agents/editor_verifier.py` |
| Entry point | `xplorekit/run.py` |
| Hand-off to the site repo | `xplorekit/sync_site.py`, `scripts/open_site_pr.sh` |
| Dashboard (Overview, Entries, Rejected, Sources, Runs, Usage = Claude tokens per run; built to `docs/index.html`, GitHub Pages) | `xplorekit/build_dashboard.py`, `xplorekit/dashboard_template.html` |
| Cloud-session permission to attach the private site repo (owner-approved) | `.claude/settings.json` |
| Workflows | `.github/workflows/`: `research` (daily), `recheck` (weekly), `dashboard`, `tests` |
| Setup, how to add a source or a section | `GUIDE.md` |
| First dry run and its findings | `samples/REPORT.md` |

## How to operate it (all from GitHub)
- **Run now:** Actions -> Research -> Run workflow (`dry_run: true` writes nothing; `section`, `limit` optional).
- **Pause / resume:** set `"paused": true` or `false` in `settings.json`, or disable the workflow in Actions.
- **Change limits:** edit `settings.json` (caps, `min_quality_score`, `stale_after_days`, `max_realistic_monthly_income`).
- **Add / pause a source:** edit `sources.json` (see `GUIDE.md`). **Change agent behaviour:** edit the prompt file.
- **Look at results:** the dashboard (Pages), `data/`, `data/rejected/` (why things were turned away), `data/runs.json`.
- **Secrets** (Settings -> Secrets -> Actions): `CLAUDE_CODE_OAUTH_TOKEN` (+ `_2`, `_3` fallbacks, tried in order when one fails or is out of
  usage), optional `ANTHROPIC_API_KEY`, `SITE_REPO_TOKEN` (fine-grained, site repo only), optional `REDDIT_CLIENT_ID/SECRET`, `YOUTUBE_API_KEY`.
  Never commit a secret; never print one; error messages name token slots, not values.

## Content rules (they apply to every agent and to every human edit)
1. Only facts present in the collected source material. Never guess a price, date, feature, number or income figure.
2. Own words. Never copy more than 120 characters from a source. Always store the source URL.
3. **Income figures only when the cited source text itself states them**, copied exactly, never above the realistic cap. No "get rich quick",
   no guarantees, no passive-income promises. Risks and limits are mandatory in the Money section.
4. No popularity numbers (stars, users, downloads, ratings) anywhere: the site forbids them.
5. Respect robots.txt and site terms. Official APIs, RSS and public pages first. Reddit only through its official API. A site that refuses
   bots (403 or robots.txt) is not read, and nothing is claimed from it. Never spoof a browser to get around it.
6. Skipping is correct. Fewer, verified entries beat padded ones. A weak candidate is dropped, not rescued.
7. Prompts are never described as "tested" unless a test result exists.
8. The AI agents (Claude in the workflow) only write drafts. They never edit config, never approve their own output, never merge anything.
   The Editor/Verifier decides; a human merges the site PR.

## Quality gate (code, not opinion)
Schema -> duplicate (accepted, same batch, **already on the live site**: URL + title similarity) -> source link alive (GitHub repos via the raw README
host; HEAD falls back to GET) -> section rules (extension needs a live Chrome Web Store page; Money income and hype gate) -> verbatim-copy check ->
fact-check -> score (min of rule score and fact-check score). No independent fact-check = tagged `rules_only` and capped at 79, below the Money floor (80).

## How we work on this repo (people and AI tools)
- **Branch, test, merge, delete.** Build every change on a branch; run `python -m unittest discover -s tests` (all must pass); merge it to
  `main` yourself (fast-forward when possible) and delete the branch. Small commits with clear messages. No long-lived branches.
- **Cloud sessions cannot delete remote branches** (the sandbox proxy blocks both `git push --delete` and the GitHub API). So: build on a *local*
  branch, merge it locally (fast-forward), and push only `main`; never push a throwaway feature branch. If one was pushed, delete it on GitHub.
- **Other writers touch `main`:** the research bot commits `data/` and `docs/`, and other Claude sessions may be working here too (branches
  `claude/...`). Always `git fetch` and fast-forward or rebase before editing, and read the current files first; never overwrite someone else's change.
- Add or change behaviour together with a test. Tests are offline: no network, no model.
- Say plainly what was and was not verified. Never claim a live workflow, token or cross-repo push works until it has run.
- Do not add dependencies: the project is Python standard library only (plus the `claude` CLI inside the workflow).
- The repo is public: no secrets, no personal contact details, no private information in code, data, logs or commit messages.

## Known gaps (update this list; do not hide them)
- **Make Money produced 0 drafts in both real runs** (2026-11-16) even though it is the priority section: the agent returned nothing, or the candidates
  were filtered out. Not diagnosed yet. Check `data/runs.json` (`money.collected`, `fresh`, `drafts`) and `data/rejected/money.json`, then the sources
  (official platform rules pages work best; generic searches return noise) and the Money prompt.
- The three library pages on the **private site** do not exist yet; nothing there reads `public/data/` (separate work in the site repo, whose
  `CLAUDE.md` section "Research data feed" documents the rules). PR #76 on the site repo carries the first data and is waiting for the owner.
- **Schedule vs rollout rule:** `research.yml` has a daily cron (05:23 UTC), but the rollout rule above says automatic runs start only after the owner
  has checked the pages. Decide whether to disable the schedule (Actions -> Research -> Disable workflow) until then.
- Both real runs were started by hand; the scheduled path, the weekly `recheck` workflow and the `ANTHROPIC_API_KEY` / token-fallback (`_2`, `_3`)
  paths have not run for real yet.
- Medium and Upwork block bots, so nothing is claimed from them.

## Open owner decisions (asked 2026-11-17; use the safe default until answered)
1. **Byline for pipeline entries.** The site's standard byline says "Reviewed by Xplorekit's independent developer". Default: do not use it for feed
   entries unless the owner really reviewed the PR. Proposed: "Researched with AI, checked by Xplorekit".
2. **Income figures on Make Money pages.** Default: show none. The data keeps a figure only when the cited source states it.
3. **Auto-merge of the site PR.** Default: a human merges it (merging deploys to the live site).
