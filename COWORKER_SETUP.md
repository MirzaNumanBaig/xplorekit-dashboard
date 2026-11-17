# Xplorekit: setup instructions for a Claude coworker (browser + the owner's help)

Goal: switch on the dashboard and the daily research pipeline. Code is finished and merged to `main`; what is left is settings and secrets in GitHub.

- Research repo (public): `MirzaNumanBaig/xplorekit-dashboard` -> https://github.com/MirzaNumanBaig/xplorekit-dashboard
- Site repo (private): `MirzaNumanBaig/xplorekit` -> https://github.com/MirzaNumanBaig/xplorekit
- Dashboard link once on: https://mirzanumanbaig.github.io/xplorekit-dashboard/
- The owner (account `MirzaNumanBaig`) must be signed in to GitHub in the browser.

## Rules (read first)
1. Never type, paste, screenshot, log or repeat a token or key anywhere except the GitHub secret form it belongs to. Not in chat, not in a file, not in a commit, not in an issue.
2. Steps 3 and 4 create credentials on the owner's accounts. The OWNER does the sign-in/authorize clicks; you guide and verify. Do not create a token on their behalf without them watching.
3. Do not merge any pull request on the site repo. The owner merges.
4. Do not change anything not listed here (no workflow edits, no other settings, no deleting anything).
5. If a tool call fails 2-3 times, a page does not load, or an unexpected dialog appears: stop, say what you tried, ask.
6. After each step, say plainly what you verified and what you could not.

## Step 1: Enable GitHub Pages (the dashboard link)
1. Open https://github.com/MirzaNumanBaig/xplorekit-dashboard/settings/pages
2. Under "Build and deployment", Source: **Deploy from a branch**.
3. Branch: **main**, folder: **/docs**. Click **Save**.
4. Wait about 1-2 minutes, reload the page; it shows "Your site is live at https://mirzanumanbaig.github.io/xplorekit-dashboard/".
5. Open that URL. Expected: "Xplorekit research dashboard" with tabs Overview, Entries, Rejected, Sources, Runs, Usage, Setup. A yellow "No research run recorded yet" notice is normal for now.
- If the Source option is disabled or says the repo must be public: Settings -> General -> check the repo is Public (it is meant to be). Report back instead of changing visibility.

## Step 2: Let workflows commit data back
1. Open https://github.com/MirzaNumanBaig/xplorekit-dashboard/settings/actions
2. Scroll to "Workflow permissions". Select **Read and write permissions**. Click **Save**.
3. Leave "Allow GitHub Actions to create and approve pull requests" as it is.

## Step 3: Claude token (secret `CLAUDE_CODE_OAUTH_TOKEN`) - owner at the keyboard
What it is: a long-lived token tied to the owner's Claude subscription (Pro or Max, which includes Claude Code). The workflow's AI agents use it to write drafts. It cannot be created from the browser alone.
1. The owner opens a terminal on their own computer. Needs Node.js 18+.
2. Run: `npm install -g @anthropic-ai/claude-code`
3. Run: `claude setup-token`
4. A browser page opens: the owner signs in to Claude and clicks **Authorize**.
5. The terminal prints a token starting `sk-ant-oat01-`. It is shown ONCE. The owner copies it (do not ask them to send it to you).
6. Open https://github.com/MirzaNumanBaig/xplorekit-dashboard/settings/secrets/actions/new
7. Name: `CLAUDE_CODE_OAUTH_TOKEN` (exact, upper case). Secret: paste the token. Click **Add secret**.
8. Verify: https://github.com/MirzaNumanBaig/xplorekit-dashboard/settings/secrets/actions lists the name. GitHub never shows the value again; that is normal.
9. Optional backups: a second Claude account's token saved as `CLAUDE_CODE_OAUTH_TOKEN_2`, a third as `_3`. They are tried in order if the first fails or hits its usage limit.
- No subscription alternative: an API key from console.anthropic.com saved as `ANTHROPIC_API_KEY` (pay per use; it wins if both exist).
- If the token ever leaks: revoke it in the Claude account settings and repeat this step.

