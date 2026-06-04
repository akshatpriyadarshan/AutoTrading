"""
Signal Engine API — status and manual trigger
"""
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from db.database import get_db
from sqlalchemy.ext.asyncio import AsyncSession
from config.config_manager import get_config

router = APIRouter(prefix="/api/engine", tags=["engine"])


@router.get("/status")
async def engine_status(db: AsyncSession = Depends(get_db)):
    """Return current signal engine configuration and next run time."""
    import time
    from services.scheduler import CANDLE_SECONDS
    interval = await get_config(db, "candle_interval") or "15m"
    active   = await get_config(db, "bot_active") == "true"
    period   = CANDLE_SECONDS.get(interval, 900)
    now      = time.time()
    next_in  = period - (now % period)
    return {
        "active":           active,
        "interval":         interval,
        "next_run_seconds": round(next_in),
        "data_source":      "Binance public API (free)",
        "strategy":         "EMA9/21 crossover + RSI(14) + Volume spike",
    }


@router.post("/run-now")
async def run_engine_now(background_tasks: BackgroundTasks, db: AsyncSession = Depends(get_db)):
    """Manually trigger a signal engine run (useful for testing)."""
    if await get_config(db, "setup_complete") != "true":
        raise HTTPException(400, "Setup not complete")
    if await get_config(db, "bot_active") != "true":
        raise HTTPException(400, "Bot not active — start the bot first")

    from services.signal_engine import run_signal_engine
    background_tasks.add_task(run_signal_engine)
    return {"success": True, "message": "Signal engine triggered — check signals feed in a few seconds"}
