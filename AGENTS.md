# AGENTS.md: Xplorekit research pipeline (single source of truth)

Everything needed to run, change and extend this system is in this repository. There is no chat memory, no personal Claude account,
no MCP server and no other tool it depends on. Claude is used **only as the AI worker inside GitHub Actions**, through repository
secrets. Any person or AI tool can continue the work by reading this file. `CLAUDE.md` only imports it.

## What it does
Finds, verifies and rewrites content for four sections of the Xplorekit site (private repo `MirzaNumanBaig/xplorekit`, live at
xplorekit.online): **Make Money with AI** (highest priority), **Prompts**, **Chrome Extensions**, **Claude Skills**. It runs **every 3 hours**
and **publishes by itself**: output is JSON in `data/<section>/`; every run renders the verified entries as cards inside the existing hub pages of
the site, runs safety checks, and merges the pull request on the site repo when they all pass (merging deploys to Cloudflare).

```
collectors -> prefilter (already on the site / already rejected / relevant) -> enrich (README, Web Store links, focused page excerpts)
  -> section agent (Claude writes drafts) -> Editor/Verifier (incl. a real fact-check) -> data/
  -> reverify older unchecked entries -> sync to the site repo -> site's build-feed.py renders cards -> safety checks -> auto-merge
  -> dashboard (docs/)
```

