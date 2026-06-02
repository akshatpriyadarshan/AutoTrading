"""
Config Manager
Stores all user settings in DB (secrets encrypted at rest).
"""
import json
import os
from typing import Any, Optional
from cryptography.fernet import Fernet
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from models.db_models import Config

# Encryption key — set via env or auto-generated once
_FERNET_KEY = os.getenv("CONFIG_ENCRYPTION_KEY", "")
_fernet: Optional[Fernet] = None


def _get_fernet() -> Fernet:
    global _fernet, _FERNET_KEY
    if _fernet:
        return _fernet
    if not _FERNET_KEY:
        _FERNET_KEY = Fernet.generate_key().decode()
        logger.warning("No CONFIG_ENCRYPTION_KEY set — generated one for this session. Set it in .env!")
    _fernet = Fernet(_FERNET_KEY.encode() if isinstance(_FERNET_KEY, str) else _FERNET_KEY)
    return _fernet


def encrypt(value: str) -> str:
    return _get_fernet().encrypt(value.encode()).decode()


def decrypt(value: str) -> str:
    return _get_fernet().decrypt(value.encode()).decode()


# ──────────────────────────────────────────────────────────────────────────────
# CRUD helpers
# ──────────────────────────────────────────────────────────────────────────────

async def get_config(db: AsyncSession, key: str) -> Optional[str]:
    result = await db.execute(select(Config).where(Config.key == key))
    row = result.scalar_one_or_none()
    if row is None:
        return None
    if row.is_secret and row.value:
        try:
            return decrypt(row.value)
        except Exception:
            logger.error(f"Failed to decrypt config key: {key}")
            return None
    return row.value


async def set_config(db: AsyncSession, key: str, value: Any, is_secret: bool = False):
    str_value = json.dumps(value) if not isinstance(value, str) else value
    if is_secret and str_value:
        str_value = encrypt(str_value)

    result = await db.execute(select(Config).where(Config.key == key))
    row = result.scalar_one_or_none()
    if row:
        row.value     = str_value
        row.is_secret = is_secret
    else:
        db.add(Config(key=key, value=str_value, is_secret=is_secret))
    await db.flush()


async def get_all_config(db: AsyncSession) -> dict:
    """Return all config as dict. Secrets returned as '***'."""
    result = await db.execute(select(Config))
    rows = result.scalars().all()
    out = {}
    for row in rows:
        out[row.key] = "***" if row.is_secret else row.value
    return out


async def bulk_set_config(db: AsyncSession, data: dict, secret_keys: list[str] = None):
    secret_keys = secret_keys or []
    for key, value in data.items():
        await set_config(db, key, value, is_secret=(key in secret_keys))
    await db.commit()


# ──────────────────────────────────────────────────────────────────────────────
# Config keys reference
# ──────────────────────────────────────────────────────────────────────────────

CONFIG_KEYS = {
    # Exchange
    "delta_api_key":            {"secret": True,  "label": "Delta Exchange API Key"},
    "delta_api_secret":         {"secret": True,  "label": "Delta Exchange API Secret"},
    "delta_testnet":            {"secret": False, "label": "Use Testnet (true/false)"},

    # TradingView
    "tradingview_webhook_secret": {"secret": True, "label": "TradingView Webhook Secret"},

    # Email
    "email_address":            {"secret": False, "label": "Report / Alert Email"},
    "smtp_host":                {"secret": False, "label": "SMTP Host"},
    "smtp_port":                {"secret": False, "label": "SMTP Port"},
    "smtp_user":                {"secret": True,  "label": "SMTP Username"},
    "smtp_password":            {"secret": True,  "label": "SMTP Password"},
    "smtp_use_tls":             {"secret": False, "label": "SMTP TLS (true/false)"},

    # Trading params
    "starting_capital":         {"secret": False, "label": "Starting Capital (USDT)"},
    "risk_per_trade_pct":       {"secret": False, "label": "Risk Per Trade % (default: 2)"},
    "stop_loss_type":           {"secret": False, "label": "Stop-Loss Type (fixed/atr)"},
    "stop_loss_fixed_pct":      {"secret": False, "label": "Fixed Stop-Loss % (default: 2)"},
    "max_drawdown_pct":         {"secret": False, "label": "Max Daily Drawdown % (default: 15)"},
    "trading_pairs":            {"secret": False, "label": "Trading Pairs CSV (e.g. BTC/USDT,ETH/USDT)"},
    "max_open_trades":          {"secret": False, "label": "Max Concurrent Open Trades (default: 3)"},
    "profit_lock_threshold":    {"secret": False, "label": "Profit Lock Threshold % (default: 100)"},
    "profit_lock_pct":          {"secret": False, "label": "Profit Lock % on Milestone (default: 25)"},

    # System
    "setup_complete":           {"secret": False, "label": "Setup Complete Flag"},
    "bot_active":               {"secret": False, "label": "Bot Active (true/false)"},
}

SECRET_KEYS = [k for k, v in CONFIG_KEYS.items() if v["secret"]]
