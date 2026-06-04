#!/usr/bin/env bash
# One-time local setup. Run once, then: python run_local.py  or F5 in VSCode.
set -e
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

G='\033[0;32m'; Y='\033[1;33m'; R='\033[0;31m'; N='\033[0m'
ok()   { echo -e "${G}[OK]${N}   $1"; }
warn() { echo -e "${Y}[WARN]${N} $1"; }
die()  { echo -e "${R}[ERR]${N} $1"; exit 1; }

# Python check
command -v python3 >/dev/null 2>&1 || die "Python 3.10+ required. Install from python.org"
PY=$(python3 -c "import sys; print(sys.version_info.minor)")
[ "$PY" -ge 10 ] || die "Python 3.10+ required (found 3.$PY)"
ok "Python 3.$PY"

# Virtual env
if [ ! -d "venv" ]; then
  python3 -m venv venv && ok "venv created"
fi

# Activate (works on Mac/Linux)
source venv/bin/activate

# Install
pip install -q --upgrade pip
pip install -q -r backend/requirements-local.txt
ok "Dependencies installed"

# .env
if [ ! -f ".env" ]; then
  warn ".env not found — creating dev .env"
  cat > .env << 'ENVEOF'
DATABASE_URL=sqlite+aiosqlite:///./data/autocrypto.db
CONFIG_ENCRYPTION_KEY=dev-only-key-32chars-change-prod
APP_ENV=development
DEBUG=true
ENVEOF
  ok ".env created"
fi

mkdir -p data

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo -e "${G}  Setup complete!${N}"
echo ""
echo "  Start options:"
echo "  1. VSCode  → F5 → '🐍 Run Backend (local Python)'"
echo "  2. Terminal → source venv/bin/activate && python run_local.py"
echo ""
echo "  Then open in browser:"
echo "    frontend/index.html    ← Setup"
echo "    frontend/dashboard.html ← Dashboard"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
