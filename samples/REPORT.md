# Dry-run report (2026-11-16)

**What this is.** The first end-to-end run. Discovery, enrichment, the Editor/Verifier, site dedupe and the hand-off to the site repo are the real
pipeline code, run against live sources. **The drafts were written by Claude Code in the build session, not by the scheduled agent**, because the
sandbox had no Claude token. Their fact-check verdicts are therefore `fact_check:manual` (I read each source before writing the verdict), not `llm`.

## Result
| Section | Accepted | Rejected | Notes |
|---|---|---|---|
| Make Money with AI | 2 | 0 | KDP and Etsy rules pages. Neither states income, so none is shown. I could not find a third source that is both reachable and verifiable. |
| Prompts | 4 | 0 | Grounded in the Anthropic and OpenAI prompting guides. |
| Chrome Extensions | 4 | 0 | Each with a live Chrome Web Store page and a real "last updated" date read from it. |
| Claude Skills | 4 | 0 | Real repos with install steps taken from their READMEs. |

**Negative controls (all four rejected, as intended):** hype + invented $10,000 figure · income numbers absent from the cited source ·
a platform already covered by an existing site plan (duplicate of `make-money-with-ai/get-paid-to-train-ai`) · extension from a repo that does not exist.

## Bugs the dry run found and fixed (with tests)
1. A page answering HEAD with 404 but GET with 200 (Etsy) was wrongly "dead".
2. Large Chrome Web Store pages were truncated, so real update dates looked unverifiable.
3. The Verifier checked claims against the collector's 1,500-character teaser instead of the full page.
4. GitHub repos were verified by scraping github.com HTML; now via the official raw host (README), which also gives better fact-check text.
5. A unit test overwrote the real candidate cache. Prompts could not share one source page.

## What this run did NOT prove
- **The agents running through `claude -p` with `CLAUDE_CODE_OAUTH_TOKEN`** (untested here). First real proof is a manual workflow run with `dry_run: true`.
- **Cross-repo push and PR.** The hand-off code ran against a throwaway copy of the site repo; `open_site_pr.sh` and `SITE_REPO_TOKEN` are untested.
- **Prompts are not "tested".** They are original and grounded in vendor guidance, but nobody ran them on ChatGPT, Claude and Gemini. The schema does not claim it.
- **Money discovery is weak.** Generic searches return noise (the two GitHub "money" repos were abandoned/compromised). Official platform pages are the useful source type.
  Medium's and Upwork's pages return 403 to bots (Upwork's investor site also disallows them), so claims from them cannot be grounded and are not used.
- Reddit and YouTube sources were skipped (no keys). The site does not yet render `public/data/`.
