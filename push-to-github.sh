#!/usr/bin/env bash
# push-to-github.sh — authenticates with GITHUB_TOKEN from .env and pushes
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Load .env
if [ -f "$SCRIPT_DIR/.env" ]; then
  export $(grep -v '^#' "$SCRIPT_DIR/.env" | grep -v '^$' | xargs)
else
  echo "❌  .env file not found. Copy .env.example to .env and fill in GITHUB_TOKEN."
  exit 1
fi

# Validate token
if [ -z "${GITHUB_TOKEN:-}" ] || [ "$GITHUB_TOKEN" = "ghp_your_token_here" ]; then
  echo "❌  GITHUB_TOKEN is not set in .env"
  echo "    Generate one at: https://github.com/settings/tokens"
  echo "    Required scopes: repo, read:org"
  exit 1
fi

# Authenticate gh CLI with the token
echo "$GITHUB_TOKEN" | gh auth login --with-token
echo "✅  GitHub authenticated"

# Create repo and push (skips if remote already exists)
cd "$SCRIPT_DIR"

if git remote get-url origin &>/dev/null; then
  echo "ℹ️   Remote 'origin' already set — pushing latest commits..."
  git push origin HEAD
else
  echo "🚀  Creating GitHub repo and pushing..."
  gh repo create Kalas1980/web-keyword-scanner \
    --public \
    --source=. \
    --remote=origin \
    --push \
    --description "Web keyword scanner — crawl sites and find pages matching your keywords"
fi

echo ""
echo "✅  Done! Your repo: https://github.com/Kalas1980/web-keyword-scanner"
