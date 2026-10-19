#!/bin/bash
# Pull the bot PC's latest logs from the bot-logs branch into this checkout and show its health.
#   bash scripts/fetch_bot_logs.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

git fetch --quiet origin bot-logs
files=$(git ls-tree -r --name-only origin/bot-logs)
for f in $files; do
  case "$f" in
    health.json|health_history.csv|sync.log) dest="phase74/logs/bot_pc_$f" ;;
    *) dest="$f" ;;
  esac
  mkdir -p "$(dirname "$dest")"
  git show "origin/bot-logs:$f" > "$dest"
done

echo "Bot PC synced at: $(git log -1 --format=%cd --date=local origin/bot-logs)"
cat phase74/logs/bot_pc_health.json
