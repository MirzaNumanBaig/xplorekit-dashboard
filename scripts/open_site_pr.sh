#!/usr/bin/env bash
# Put the synced files on ONE rolling branch of the private site repo and open (or update) a single pull request.
# usage: open_site_pr.sh <site-checkout> <pr-body-file>      env: GH_TOKEN (token with access to the site repo), SITE_REPO
set -euo pipefail
site="$1"; body="$2"; branch="feed/xplorekit-research"
cd "$site"
git config user.name "xplorekit-research-bot"
git config user.email "xplorekit-research-bot@users.noreply.github.com"
git checkout -B "$branch" origin/main
git add public/data
if git diff --cached --quiet; then echo "nothing new for the site"; exit 0; fi
git commit -q -m "Research feed: update verified entries ($(date -u +%F))"
git push -q --force-with-lease origin "$branch" || git push -q --force origin "$branch"
if gh pr list --repo "$SITE_REPO" --head "$branch" --state open --json number --jq '.[0].number' | grep -q .; then
  gh pr edit "$branch" --repo "$SITE_REPO" --body-file "$body"
  echo "updated the open pull request"
else
  gh pr create --repo "$SITE_REPO" --base main --head "$branch" --title "Research feed: new verified entries" --body-file "$body"
fi