## Step 4: Site-repo token (secret `SITE_REPO_TOKEN`) - owner at the keyboard
What it is: a GitHub token that lets the workflow read the private site repo and open ONE pull request there. Keep it as narrow as possible.
1. Open https://github.com/settings/personal-access-tokens/new (fine-grained token).
2. Token name: `xplorekit-research`. Expiration: 90 days (owner should note the date to renew).
3. Resource owner: the `MirzaNumanBaig` account.
4. Repository access: **Only select repositories** -> choose **`MirzaNumanBaig/xplorekit`** and nothing else.
5. Repository permissions: **Contents: Read and write**, **Pull requests: Read and write**. (Metadata: Read-only is added automatically.) Leave everything else at "No access".
6. Click **Generate token**. Copy it (shown once; do not send it to you).
7. Open https://github.com/MirzaNumanBaig/xplorekit-dashboard/settings/secrets/actions/new
8. Name: `SITE_REPO_TOKEN`. Secret: paste it. **Add secret**.
- Failure signs later: the workflow step "Check out the private site repo" fails with 404/403 = the token does not cover `xplorekit` or lacks Contents access.

## Step 5 (optional): extra sources and a contact line
- Reddit (official API only): create a "script" app at https://www.reddit.com/prefs/apps, then secrets `REDDIT_CLIENT_ID` and `REDDIT_CLIENT_SECRET`. Without them Reddit sources are skipped, not fatal.
- YouTube: a YouTube Data API v3 key as secret `YOUTUBE_API_KEY`. Without it YouTube sources are skipped.
- Variable (not secret) `XK_CONTACT` at Settings -> Secrets and variables -> Actions -> Variables: a URL (suggest the repo URL) that goes into our User-Agent. The repo is public, so do not use a personal email or phone.

## Step 6: First test run (writes nothing)
1. Open https://github.com/MirzaNumanBaig/xplorekit-dashboard/actions/workflows/research.yml
2. **Run workflow** -> Branch `main`, section `all`, limit `3`, dry_run `true` -> Run.
3. Open the new run, wait for it (up to ~45 min max, usually much less). Open the job logs.
4. Expected: collectors lines like `[prompts] hn-prompts: ok (9)`; Reddit/YouTube "skipped, missing ..." if no keys; agent steps; final line like `done: N accepted, M rejected (written to .dryrun/)`.
5. If it fails, read the failing step and report the exact error text (token values never appear; messages say "slot 1" etc.). Common causes:
   | Symptom | Cause / fix |
   |---|---|
   | "claude CLI failed on every token" | Step 3 secret missing/wrong name, token expired, or usage limit. Redo step 3 or add `_2`. |
   | checkout of `xplorekit` fails 404/403 | Step 4 token scope or secret name wrong. |
   | push rejected / permission denied | Step 2 not saved. |
   | log says "no language model configured ... agent skipped" (status `no_model`) | No Claude secret reached the job. |
6. Do not retry blindly more than twice; report to the owner.

## Step 7: First real run (writes data and opens ONE PR)
Only after step 6 passes and the owner agrees.
1. Same Run workflow form: section `all`, limit `3`, dry_run `false`.
2. Expected results: a commit to `main` of the research repo ("Research: update entries and dashboard") with `data/` and `docs/`; one pull request on `MirzaNumanBaig/xplorekit` from branch `feed/xplorekit-research`, listing each new entry with source, score and checks.
3. Do NOT merge that PR. Give the owner its link. They review and merge; Cloudflare then deploys the site as for any merge.
4. Reload the dashboard link: Overview shows counts, Entries/Rejected/Runs fill in, Usage shows Claude tokens for the run.

## Step 8: Report back
Give the owner: which steps passed, the dashboard URL, the PR link (if step 7 ran), and anything unverified. Be honest that the Claude-agent step and the cross-repo PR are proven only once step 6/7 have actually run green.

## Known gaps (not part of this task)
- Since 2026-11-17 the private site repo has `scripts/build-feed.py`, which renders the delivered data as cards inside the four hub pages; the pipeline runs it and merges the result itself (see AGENTS.md).
- Sample entries in `samples/` were fact-checked by hand, not by the scheduled agent. Money discovery is weak; official platform rules pages work best.
- Schedules after setup: `research.yml` every 3 hours (minute 17), `recheck.yml` weekly (Mondays 05:41 UTC). Pause by setting `"paused": true` in `xplorekit/config/settings.json`.
