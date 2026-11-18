# How to run, add a source, add a section

## 1. One-time setup (about 10 minutes)

**Secrets and variables** (this repo → Settings → Secrets and variables → Actions):

| Name | Kind | What it is |
|---|---|---|
| `CLAUDE_CODE_OAUTH_TOKEN` | secret | your Claude Code token (secrets do not carry over between repos; add it here). Optional `CLAUDE_CODE_OAUTH_TOKEN_2` and `_3` are tried in order when one fails or runs out of usage |
| `SITE_REPO_TOKEN` | secret | fine-grained token for the private site repo, see below |
| `ANTHROPIC_API_KEY` | secret, optional | alternative to the OAuth token; wins if both are set |
| `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`, `YOUTUBE_API_KEY` | secrets, optional | each source is skipped when its key is missing |
| `XK_CONTACT` | variable, optional | a URL or email added to our User-Agent so site owners can reach you |

**Get the Claude token (`CLAUDE_CODE_OAUTH_TOKEN`)** (only you can do this: it is tied to your Claude account, and nobody else, including an AI tool, can create or read it):
1. You need a paid Claude plan that includes Claude Code (Pro or Max). The agents use that plan's usage, so a heavy run can hit its limit; this is why the pipeline accepts a second and third token as fallbacks.
2. On any computer, install Node.js 18+ and the CLI: `npm install -g @anthropic-ai/claude-code`.
3. Run `claude setup-token` in a terminal. It opens a browser page: sign in to Claude and click **Authorize**.
4. The terminal then prints a long-lived token that starts with `sk-ant-oat01-`. Copy it at once; it is shown only one time (run the command again to get a new one).
5. GitHub → this repo → Settings → Secrets and variables → Actions → **New repository secret**. Name: `CLAUDE_CODE_OAUTH_TOKEN`. Value: the token. Save.
6. Optional fallbacks: repeat with a second Claude account and save it as `CLAUDE_CODE_OAUTH_TOKEN_2` (and `_3`). They are tried in this order when one fails or is out of usage.
7. Never paste the token into chat, an issue, a file or a commit. If it leaks, revoke it in your Claude account settings and run `claude setup-token` again.
8. Test it: Actions → *Research* → *Run workflow* with `dry_run: true`. The log names the token slot that worked (never its value).
Alternative without a subscription: an API key from console.anthropic.com saved as `ANTHROPIC_API_KEY` (pay per use; wins if both are set).

**Create `SITE_REPO_TOKEN`** (only you can do this, from your GitHub account):
1. GitHub → your avatar → Settings → Developer settings → Personal access tokens → **Fine-grained tokens** → Generate new token.
2. Resource owner: your account. Repository access: **Only select repositories** → the private site repo (`xplorekit`) and nothing else.
3. Repository permissions: **Contents: Read and write**, **Pull requests: Read and write**. Metadata (read) is added automatically.
4. Set an expiry you will remember (for example 90 days), generate, copy the token, and paste it as the `SITE_REPO_TOKEN` secret here.

**Allow the workflow to push**: this repo → Settings → Actions → General → Workflow permissions → *Read and write*.

**Publish the dashboard**: Settings → Pages → Build and deployment → Source *Deploy from a branch* → branch `main`, folder `/docs`. The page is
`https://<your-github-name>.github.io/xplorekit-dashboard/`. It is rebuilt by every research run and by the `Dashboard` workflow when data or settings change.

## 2. Run it
- **Automatically:** `research.yml` runs **every 3 hours**; `recheck.yml` runs weekly (re-checks links, flags stale entries).
- **By hand:** Actions → *Research* → *Run workflow*. Use `dry_run: true` the first time: it writes to `.dryrun/` and commits nothing.
- **Locally:** `python -m xplorekit.run --section money --dry-run --site-dir ../xplorekit` (needs `claude` CLI + token, or an API key).
- **Publishing (automatic):** each run syncs the fact-checked entries to the site repo, whose `scripts/build-feed.py` renders them as cards inside the four hub pages, then
  `xplorekit/site_pr.py` runs the safety checks (see AGENTS.md) and **merges the pull request itself** (branch `feed/xplorekit-research`); Cloudflare deploys as for any merge to `main`.
  If a check fails, the pull request stays open and the dashboard shows why. To change where new posts go, use the dashboard's **"New posts go to"** dropdown or set `"publish_mode"` (`publish` / `pending` / `draft`) in `settings.json`; to undo a batch, `git revert` its squash commit in the site repo.
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


## 6. The dashboard control bar (Pause, Run now, "New posts go to")
Above the tabs on the dashboard. To use the buttons, GitHub has to know it is you, so you connect a token once:
1. On the dashboard click **Connect GitHub** (or any button), then **Create a token on GitHub**.
2. Fine-grained token, **Only select repositories** -> `xplorekit-dashboard`. Permissions: **Actions: Read and write** (to start a run) and **Contents: Read and write** (to change `settings.json`). Pick a short expiry (for example 90 days).
3. Paste it into the panel and **Save token**. By default it is forgotten when you close the tab; tick "Remember it on this device" to keep it. **Forget token** removes it.

What the controls do: **Pause / Resume** sets `paused` in `settings.json`; **Run now** starts the Research workflow; **New posts go to** sets `publish_mode`: *Published (live)* merges by itself, *Pending* opens a pull request that a person merges, *Draft* only researches and saves (nothing is sent to the site). Every change is a commit on `main` titled "Dashboard: ...", so it shows in git history and can be reverted. A change applies from the next run.
Without a token the bar still shows the schedule and live run status (it reads GitHub's public API) and the buttons just ask you to connect.
Safety: the page only ever contacts `api.github.com` (the browser enforces this), and the token travels only in a request header, never in a URL.
