"""
Scheduler — starts all background loops on app startup.
  - Signal Engine   every candle interval (15m default) — replaces TradingView
  - Risk checks     every 30s
  - Alert monitor   every 60s
  - Fund snapshot   every hour
  - Daily report    8 PM IST (14:30 UTC)
"""
import asyncio
from datetime import datetime, timezone, timedelta
from loguru import logger

_tasks = []

# Intervals in seconds
RISK_INTERVAL     = 30
ALERT_INTERVAL    = 60
SNAPSHOT_INTERVAL = 3600
REPORT_HOUR_UTC   = 14
REPORT_MINUTE_UTC = 30

CANDLE_SECONDS = {
    "1m": 60, "5m": 300, "15m": 900,
    "1h": 3600, "4h": 14400, "1d": 86400,
}


async def start_all():
    logger.info("Starting background schedulers…")
    _tasks.clear()
    _tasks.append(asyncio.create_task(_signal_engine_loop(), name="signal_engine"))
    _tasks.append(asyncio.create_task(_risk_loop(),          name="risk"))
    _tasks.append(asyncio.create_task(_alert_loop(),         name="alerts"))
    _tasks.append(asyncio.create_task(_snapshot_loop(),      name="fund_snap"))
    _tasks.append(asyncio.create_task(_report_loop(),        name="daily_report"))
    logger.info(f"{len(_tasks)} background tasks started")


async def stop_all():
    for t in _tasks:
        t.cancel()
    await asyncio.gather(*_tasks, return_exceptions=True)
    logger.info("Background tasks stopped")


# ── Signal Engine loop ────────────────────────────────────────────────────────

async def _signal_engine_loop():
    """
    Waits until the next candle close, then runs analysis.
    E.g. for 15m: waits until :00, :15, :30, :45 each hour.
    This ensures we always analyse a fully-closed candle.
    """
    while True:
        try:
            interval = await _get_interval()
            wait = _seconds_to_next_candle(interval)
            logger.info(f"Signal engine: next run in {wait:.0f}s (interval={interval})")
            await asyncio.sleep(wait)

            if await _bot_active():
                from services.signal_engine import run_signal_engine
                await run_signal_engine()
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Signal engine loop error: {e}", exc_info=True)
            await asyncio.sleep(60)


def _seconds_to_next_candle(interval: str) -> float:
    """Calculate seconds until the next candle boundary."""
    import time
    period = CANDLE_SECONDS.get(interval, 900)
    now    = time.time()
    return period - (now % period)


async def _get_interval() -> str:
    try:
        from db.database import AsyncSessionLocal
        from config.config_manager import get_config
        async with AsyncSessionLocal() as db:
            return await get_config(db, "candle_interval") or "15m"
    except Exception:
        return "15m"


# ── Other loops ───────────────────────────────────────────────────────────────

async def _risk_loop():
    while True:
        try:
            if await _bot_active():
                from services.risk_manager import run_risk_checks
                await run_risk_checks()
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Risk loop error: {e}")
        await asyncio.sleep(RISK_INTERVAL)


async def _alert_loop():
    while True:
        try:
            from services.alert_system import process_pending_alerts
            await process_pending_alerts()
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Alert loop error: {e}")
        await asyncio.sleep(ALERT_INTERVAL)


async def _snapshot_loop():
    while True:
        try:
            await asyncio.sleep(SNAPSHOT_INTERVAL)
            if await _bot_active():
                from services.fund_manager import take_fund_snapshot
                await take_fund_snapshot()
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Snapshot loop error: {e}")


async def _report_loop():
    while True:
        try:
            now      = datetime.now(timezone.utc)
            next_run = now.replace(hour=REPORT_HOUR_UTC, minute=REPORT_MINUTE_UTC, second=0, microsecond=0)
            if next_run <= now:
                next_run += timedelta(days=1)
            await asyncio.sleep((next_run - now).total_seconds())
            from services.daily_reporter import send_daily_report
            await send_daily_report()
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Report loop error: {e}")
            await asyncio.sleep(3600)


async def _bot_active() -> bool:
    try:
        from db.database import AsyncSessionLocal
        from config.config_manager import get_config
        async with AsyncSessionLocal() as db:
            return await get_config(db, "bot_active") == "true"
    except Exception:
        return False
