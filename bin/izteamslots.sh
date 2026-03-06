#!/usr/bin/env bash
set -e

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

# Resolve Python from venv
if [ -f "$ROOT/.venv/bin/python" ]; then
  export PYTHON_BIN="$ROOT/.venv/bin/python"
elif [ -f "$ROOT/.venv/Scripts/python.exe" ]; then
  export PYTHON_BIN="$ROOT/.venv/Scripts/python.exe"
fi

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