## Project goal and scope (updated)
The site's front end is to become three data-driven libraries, each filled by this pipeline: a **Prompt library** (grouped by job: marketing,
SEO, QA, web development and so on), a **Claude Skills library** and a **Chrome Extension library**. "Make Money with AI" stays a fourth section.
- Libraries are for the site visitor. Cards are built from `public/data/<section>/` in the private site repo by its `scripts/build-feed.py`; no page may invent data.
- Done when: the hub pages show merged, fact-checked cards, new items keep arriving every 3 hours without duplicates, and the dashboard shows entries and Claude token usage.
- Open-source images are optional: use one only when its licence is clear and it is stored with the entry's source. Skipping is fine.
- Rollout: **the owner approved scheduled runs and automatic publishing on 2026-11-17** (every 3 hours, auto-merge on).
- `Researcher-agents` (celebrity news) is a workflow reference only. Never copy its data, names or sources.
- Status (2026-11-17): the pipeline and dashboard are built. Two real manual runs on 2026-11-16 worked (Claude CLI via the OAuth token, real entries,
  hand-off opened PR #76 on the site repo). On 2026-11-17 these were fixed and the site-side card builder was added (see Known gaps for what is not yet
  proven live). Each entry has its own page at `/research/<section>/<id>` (built by the site's `build-feed.py`, owner decision 2026-11-18); the card on the existing hub page links to it.

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
| Hand-off to the site repo (sync, safety checks, PR, auto-merge) | `xplorekit/sync_site.py`, `xplorekit/site_pr.py` (cards: `scripts/build-feed.py` in the SITE repo) |
| Dashboard (**Overview** = status, last-run flow strip, sections; **Activity** = every run with the items saved/turned away and why; **Posts** = status dropdown + details of everything published, pending, draft, stale or rejected; Sources; Usage = Claude tokens per run; **How it works** = the whole flow in plain words with live numbers; Setup; built to `docs/index.html`, GitHub Pages) | `xplorekit/build_dashboard.py`, `xplorekit/dashboard_template.html` |
| Cloud-session permission to attach the private site repo (owner-approved) | `.claude/settings.json` |
| Workflows | `.github/workflows/`: `research` (every 3 hours), `recheck` (weekly), `dashboard`, `tests` |
| Setup, how to add a source or a section | `GUIDE.md` |
| First dry run and its findings | `samples/REPORT.md` |

## How to operate it (all from GitHub)
- **Schedule:** `research.yml` runs at minute 17 of every 3rd hour. `per_run_max` (1 per section) spreads the daily/weekly caps over the day's runs; a run
  whose section is already at its cap exits before spending any Claude tokens.
- **Run now:** Actions -> Research -> Run workflow (`dry_run: true` writes nothing; `section`, `limit` optional).
- **Pause / resume:** `"paused": true` or `false` in `settings.json`, or disable the workflow in Actions. Nothing is collected, written or published while paused.
- **Where new posts go (`"publish_mode"` in `settings.json`):** `"publish"` = delivered and merged by itself, live on the site; `"pending"` = a pull request opens and a
  person merges it; `"draft"` = research only, nothing is sent to the site. Anything unrecognised falls back to `"pending"`, never to publishing. Old files with
  `auto_merge_site` still work (true = publish, otherwise pending).
- **Dashboard control bar** (above the tabs, like the old researcher dashboard): shows "Runs every 3h" and the next run, **Pause / Resume** (sets `paused`), **Run now**
  (dispatches `research.yml`) and a **"New posts go to"** dropdown (sets `publish_mode`). It works by calling GitHub's API from the browser with a fine-grained token
  the owner pastes in (this repository only; Actions and Contents read/write; kept in `sessionStorage`, or `localStorage` only if "remember" is ticked). The page's
  Content-Security-Policy lets it contact **only `https://api.github.com`**, the token only ever travels as an `Authorization` header, and a change is a normal commit to
  `main` ("Dashboard: ..."), so it is visible and reversible in git history. A change applies from the next run. **Check token** tests each permission without changing anything
  visible; a refused action names the step, the permission and GitHub's own message (the usual cause: the repo is not selected for the token, or Contents/Actions is not Read and write).
- **Undo a published batch:** in the site repo, `git revert` the squash commit "Research feed: verified entries (<date>)" and push to `main`.
- **Change limits:** edit `settings.json` (caps, `per_run_max`, `min_quality_score`, `stale_after_days`, `max_realistic_monthly_income`, `near_duplicate`).
- **Add / pause a source:** edit `sources.json` (see `GUIDE.md`). **Change agent behaviour:** edit the prompt file.
- **Look at results:** the dashboard (Pages; its **Posts** tab has a Status dropdown: Published / Pending / Draft / Stale / Rejected, and each post opens into its full details with links to the live page and the pull request), `data/`, `data/rejected/` (why things were turned away), `data/runs.json`, `data/site_pr.json` (what the last delivery did), `data/published.json` (which entries went live, when, and in which pull request: written by `site_pr.py` only after a merge).
- **Secrets** (Settings -> Secrets -> Actions): `CLAUDE_CODE_OAUTH_TOKEN` (+ `_2`, `_3` fallbacks, tried in order when one fails or is out of
  usage), optional `ANTHROPIC_API_KEY`, `SITE_REPO_TOKEN` (fine-grained, site repo only: Contents + Pull requests read/write), optional `REDDIT_CLIENT_ID/SECRET`,
  `YOUTUBE_API_KEY`. Never commit a secret; never print one; error messages name token slots, not values.

## Content rules (they apply to every agent and to every human edit)
1. Only facts present in the collected source material. Never guess a price, date, feature, number or income figure.
2. Own words. Never copy more than 120 characters from a source. Always store the source URL.
3. **Income figures only when the cited source text itself states them**, copied exactly, never above the realistic cap. No "get rich quick",
   no guarantees, no passive-income promises. Risks and limits are mandatory in the Money section.
4. No popularity numbers (stars, users, downloads, ratings) anywhere: the site forbids them.
   Cards carry the byline "Researched with AI, checked by Xplorekit" (owner decision), never "Reviewed by"; Make Money cards show an income figure only when the source states it, attributed.
5. Respect robots.txt and site terms. Official APIs, RSS and public pages first. Reddit only through its official API. A site that refuses
   bots (403 or robots.txt) is not read, and nothing is claimed from it. Never spoof a browser to get around it.
6. Skipping is correct. Fewer, verified entries beat padded ones. A weak candidate is dropped, not rescued.
7. Prompts are never described as "tested" unless a test result exists.
8. The AI agents (Claude in the workflow) only write drafts. They never edit config, never approve their own output, never merge anything.
   The Editor/Verifier decides; a human merges the site PR.

## Quality gate (code, not opinion)
Schema -> duplicate (see "No duplicates") -> source link alive (GitHub repos via the raw README host; HEAD falls back to GET) -> section rules (extension
needs a live Chrome Web Store page; Money income and hype gate) -> verbatim-copy check -> **fact-check** (the model checks every claim against the source
text; an unreadable answer is retried once, then the draft is rejected as `fact_check_failed`, never published unchecked) -> score (min of rule score and
fact-check score). An entry stored without an independent fact-check is tagged `rules_only`, capped at 79 (below the Money floor, 80), **never delivered to
the site**, and is re-run through the whole gate by `python -m xplorekit.run --reverify` (it earns a real fact-check or is removed).

## No duplicates (decided 2026-11-17; enforced in code at four places)
1. **Identity, not just URL:** one key per thing: a GitHub repo (`owner/repo`, any spelling), a Chrome Web Store extension id (any slug or host), else the cleaned URL.
2. **Against everything known:** entries already accepted, the rest of the batch, **other sections** (a skill is not also an extension), data already delivered to
   the site (`public/data`), and the hand-written site pages (their `<h1>` and outbound links).
3. **Wording, only where there is no unique id:** prompts (title overlap >= 0.4 or prompt-text overlap >= 0.33) and money ideas (title overlap >= 0.5). Shared generic words
   do NOT make two extensions or skills duplicates (their store id / repo decides). Thresholds: `settings.json` -> `near_duplicate`.
4. **Again at render time:** the site's `scripts/build-feed.py` applies the same identity and wording rules and shows each thing once.

## Publishing safety (what must pass before the pipeline merges by itself)
`xplorekit/site_pr.py` (in `publish_mode` `"publish"` only) merges the pull request only if ALL of these pass: only `public/data/`, the entry pages, the sitemap and the hub pages (the four hubs plus the homepage) changed; the change is not unusually
large (`auto_merge_max_files`, default 120); only `public/data/`, `public/research/` (the entry pages), `public/sitemap.xml` and the four hub pages changed; the hub pages (homepage included) and the sitemap changed only inside the generated feed blocks (the homepage's are `feed:home_prompts`, `feed:home_extensions`, `feed:home_skills`, `feed:home_money`); every entry has a `fact_check:*` tag and no popularity-count
field; the site's `scripts/build-feed.py --check` passes. Otherwise the pull request stays open with the failed checks listed, and the dashboard shows a warning.

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
- **Auto-publish is proven live (2026-11-17/18).** The site's `main` has "Research feed: verified entries" commits from the pipeline (2026-11-17 02:02 and 2026-11-18 07:57 UTC),
  `data/published.json` records what went live, and the cards are visible on the real hub pages (extensions, prompts, skills). Still unproven: a delivery that fails a safety
  check (it should stay open and show a warning), `publish_mode` `pending`/`draft` in a real run, and the dashboard control bar against the real GitHub API (it is tested only
  against a faked one).
- **Everything saved before 2026-11-17 was stored without a fact-check** (`rules_only`): fact-check replies were parsed as the wrong piece of JSON and silently
  dropped. Fixed (and covered by a regression test). Those entries are held back from the site; `--reverify` runs on every research run and either gives them a real
  fact-check or removes them.
- **Make Money had no live entries (checked 2026-11-18).** Cause: its sources were product-launch feeds, newsletters and essays (almost nothing that describes a way to earn), plus rules pages, so the writer correctly returned nothing; Hacker News returned 0 (queries too long). Fix: sources are now programme pages where the platform states how people earn (YouTube Partner Programme, AdSense, KDP royalties, Shopify partners, Gumroad, Outlier, DataAnnotation, Etsy, Respondent, User Interviews) plus broader HN queries, and the writer prompt says such pages are valid sources (one idea per page, income only if the page states it). Not yet seen in a real run (no model access outside Actions). Medium and Upwork block bots, so nothing is claimed from them.
- **Make Money status (2026-11-18).** Still no pipeline-published Make Money entry. Meanwhile the site has five hand-written plans; two were added on 2026-11-18 (YouTube Partner Programme with AI, Etsy digital downloads and AI rules), written only from the platforms' own help pages. They are not in `data/`, so the dashboard does not list them. Plan: add a `YOUTUBE_API_KEY` secret (owner creates it in Google Cloud, YouTube Data API v3, restricted to that API) to find ideas and embeddable creator videos; facts must still come from the official programme page, and a creator's income claims are never repeated as fact. Reddit API access needs approval under Reddit's Responsible Builder Policy (requested by the owner, not granted yet); the pipeline works without it. Neither key has been tested in a real run.
- **Token use at a 3-hour cadence is unknown.** The first real runs cost roughly 1 USD API-equivalent each. Watch the dashboard's Usage tab; tune `per_run_max` or the caps
  if usage runs high.
- The scheduled path, the weekly `recheck` workflow, the token fallback (`_2`, `_3`) and the `ANTHROPIC_API_KEY` path have not run for real yet.
- Open question for the owner: should the site's `robots.txt` disallow `/data/` (the raw JSON)?
- **Rejection fixes (2026-11-18).** `--reverify` used to judge duplicate partners against each other (both deleted) and delete an entry when the AI check merely crashed; the fact-checker also saw only the first 6,000 characters of a long page. Now: entries are judged one at a time against entries that are staying (one of a duplicate pair always survives); `fact_check_failed`, `error` and `dead_link` leave the entry untouched to retry; the checker gets the page start plus the passages relevant to the draft (~14,000 chars). The Posts tab shows a plain-English reason per rejection. Five wrongly removed entries were restored from git (they re-run through reverify). Not yet seen in a real run.

- **Dashboard reworked (2026-11-18).** Tabs: Overview, Activity, Posts, Sources, Usage, How it works, Setup (the old Rejected and Runs tabs are folded into Posts and Activity; the control bar shows on Overview and Setup only). `run.py` now records the titles saved and turned away per run (`accepted_items`, `rejected_items` in `data/runs.json`); runs before this change show counts only. A published post links to its own page `/research/<section>/<id>`.

- **Library layout (2026-11-18).** The site's hub pages are now filterable libraries (site repo, `scripts/build-feed.py`). The extension scout prompt and schema accept optional `account` and `open_source` (only when the source states them); the site shows "not stated" otherwise. `permissions` is not collected yet, so the "Permissions" check is empty for pipeline entries. The pipeline's safety check is unchanged: a delivery still changes only `public/data/`, `public/research/`, the sitemap, and the generated blocks of the hub pages and the homepage.

## Roadmap split (owner request 2026-11-18): done now on the site, and later work for this pipeline
**Done now (site repo, live):** one filter and one grid on `/extensions-directory/` (three columns; researched extensions join the hand-picked list, category "Newly researched"); "Last updated" at the top of the extensions, skills and prompts pages = the day something was last ADDED (newest `first_seen` of an entry, or `scripts/hand-updated.json` for hand-written ones), generated inside the feed block, so this pipeline's PRs keep it current; byline "by the Xplorekit team"; a hand-written prompt library on `/prompts/` (34 prompts in 8 fields, each with an output: camera diagrams for image and video prompts), where researched prompts join the same grid (`feed:prompts_items`, `feed:prompts_chip`, which the safety check treats as feed blocks); guide pages use the full width. The prompt hunter prompt now asks for field-specific, useful prompts (see `xplorekit/prompts/prompt_hunter.md`).
**Later (needs code and tests here, not started):**
1. Prompt schema: add a `field` (image, video, code-review, agents, website, writing, copywriting, fitness, ...) and an optional `output` (text) so cards can show an output and the site can group by field instead of the current `use_case` list. Update `schemas/prompts.schema.json`, the verifier, the fact-check and `build-feed.py` together.
2. New sources for field prompts (official prompt guides of the image and video tools, the vendors' own prompting documentation). Add them in `sources.json`; never copy a prompt longer than 120 characters.
3. Make Money: `YOUTUBE_API_KEY` (and Reddit, if approved) to find ideas and embeddable creator videos; facts only from the official programme page; never repeat a creator's income claim as a fact; one guide a day only if each passes the fact-check.
4. Dashboard: a Posts filter by field and a "hand-written" count, once the schema has `field`.
5. Skills: a "Last updated" per category from its newest skill, and one filter for the skills page like extensions (not done; skills still has the rail plus its own grid).

## Owner decisions
Decided 2026-11-17: cards go **inside the existing hub pages**; byline "Researched with AI, checked by Xplorekit"; Make Money cards **show income figures only when the
source states them**, attributed; the pipeline **merges by itself** (safety checks above); **no duplicates**; schedule **every 3 hours**.
Decided 2026-11-18: final UI (new type and logo, sliders of the latest entries on the home page and hub pages, Copy button on prompts; the homepage's feed blocks are generated and allowed by the safety check). Decided 2026-11-17/18 (later): the site UI is redesigned ("clean product directory"); the homepage's third tile is Prompts; the dashboard has a Posts tab and a control bar.
Still open: whether `/data/` is hidden from search engines.
