"""
Setup & Config API
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from db.database import get_db
from config.config_manager import bulk_set_config, get_config, get_all_config, SECRET_KEYS
from models.schemas import SetupRequest, SetupResponse, BotStatusResponse
from loguru import logger

router = APIRouter(prefix="/api/setup", tags=["setup"])


@router.post("/", response_model=SetupResponse)
async def run_setup(payload: SetupRequest, db: AsyncSession = Depends(get_db)):
    try:
        data = {
            # Exchange
            "delta_api_key":              payload.delta_api_key,
            "delta_api_secret":           payload.delta_api_secret,
            "delta_testnet":              str(payload.delta_testnet).lower(),
            # TradingView webhook (optional now — kept for manual signals)
            "tradingview_webhook_secret": payload.tradingview_webhook_secret or "not-used",
            # Email
            "email_address":              payload.email_address,
            "smtp_host":                  payload.smtp_host,
            "smtp_port":                  str(payload.smtp_port),
            "smtp_user":                  payload.smtp_user,
            "smtp_password":              payload.smtp_password,
            "smtp_use_tls":               str(payload.smtp_use_tls).lower(),
            # Trading
            "starting_capital":           str(payload.starting_capital),
            "risk_per_trade_pct":         str(payload.risk_per_trade_pct),
            "stop_loss_type":             payload.stop_loss_type,
            "stop_loss_fixed_pct":        str(payload.stop_loss_fixed_pct),
            "max_drawdown_pct":           str(payload.max_drawdown_pct),
            "trading_pairs":              payload.trading_pairs,
            "max_open_trades":            str(payload.max_open_trades),
            "profit_lock_threshold":      str(payload.profit_lock_threshold),
            "profit_lock_pct":            str(payload.profit_lock_pct),
            "candle_interval":            payload.candle_interval,
            # System
            "setup_complete":             "true",
            "bot_active":                 "false",
        }
        await bulk_set_config(db, data, secret_keys=SECRET_KEYS)
        logger.info("Setup saved")
        return SetupResponse(success=True, message="Setup complete. Start the bot from the dashboard.")

    except Exception as e:
        logger.error(f"Setup failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status", response_model=BotStatusResponse)
async def get_status(db: AsyncSession = Depends(get_db)):
    return BotStatusResponse(
        active            = await get_config(db, "bot_active") == "true",
        setup_complete    = await get_config(db, "setup_complete") == "true",
        delta_testnet     = await get_config(db, "delta_testnet") == "true",
        trading_pairs     = [p.strip() for p in (await get_config(db, "trading_pairs") or "BTC/USDT").split(",")],
        starting_capital  = float(await get_config(db, "starting_capital") or "0"),
        risk_per_trade_pct= float(await get_config(db, "risk_per_trade_pct") or "2"),
        max_open_trades   = int(await get_config(db, "max_open_trades") or "3"),
        candle_interval   = await get_config(db, "candle_interval") or "15m",
        uptime_since      = None,
    )


@router.post("/bot/start")
async def start_bot(db: AsyncSession = Depends(get_db)):
    if await get_config(db, "setup_complete") != "true":
        raise HTTPException(400, "Complete setup first")
    from config.config_manager import set_config
    await set_config(db, "bot_active", "true")
    await db.commit()
    logger.info("Bot started")
    return {"success": True, "message": "Bot started — signal engine active"}


@router.post("/bot/stop")
async def stop_bot(db: AsyncSession = Depends(get_db)):
    from config.config_manager import set_config
    await set_config(db, "bot_active", "false")
    await db.commit()
    logger.info("Bot stopped")
    return {"success": True, "message": "Bot stopped"}


@router.get("/config")
async def read_config(db: AsyncSession = Depends(get_db)):
    return await get_all_config(db)
