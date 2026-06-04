"""
Config Manager
Stores all user settings in DB. Secrets are Fernet-encrypted at rest.
"""
import json
import os
from typing import Any, Optional
from cryptography.fernet import Fernet
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from models.db_models import Config

_fernet: Optional[Fernet] = None


def _get_fernet() -> Fernet:
    global _fernet
    if _fernet:
        return _fernet

    key = os.environ.get("CONFIG_ENCRYPTION_KEY", "")

    # If key missing or invalid, generate one (dev fallback)
    if not key:
        key = Fernet.generate_key().decode()
        os.environ["CONFIG_ENCRYPTION_KEY"] = key
        logger.warning("No CONFIG_ENCRYPTION_KEY set — generated one for this session. Add it to .env!")

    # Validate key is proper Fernet format before creating instance
    try:
        _fernet = Fernet(key.encode() if isinstance(key, str) else key)
    except Exception:
        # Key is set but invalid format — regenerate
        logger.warning("CONFIG_ENCRYPTION_KEY was invalid — regenerating.")
        key = Fernet.generate_key().decode()
        os.environ["CONFIG_ENCRYPTION_KEY"] = key
        _fernet = Fernet(key.encode())

    return _fernet


def encrypt(value: str) -> str:
    return _get_fernet().encrypt(value.encode()).decode()


def decrypt(value: str) -> str:
    return _get_fernet().decrypt(value.encode()).decode()


# ── CRUD ──────────────────────────────────────────────────────────────────────

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
    """Return all config keys. Secret values shown as '***'."""
    result = await db.execute(select(Config))
    rows = result.scalars().all()
    return {row.key: "***" if row.is_secret else row.value for row in rows}


async def bulk_set_config(db: AsyncSession, data: dict, secret_keys: list = None):
    secret_keys = secret_keys or []
    for key, value in data.items():
        await set_config(db, key, value, is_secret=(key in secret_keys))
    await db.commit()


# ── Config key registry ───────────────────────────────────────────────────────

CONFIG_KEYS = {
    "delta_api_key":              {"secret": True,  "label": "Delta Exchange API Key"},
    "delta_api_secret":           {"secret": True,  "label": "Delta Exchange API Secret"},
    "delta_testnet":              {"secret": False, "label": "Use Testnet"},
    "tradingview_webhook_secret": {"secret": True,  "label": "TradingView Webhook Secret"},
    "email_address":              {"secret": False, "label": "Report Email"},
    "smtp_host":                  {"secret": False, "label": "SMTP Host"},
    "smtp_port":                  {"secret": False, "label": "SMTP Port"},
    "smtp_user":                  {"secret": True,  "label": "SMTP Username"},
    "smtp_password":              {"secret": True,  "label": "SMTP Password"},
    "smtp_use_tls":               {"secret": False, "label": "SMTP TLS"},
    "starting_capital":           {"secret": False, "label": "Starting Capital (INR)"},
    "risk_per_trade_pct":         {"secret": False, "label": "Risk Per Trade %"},
    "stop_loss_type":             {"secret": False, "label": "Stop-Loss Type"},
    "stop_loss_fixed_pct":        {"secret": False, "label": "Fixed Stop-Loss %"},
    "max_drawdown_pct":           {"secret": False, "label": "Max Daily Drawdown %"},
    "trading_pairs":              {"secret": False, "label": "Trading Pairs"},
    "max_open_trades":            {"secret": False, "label": "Max Open Trades"},
    "profit_lock_threshold":      {"secret": False, "label": "Profit Lock Threshold %"},
    "profit_lock_pct":            {"secret": False, "label": "Profit Lock %"},
    "setup_complete":             {"secret": False, "label": "Setup Complete"},
    "bot_active":                 {"secret": False, "label": "Bot Active"},
    "candle_interval":            {"secret": False, "label": "Candle Interval (1m/5m/15m/1h/4h)"},
}

SECRET_KEYS = [k for k, v in CONFIG_KEYS.items() if v["secret"]]
