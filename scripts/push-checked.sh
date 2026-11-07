#!/usr/bin/env bash
# Pushes main only after GitHub's checks pass on it (Linux, Windows, macOS; free for this public
# repo). Two short steps, so no single command waits the whole run:
#
#   scripts/push-checked.sh start    pushes HEAD to check/<short sha> and returns
#   scripts/push-checked.sh finish   waits up to 9 minutes; when every run passed, pushes main and
#                                    deletes the check branch. Still running: exits 2, run it again.
#                                    A failed run: names the failed jobs, main stays unpushed, exit 1.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
[ "$(git branch --show-current)" = main ] || { echo "Run on main."; exit 1; }
sha=$(git rev-parse HEAD)
branch="check/${sha:0:12}"

case "${1:-}" in
  start)
    git push -q origin "HEAD:refs/heads/$branch"
    echo "Checking $sha on $branch. Run: scripts/push-checked.sh finish"
    ;;
  finish)
    git ls-remote --exit-code --heads origin "$branch" >/dev/null ||
      { echo "No $branch on GitHub. Run: scripts/push-checked.sh start"; exit 1; }
    deadline=$((SECONDS + 540))
    while :; do
      runs=$(gh run list --branch "$branch" --json status,conclusion,name,databaseId)
      if [ "$(jq length <<<"$runs")" -gt 0 ] &&
        [ "$(jq '[.[] | select(.status != "completed")] | length' <<<"$runs")" = 0 ]; then
        break
      fi
      if [ $SECONDS -ge $deadline ]; then
        echo "Still running on $branch. Run finish again."
        exit 2
      fi
      sleep 30
    done
    jq -r '.[] | "\(.name): \(.conclusion)"' <<<"$runs"
    failed=$(jq -r '.[] | select(.conclusion != "success" and .conclusion != "skipped") | .databaseId' <<<"$runs")
    if [ -n "$failed" ]; then
      for id in $failed; do
        gh run view "$id" --json jobs -q '.jobs[] | select(.conclusion == "failure") | "  failed: \(.name)"'
      done
      echo "main was not pushed."
      exit 1
    fi
    git push -q origin main
    git push -q origin --delete "$branch"
    echo "main pushed: $sha"
    ;;
  *)
    echo "Usage: scripts/push-checked.sh start|finish"
    exit 1
    ;;
esac
