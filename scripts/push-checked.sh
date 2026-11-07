#!/usr/bin/env bash
# Pushes main only after GitHub's checks pass on it (Linux, Windows, macOS; free for this public
# repo). The commit goes to check/<short sha> first; when every run on it passes, main is pushed
# and the check branch deleted. A failing run leaves main unpushed and prints the failed jobs.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
[ "$(git branch --show-current)" = main ] || { echo "Run on main."; exit 1; }
sha=$(git rev-parse HEAD)
branch="check/${sha:0:12}"
git push -q origin "HEAD:refs/heads/$branch"
trap 'git push -q origin --delete "$branch" 2>/dev/null || true' EXIT
echo "Checking $sha on $branch ..."
sleep 30
while :; do
  runs=$(gh run list --branch "$branch" --json status,conclusion,name,databaseId)
  [ "$(jq length <<<"$runs")" -gt 0 ] || { sleep 30; continue; }
  [ "$(jq '[.[] | select(.status != "completed")] | length' <<<"$runs")" = 0 ] && break
  sleep 60
done
jq -r '.[] | "\(.name): \(.conclusion)"' <<<"$runs"
if [ "$(jq '[.[] | select(.conclusion != "success" and .conclusion != "skipped")] | length' <<<"$runs")" != 0 ]; then
  for id in $(jq -r '.[] | select(.conclusion != "success" and .conclusion != "skipped") | .databaseId' <<<"$runs"); do
    gh run view "$id" --json jobs -q '.jobs[] | select(.conclusion == "failure") | "  failed: \(.name)"'
  done
  echo "main was not pushed."
  exit 1
fi
git push -q origin main
echo "main pushed: $sha"
