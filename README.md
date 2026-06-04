# AutoCrypto Trader

Automated crypto trading — TradingView signals → Delta Exchange execution.

---

## Quick Start

### Option A — VSCode (no Docker, easiest)

```bash
# 1. Run once to set up Python env
chmod +x setup_local.sh
./setup_local.sh

# 2. Open in VSCode
code .

# 3. Press F5 → select "🐍 Backend Only (local Python)"
# 4. Open frontend/index.html in browser to complete setup
```

### Option B — Docker (full production stack)

```bash
chmod +x scripts/quickstart.sh
./scripts/quickstart.sh
# → open http://localhost:3000
```

---

## Currency

All amounts are in **INR (₹)**. The bot trades crypto pairs priced in USDT,
but your starting capital, P&L reports, and fund displays are shown in INR.

---

## Setup Flow

1. Open **Setup UI** (`frontend/index.html` or `http://localhost:3000`)
2. Fill in 4 steps: Exchange → Email → Trading Rules → Review
3. Click **Save & Complete Setup**
4. Open Dashboard → click **Start Bot**
5. Add webhook URL to TradingView Pine Script alerts

---

## URLs

| Mode | Setup UI | Dashboard | API Docs |
|------|----------|-----------|----------|
| Local (VSCode) | `frontend/index.html` | `frontend/dashboard.html` | `http://localhost:8000/docs` |
| Docker | `http://localhost:3000` | `http://localhost:3000/dashboard` | `http://localhost:8000/docs` |

---

## Phase Status

| Phase | Description | Status |
|-------|-------------|--------|
| 1 | Foundation — scaffold, config, DB | ✅ |
| 2 | Signal Engine — TradingView webhook | ✅ |
| 3 | Risk + Fund Manager | 🔜 |
| 4 | Trade Executor (Delta API) | ⏳ |
| 5 | Daily Reports + Alerts | ⏳ |
| 6 | Hardening | ⏳ |

---

## Key Rules

- Risk per trade: 0.5–10% of available fund (default 2%)
- Stop-loss: Fixed % or ATR-based
- Max daily drawdown: Bot pauses if fund drops >15%
- **25% lock rule**: When fund doubles → lock 25% permanently → trade with 75%
