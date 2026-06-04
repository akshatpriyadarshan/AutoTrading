"""
Risk Manager
Called every 30s by scheduler.
Single-tick: checks all open trades once, then returns.
Scheduler handles the loop and bot-active gate.
"""
import asyncio
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from loguru import logger

from db.database import AsyncSessionLocal
from models.db_models import Trade, TradeStatus, TradeDirection, Alert, AlertLevel, FundSnapshot
from config.config_manager import get_config
from sqlalchemy import select, and_


async def run_risk_checks():
    """Single tick — called by scheduler every 30s."""
    await _check_all_open_trades()
    await _check_daily_drawdown()


async def _check_all_open_trades():
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Trade).where(Trade.status == TradeStatus.OPEN))
        trades = result.scalars().all()
        if not trades:
            return
        for trade in trades:
            await _evaluate_trade(db, trade)
        await db.commit()


async def _evaluate_trade(db, trade: Trade):
    try:
        current_price = await _get_current_price(db, str(trade.pair))
        if current_price is None:
            return

        entry = float(trade.entry_price or 0)
        sl    = float(trade.stop_loss_price or 0)

        if entry <= 0 or sl <= 0:
            return

        sl_breached = (
            (trade.direction == TradeDirection.BUY  and current_price <= sl) or
            (trade.direction == TradeDirection.SELL and current_price >= sl)
        )

        if sl_breached:
            logger.warning(
                f"STOP-LOSS BREACH | trade={trade.id} pair={trade.pair} "
                f"entry={entry} sl={sl} current={current_price}"
            )
            await _close_trade_at_stop_loss(db, trade, current_price)

    except Exception as e:
        logger.error(f"Error evaluating trade {trade.id}: {e}")


async def _close_trade_at_stop_loss(db, trade: Trade, exit_price: float):
    entry   = float(trade.entry_price or exit_price)
    qty     = float(trade.quantity)
    pnl     = (exit_price - entry) * qty if trade.direction == TradeDirection.BUY else (entry - exit_price) * qty
    pnl_pct = ((exit_price - entry) / entry * 100) if entry > 0 else 0
    if trade.direction == TradeDirection.SELL:
        pnl_pct = -pnl_pct

    trade.status     = TradeStatus.CLOSED
    trade.exit_price = Decimal(str(round(exit_price, 8)))
    trade.pnl        = Decimal(str(round(pnl, 2)))
    trade.pnl_pct    = Decimal(str(round(pnl_pct, 4)))
    trade.closed_at  = datetime.now(timezone.utc)
    trade.notes      = (trade.notes or "") + f" | STOP-LOSS at {exit_price}"

    try:
        from services.trade_executor import close_trade_market
        await close_trade_market(trade.id, exit_price, reason="stop_loss")
    except Exception as e:
        logger.error(f"Executor close failed for trade {trade.id}: {e}")

    logger.info(f"Trade {trade.id} closed at stop-loss | pnl=₹{pnl:.2f} ({pnl_pct:.2f}%)")


async def _check_daily_drawdown():
    async with AsyncSessionLocal() as db:
        max_dd = float(await get_config(db, "max_drawdown_pct") or "15")
        today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

        r1 = await db.execute(
            select(FundSnapshot).where(FundSnapshot.snapshot_at >= today_start)
            .order_by(FundSnapshot.snapshot_at.asc()).limit(1)
        )
        r2 = await db.execute(
            select(FundSnapshot).order_by(FundSnapshot.snapshot_at.desc()).limit(1)
        )
        start_snap  = r1.scalar_one_or_none()
        latest_snap = r2.scalar_one_or_none()

        if not start_snap or not latest_snap:
            return

        start_fund   = float(start_snap.total_balance)
        current_fund = float(latest_snap.total_balance)
        if start_fund <= 0:
            return

        drawdown_pct = ((start_fund - current_fund) / start_fund) * 100
        if drawdown_pct >= max_dd:
            logger.critical(f"MAX DRAWDOWN {drawdown_pct:.1f}% >= {max_dd}% — stopping bot")
            from config.config_manager import set_config
            await set_config(db, "bot_active", "false")
            db.add(Alert(
                level    = AlertLevel.CRITICAL,
                category = "drawdown",
                message  = (
                    f"Bot stopped: daily drawdown {drawdown_pct:.1f}% exceeded {max_dd}%. "
                    f"Fund: ₹{current_fund:,.2f} (started day: ₹{start_fund:,.2f})"
                ),
            ))
            await db.commit()


async def _get_current_price(db, pair: str):
    try:
        from services.trade_executor import get_market_price
        return await get_market_price(pair)
    except Exception:
        return None
