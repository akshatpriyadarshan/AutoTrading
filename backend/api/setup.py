"""
Setup & Config API endpoints
"""
import json
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from db.database import get_db
from config.config_manager import (
    bulk_set_config, get_config, get_all_config,
    CONFIG_KEYS, SECRET_KEYS
)
from models.schemas import SetupRequest, SetupResponse, BotStatusResponse
from loguru import logger

router = APIRouter(prefix="/api/setup", tags=["setup"])


@router.post("/", response_model=SetupResponse)
async def run_setup(payload: SetupRequest, db: AsyncSession = Depends(get_db)):
    """
    One-time setup endpoint. Saves all credentials and trading params to DB.
    """
    try:
        data = {
            "delta_api_key":              payload.delta_api_key,
            "delta_api_secret":           payload.delta_api_secret,
            "delta_testnet":              str(payload.delta_testnet).lower(),
            "tradingview_webhook_secret": payload.tradingview_webhook_secret,
            "email_address":              payload.email_address,
            "smtp_host":                  payload.smtp_host,
            "smtp_port":                  str(payload.smtp_port),
            "smtp_user":                  payload.smtp_user,
            "smtp_password":              payload.smtp_password,
            "smtp_use_tls":               str(payload.smtp_use_tls).lower(),
            "starting_capital":           str(payload.starting_capital),
            "risk_per_trade_pct":         str(payload.risk_per_trade_pct),
            "stop_loss_type":             payload.stop_loss_type,
            "stop_loss_fixed_pct":        str(payload.stop_loss_fixed_pct),
            "max_drawdown_pct":           str(payload.max_drawdown_pct),
            "trading_pairs":              payload.trading_pairs,
            "max_open_trades":            str(payload.max_open_trades),
            "profit_lock_threshold":      str(payload.profit_lock_threshold),
            "profit_lock_pct":            str(payload.profit_lock_pct),
            "setup_complete":             "true",
            "bot_active":                 "false",  # user starts bot manually
        }

        await bulk_set_config(db, data, secret_keys=SECRET_KEYS)

        # Determine webhook URL hint
        webhook_url = "/api/signals/webhook"

        logger.info("Setup completed successfully")
        return SetupResponse(
            success=True,
            message="Setup complete. Configure your TradingView webhook and start the bot.",
            webhook_url=webhook_url,
        )

    except Exception as e:
        logger.error(f"Setup failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status", response_model=BotStatusResponse)
async def get_status(db: AsyncSession = Depends(get_db)):
    """Return current bot configuration status."""
    setup_complete = await get_config(db, "setup_complete")
    bot_active     = await get_config(db, "bot_active")
    testnet        = await get_config(db, "delta_testnet")
    pairs_raw      = await get_config(db, "trading_pairs") or "BTC/USDT"
    capital        = await get_config(db, "starting_capital") or "0"
    risk           = await get_config(db, "risk_per_trade_pct") or "2"
    max_trades     = await get_config(db, "max_open_trades") or "3"

    return BotStatusResponse(
        active=bot_active == "true",
        setup_complete=setup_complete == "true",
        delta_testnet=testnet == "true",
        trading_pairs=[p.strip() for p in pairs_raw.split(",")],
        starting_capital=float(capital),
        risk_per_trade_pct=float(risk),
        max_open_trades=int(max_trades),
        uptime_since=None,
    )


@router.post("/bot/start")
async def start_bot(db: AsyncSession = Depends(get_db)):
    setup = await get_config(db, "setup_complete")
    if setup != "true":
        raise HTTPException(status_code=400, detail="Setup not complete")
    from config.config_manager import set_config
    await set_config(db, "bot_active", "true")
    await db.commit()
    logger.info("Bot started")
    return {"success": True, "message": "Bot started"}


@router.post("/bot/stop")
async def stop_bot(db: AsyncSession = Depends(get_db)):
    from config.config_manager import set_config
    await set_config(db, "bot_active", "false")
    await db.commit()
    logger.info("Bot stopped")
    return {"success": True, "message": "Bot stopped"}


@router.get("/config")
async def read_config(db: AsyncSession = Depends(get_db)):
    """Return all config keys (secrets masked)."""
    return await get_all_config(db)
