#!/bin/bash
# Install git post-commit auto-push for this repo (run once per machine).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

chmod +x .githooks/post-commit .cursor/hooks/auto-push.sh 2>/dev/null || true

# Use repo-local hooks directory (user must run this script explicitly).
git config core.hooksPath .githooks

echo "Installed: core.hooksPath=.githooks (post-commit auto-push)"
echo "Cursor stop hook: .cursor/hooks.json (reload Cursor if needed)"
