# AutoCrypto Trader

Automated crypto trading system using **TradingView** for chart analysis and **Delta Exchange** for execution.

## Architecture

```
TradingView Pine Script
  └── Webhook (Buy/Sell signals)
        └── Signal Receiver (FastAPI)
              ├── Risk Manager (stop-loss, sizing)
              ├── Fund Manager (25% lock rule)
              └── Trade Executor (Delta Exchange API)
                    └── Daily Reporter (email)
```

## Phase Build Status

| Phase | Description | Status |
|-------|-------------|--------|
| 1 | Foundation (scaffold, config UI, DB) | ✅ Complete |
| 2 | Signal Engine (TradingView → webhook) | 🔜 Next |
| 3 | Risk + Fund Logic | ⏳ Pending |
| 4 | Trade Executor (Delta API) | ⏳ Pending |
| 5 | Reporting + Alerts | ⏳ Pending |
| 6 | Hardening | ⏳ Pending |

## Quick Start

```bash
# 1. Clone and enter project
cd autocrypto

# 2. Run quickstart (sets up .env, builds containers)
chmod +x scripts/quickstart.sh
./scripts/quickstart.sh

# 3. Open setup UI
open http://localhost:3000
```

## Manual Start

```bash
# Copy and edit env
cp .env.example .env
# Edit .env with your values

# Start
docker compose up -d --build

# Logs
docker compose logs -f backend
```

## Services

| Service | Port | Description |
|---------|------|-------------|
| frontend | 3000 | Setup UI + Dashboard |
| backend | 8000 | FastAPI (signals, trades, reports) |
| db | 5432 | PostgreSQL |

## Key Trading Rules

- **Risk per trade**: 0.5%–10% of available fund (configurable, default 2%)
- **Stop-loss**: Fixed % or ATR-based (dynamic)
- **Max daily drawdown**: Bot pauses if fund drops >15% in 24h
- **25% lock rule**: When fund doubles (100% profit), lock 25% permanently; trade with remaining 75%
- **Emergency alerts**: Email on API failure, auth issues, fund critically low

## API Docs

`http://localhost:8000/docs` — Swagger UI

## Environment Variables

See `.env.example` for all required variables.
