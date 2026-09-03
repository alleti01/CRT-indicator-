#!/bin/bash
# Auto-commit and push when a Cursor agent session ends (if there are changes).
# Never force-push. Never commits secrets (.env is gitignored).
set -euo pipefail

cat >/dev/null # consume hook stdin JSON

ROOT="$(git rev-parse --show-toplevel 2>/dev/null)" || exit 0
cd "$ROOT"

# Nothing to do
if git diff --quiet && git diff --cached --quiet && [ -z "$(git ls-files --others --exclude-standard)" ]; then
  exit 0
fi

git add -A

if git diff --cached --quiet; then
  exit 0
fi

MSG="Auto-sync: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
git commit -m "$MSG" || exit 0

BRANCH="$(git rev-parse --abbrev-ref HEAD)"
git push origin HEAD 2>/dev/null || git push origin "$BRANCH" 2>/dev/null || true

exit 0
