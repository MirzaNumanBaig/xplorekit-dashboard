# How to run, add a source, add a section

## 1. One-time setup (about 10 minutes)

**Secrets and variables** (this repo → Settings → Secrets and variables → Actions):

| Name | Kind | What it is |
|---|---|---|
| `CLAUDE_CODE_OAUTH_TOKEN` | secret | the same Claude Code token the celebrity repo used (secrets do not carry over between repos; add it again) |
| `SITE_REPO_TOKEN` | secret | fine-grained token for the private site repo, see below |
| `ANTHROPIC_API_KEY` | secret, optional | alternative to the OAuth token; wins if both are set |
| `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`, `YOUTUBE_API_KEY` | secrets, optional | each source is skipped when its key is missing |
| `XK_CONTACT` | variable, optional | a URL or email added to our User-Agent so site owners can reach you |

**Create `SITE_REPO_TOKEN`** (only you can do this, from your GitHub account):
1. GitHub → your avatar → Settings → Developer settings → Personal access tokens → **Fine-grained tokens** → Generate new token.
2. Resource owner: your account. Repository access: **Only select repositories** → the private site repo (`xplorekit`) and nothing else.
3. Repository permissions: **Contents: Read and write**, **Pull requests: Read and write**. Metadata (read) is added automatically.
4. Set an expiry you will remember (for example 90 days), generate, copy the token, and paste it as the `SITE_REPO_TOKEN` secret here.

**Allow the workflow to push**: this repo → Settings → Actions → General → Workflow permissions → *Read and write*.

## 2. Run it
- **Automatically:** `research.yml` runs daily; `recheck.yml` runs weekly (re-checks links, flags stale entries).
- **By hand:** Actions → *Research* → *Run workflow*. Use `dry_run: true` the first time: it writes to `.dryrun/` and commits nothing.
- **Locally:** `python -m xplorekit.run --section money --dry-run --site-dir ../xplorekit` (needs `claude` CLI + token, or an API key).
- **Review:** each run opens (or updates) **one** pull request on the site repo from the branch `feed/xplorekit-research`. It lists every new entry with its
  source, score and checks. Merge it to publish the data; Cloudflare deploys as it does for any merge to `main`.
- **Caps** (daily/weekly per section), score floors, stale-after days and the income cap live in `xplorekit/config/settings.json`.

Useful flags: `--limit N`, `--section money|prompts|extensions|skills|all`, `--collect-only`, `--use-cache`,
`--drafts-file F` (skip the agent and verify drafts you wrote), `--verdicts-file F` (manual fact-check verdicts), `--recheck`.

## 3. Add a new source
Edit `xplorekit/config/sources.json` only. Add an object to the section's list:
```json
{"id": "my-feed", "type": "rss", "enabled": true, "url": "https://example.com/feed.xml"}
```
Types: `hn` (queries), `github` (search queries), `rss` / `producthunt_rss` (url), `reddit` (subreddits, needs keys), `youtube` (queries, needs key),
`webpage` (urls: official docs/help pages). Set `"requires_key": "ENV_NAME"` to skip it when the key is absent, `"enabled": false` to pause it.
robots.txt is enforced automatically. A source that fails is reported and skipped, never fatal. Only a brand-new *type* needs code:
add `xplorekit/collectors/<type>.py` with `collect(src) -> [{title, url, snippet, date, score, extra}]` and register it in `collectors/__init__.py`.
Official help and rules pages (`webpage`) make the best Money sources: they are verifiable and honest about limits.
If a site refuses bots (403) or disallows them in robots.txt, the pipeline will not read it, so it cannot ground claims from it.

## 4. Add a new section
1. `xplorekit/schemas/<section>.schema.json`: copy an existing one and change the fields (keep the shared metadata block).
2. `xplorekit/prompts/<agent>.md`: the agent's instructions (the shared rules in `_shared_rules.md` are added automatically).
3. `xplorekit/agents/<agent>.py`: copy one of the four (5 lines) and set `SECTION`/`PROMPT_FILE`; register it in `agents/__init__.py`.
4. `xplorekit/config/settings.json`: add the section to `sections`, `caps`, `min_quality_score`, `stale_after_days`, and `relevance_keywords`.
5. `xplorekit/config/sources.json`: add its sources. `xplorekit/site_known.py`: add where the site keeps that section's pages (for dedupe).
6. Add a sample draft to `tests/helpers.py` and run the tests.

## 5. Where the data lands on the site
`public/data/<section>/<id>.json` plus `public/data/<section>/index.json` and a manifest `public/data/index.json`
(served at `/data/...`). The folder is fully generated: do not hand-edit it. The site's pages must read these files
(a build script that renders marker blocks, as `scripts/build-hub.py` does, or client-side fetch for sliders). That rendering step is separate work.
