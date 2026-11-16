# xplorekit-dashboard

Public research pipeline for [Xplorekit](https://xplorekit.online). It **discovers, verifies and rewrites** content for four site
sections and hands the verified result to the private site repo as a pull request.

| Section | Agent | What it produces |
|---|---|---|
| Make Money with AI (priority) | Money Ideas Researcher | realistic ideas with workflow, risks and a verifiable source; income figures only when the source states them |
| Prompts | Prompt Hunter | original, reusable prompts for ChatGPT, Claude, Gemini, grouped by use case |
| Chrome Extensions | Extension Scout | AI-first extensions, each with a Chrome Web Store link, pros and cons, pricing, last-updated date |
| Claude Skills | Skills Scout | SKILL.md skills and related agent skills with install steps and a source repo |

A shared **Editor/Verifier** checks every draft before it is saved.

```
collectors (HN, GitHub, RSS, official docs, Reddit/YouTube with keys)
   -> prefilter (already on the site? already rejected? relevant?) -> enrich (README, Web Store links)
   -> section agent (Claude writes drafts in its own words)
   -> Editor/Verifier (schema, duplicates, live links, income + hype gate, copy check, fact-check, score)
   -> data/<section>/*.json + index.json   (this repo)
   -> one rolling pull request on the private site repo (public/data/...)  -> you review -> merge -> Cloudflare deploys
```

## Quality gate (what gets rejected)
Invalid schema · duplicate of anything already accepted, in the same batch, or **already on the live site** (by URL and title similarity) ·
dead or unreachable source link · extension without a live Chrome Web Store link · hype or guarantee wording ·
**any income figure the source text does not itself contain** (or above a realistic cap) · more than 120 characters copied from the source ·
claims the fact-checker cannot support · quality score below the section floor (Money 80, others 70). Entries with no independent
fact-check are tagged `rules_only` and capped at 79, so they can never pass the Money floor. Rejections are logged in `data/rejected/`.

## Rules the pipeline follows
robots.txt is checked before every page fetch (and Reddit is used through its official API only) · official APIs, RSS and public pages first ·
nothing is copied; the source URL is always stored · no star, user, download or rating counts are ever stored (the site's own rule) ·
daily and weekly caps per section (`xplorekit/config/settings.json`).

## Use it
See **[docs/GUIDE.md](docs/GUIDE.md)**: setup, how to run, how to add a source, how to add a section.

```bash
python -m unittest discover -s tests          # 56 offline tests
python -m xplorekit.run --section money --dry-run --site-dir ../xplorekit
```

`samples/` holds the first dry run (see `samples/REPORT.md`).
