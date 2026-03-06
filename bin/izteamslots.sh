#!/usr/bin/env bash
set -e

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

# Ensure bun is available
if ! command -v bun &>/dev/null; then
  if [ -d "$HOME/.bun/bin" ]; then
    export PATH="$HOME/.bun/bin:$PATH"
  else
    echo "Bun not found. Run: npm run setup" >&2
    exit 1
  fi
fi

exec bun run --cwd "$ROOT/ui" src/main.ts "$@"
