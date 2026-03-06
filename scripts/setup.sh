#!/usr/bin/env bash
set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

ok()   { echo -e "  ${GREEN}✓${NC} $1"; }
warn() { echo -e "  ${YELLOW}!${NC} $1"; }
fail() { echo -e "  ${RED}✗${NC} $1"; exit 1; }

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
echo ""
echo "izTeamSlots setup"
echo "================="
echo ""

# ── Python ──────────────────────────────────────────────
echo "Checking Python..."
PYTHON=""
for cmd in python3 python; do
  if command -v "$cmd" &>/dev/null; then
    ver=$("$cmd" --version 2>&1 | grep -oE '[0-9]+\.[0-9]+')
    major=$(echo "$ver" | cut -d. -f1)
    minor=$(echo "$ver" | cut -d. -f2)
    if [ "$major" -ge 3 ] && [ "$minor" -ge 11 ]; then
      PYTHON="$cmd"
      break
    fi
  fi
done
[ -z "$PYTHON" ] && fail "Python 3.11+ not found. Install: https://python.org"
ok "Python: $($PYTHON --version)"

# ── uv ──────────────────────────────────────────────────
echo "Checking uv..."
if ! command -v uv &>/dev/null; then
  warn "uv not found. Installing..."
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
fi
command -v uv &>/dev/null || fail "uv install failed. Install manually: https://docs.astral.sh/uv"
ok "uv: $(uv --version)"

# ── Python deps ─────────────────────────────────────────
echo "Installing Python dependencies..."
uv pip install --system -q -r "$ROOT/requirements.txt"
ok "Python deps installed"

# ── Bun ─────────────────────────────────────────────────
echo "Checking Bun..."
if ! command -v bun &>/dev/null; then
  warn "Bun not found. Installing..."
  curl -fsSL https://bun.sh/install | bash
  export PATH="$HOME/.bun/bin:$PATH"
fi
command -v bun &>/dev/null || fail "Bun install failed. Install manually: https://bun.sh"
ok "Bun: $(bun --version)"

# ── UI deps ─────────────────────────────────────────────
echo "Installing UI dependencies..."
cd "$ROOT/ui"
bun install --frozen-lockfile 2>/dev/null || bun install
ok "UI deps installed"
cd "$ROOT"

# ── .env ────────────────────────────────────────────────
if [ ! -f "$ROOT/.env" ]; then
  if [ -f "$ROOT/.env.example" ]; then
    cp "$ROOT/.env.example" "$ROOT/.env"
    warn ".env created from .env.example — edit it with your API keys"
  fi
fi

# ── Done ────────────────────────────────────────────────
echo ""
echo -e "${GREEN}Setup complete!${NC}"
echo ""
echo "  Start:  npm start"
echo "  Or:     bun run --cwd ui src/main.ts"
echo ""
