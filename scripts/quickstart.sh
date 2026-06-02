#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────────────
# AutoCrypto Trader — Quickstart Script
# Run once on a fresh VPS or local machine
# ──────────────────────────────────────────────────────────────────────────────
set -e

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'

info()  { echo -e "${GREEN}[INFO]${NC}  $1"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

# Check docker
command -v docker >/dev/null 2>&1 || error "Docker not installed. Install from https://docs.docker.com/get-docker/"
command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1 || error "Docker Compose v2 not available"

# Create .env if not exists
if [ ! -f .env ]; then
  info "Creating .env from template..."
  cp .env.example .env

  # Generate Fernet key
  FERNET_KEY=$(python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())" 2>/dev/null || \
               docker run --rm python:3.11-slim python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
  sed -i "s|your_fernet_key_here|${FERNET_KEY}|" .env

  # Generate DB password
  DB_PASS=$(openssl rand -hex 16 2>/dev/null || cat /dev/urandom | tr -dc 'a-zA-Z0-9' | fold -w 32 | head -n 1)
  sed -i "s|change_this_strong_password|${DB_PASS}|g" .env

  warn ".env created. Review it before proceeding."
fi

# Create data dir
mkdir -p data

info "Building and starting containers..."
docker compose up -d --build

info "Waiting for backend to be ready..."
for i in $(seq 1 30); do
  if curl -sf http://localhost:8000/health >/dev/null 2>&1; then
    info "Backend is up!"
    break
  fi
  sleep 2
  echo -n "."
done

echo ""
echo "────────────────────────────────────────────"
echo -e "${GREEN}AutoCrypto Trader is running!${NC}"
echo ""
echo "  Setup UI:    http://localhost:3000"
echo "  API Docs:    http://localhost:8000/docs"
echo "  Health:      http://localhost:8000/health"
echo ""
echo "  Open the Setup UI to configure your bot."
echo "────────────────────────────────────────────"
