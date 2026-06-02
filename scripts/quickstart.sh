#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────────────
# AutoCrypto Trader — Quickstart Script
# Can be run from any directory:
#   ./scripts/quickstart.sh
#   bash scripts/quickstart.sh
#   cd scripts && ./quickstart.sh   (all work)
# ──────────────────────────────────────────────────────────────────────────────
set -e

# Always cd to project root (one level up from this script)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${PROJECT_ROOT}"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
info()  { echo -e "${GREEN}[INFO]${NC}  $1"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

info "Project root: ${PROJECT_ROOT}"

# ── Check Docker ──────────────────────────────────────────────────────────────
command -v docker >/dev/null 2>&1 \
  || error "Docker not found. Install from https://docs.docker.com/get-docker/"

docker compose version >/dev/null 2>&1 \
  || error "Docker Compose v2 not found. Update Docker Desktop or: sudo apt install docker-compose-plugin"

# ── Create .env ───────────────────────────────────────────────────────────────
if [ ! -f "${PROJECT_ROOT}/.env" ]; then
  info "Creating .env from .env.example ..."

  [ -f "${PROJECT_ROOT}/.env.example" ] \
    || error ".env.example missing. Ensure you extracted the full autocrypto directory."

  cp "${PROJECT_ROOT}/.env.example" "${PROJECT_ROOT}/.env"

  # macOS needs: sed -i ''   |   Linux needs: sed -i
  _sed() {
    if [[ "$(uname)" == "Darwin" ]]; then
      sed -i '' "$@"
    else
      sed -i "$@"
    fi
  }

  # Generate Fernet encryption key for secrets stored in DB
  info "Generating CONFIG_ENCRYPTION_KEY ..."
  FERNET_KEY=""
  if command -v python3 >/dev/null 2>&1; then
    FERNET_KEY=$(python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())" 2>/dev/null || true)
  fi
  if [ -z "${FERNET_KEY}" ]; then
    info "python3 cryptography not available locally — using Docker to generate key..."
    FERNET_KEY=$(docker run --rm python:3.11-slim \
      python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
  fi
  [ -z "${FERNET_KEY}" ] && error "Could not generate Fernet key."
  _sed "s|your_fernet_key_here|${FERNET_KEY}|" "${PROJECT_ROOT}/.env"

  # Generate random DB password
  info "Generating DB password ..."
  DB_PASS=$(openssl rand -hex 20 2>/dev/null \
    || head -c 40 /dev/urandom | base64 | tr -dc 'a-zA-Z0-9' | head -c 32)
  [ -z "${DB_PASS}" ] && error "Could not generate DB password."
  _sed "s|change_this_strong_password|${DB_PASS}|g" "${PROJECT_ROOT}/.env"

  warn ".env created. Edit ${PROJECT_ROOT}/.env to review settings."
else
  info ".env already exists — skipping key generation."
fi

# ── Data directory ────────────────────────────────────────────────────────────
mkdir -p "${PROJECT_ROOT}/data"

# ── Build & start ─────────────────────────────────────────────────────────────
info "Building and starting containers (this may take a few minutes first time)..."
docker compose -f "${PROJECT_ROOT}/docker-compose.yml" up -d --build

# ── Wait for backend ──────────────────────────────────────────────────────────
info "Waiting for backend to be ready..."
READY=0
for i in $(seq 1 30); do
  if curl -sf http://localhost:8000/health >/dev/null 2>&1; then
    READY=1
    break
  fi
  printf "."
  sleep 2
done
echo ""

if [ "${READY}" -eq 0 ]; then
  warn "Backend did not respond after 60s. Check logs:"
  warn "  docker compose logs backend"
else
  info "Backend is up!"
fi

# ── Done ──────────────────────────────────────────────────────────────────────
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo -e "${GREEN}  AutoCrypto Trader is running!${NC}"
echo ""
echo "  Setup UI   →  http://localhost:3000"
echo "  API Docs   →  http://localhost:8000/docs"
echo "  Health     →  http://localhost:8000/health"
echo ""
echo "  Open Setup UI and fill in your credentials."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
