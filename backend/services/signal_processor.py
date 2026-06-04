"""
Signal Processor
Background task that runs after a validated signal is saved.
Reads config, calculates position size, stop-loss, then hands off to trade executor.
This is the bridge between "signal received" and "order placed".
"""
from decimal import Decimal
from typing import Optional
from loguru import logger

from db.database import AsyncSessionLocal
from models.db_models import Signal, Trade, TradeDirection, TradeStatus, OrderType
from config.config_manager import get_config
from services.position_sizer import calculate_position_size, calculate_stop_loss


async def process_signal(signal_id: int, is_close: bool = False):
    """
    Entry point called as a FastAPI BackgroundTask.
    Opens its own DB session (background tasks can't share the request session).
    """
    async with AsyncSessionLocal() as db:
        try:
            from sqlalchemy import select
            result = await db.execute(select(Signal).where(Signal.id == signal_id))
            signal = result.scalar_one_or_none()

            if not signal:
                logger.error(f"process_signal: signal {signal_id} not found")
                return

            if is_close:
                await _handle_close(db, signal)
            else:
                await _handle_open(db, signal)

            signal.processed = True
            await db.commit()

        except Exception as e:
            logger.error(f"process_signal error for signal {signal_id}: {e}", exc_info=True)
            await db.rollback()


async def _handle_open(db, signal: Signal):
    """Create a new trade from a BUY/SELL signal."""
    logger.info(f"Processing OPEN signal | id={signal.id} pair={signal.pair} dir={signal.direction}")

    # Load config
    available_fund  = await _get_available_fund(db)
    risk_pct        = float(await get_config(db, "risk_per_trade_pct") or "2")
    sl_type         = await get_config(db, "stop_loss_type") or "fixed"
    sl_fixed_pct    = float(await get_config(db, "stop_loss_fixed_pct") or "2")

    entry_price = float(signal.price)
    atr         = float(signal.atr) if signal.atr else None

    # Calculate stop-loss price
    sl_price = calculate_stop_loss(
        direction=signal.direction,
        entry_price=entry_price,
        sl_type=sl_type,
        sl_fixed_pct=sl_fixed_pct,
        atr=atr,
    )

    # Calculate position size (how much to buy/sell)
    quantity = calculate_position_size(
        available_fund=available_fund,
        risk_pct=risk_pct,
        entry_price=entry_price,
        stop_loss_price=sl_price,
    )

    if quantity <= 0:
        logger.warning(f"Position size is 0 for signal {signal.id} — skipping")
        signal.rejected = True
        signal.reject_reason = "Calculated position size is 0 (check fund/risk config)"
        return

    # Create trade record (PENDING — executor will update to OPEN)
    trade = Trade(
        signal_id       = signal.id,
        pair            = signal.pair,
        direction       = signal.direction,
        order_type      = OrderType.MARKET,
        status          = TradeStatus.PENDING,
        quantity        = Decimal(str(round(quantity, 8))),
        entry_price     = None,          # filled by executor after order placed
        stop_loss_price = Decimal(str(round(sl_price, 8))),
        fund_at_entry   = Decimal(str(round(available_fund, 2))),
        notes           = f"Signal #{signal.id} | ATR={atr} | SL type={sl_type}",
    )
    db.add(trade)
    await db.flush()
    await db.commit()  # commit BEFORE executor so it can see the trade

    logger.info(
        f"Trade created | id={trade.id} pair={signal.pair} "
        f"dir={signal.direction} qty={quantity:.6f} sl={sl_price:.4f}"
    )

    # Hand off to executor
    try:
        from services.trade_executor import execute_trade
        await execute_trade(trade.id)
    except Exception as e:
        logger.error(f"Executor failed for trade {trade.id}: {e}")


async def _handle_close(db, signal: Signal):
    """Close any open trade for this pair."""
    from sqlalchemy import select, and_
    logger.info(f"Processing CLOSE signal | id={signal.id} pair={signal.pair}")

    result = await db.execute(
        select(Trade).where(
            and_(
                Trade.pair   == signal.pair,
                Trade.status == TradeStatus.OPEN,
            )
        )
    )
    open_trades = result.scalars().all()

    if not open_trades:
        logger.info(f"CLOSE signal for {signal.pair} — no open trades found")
        return

    for trade in open_trades:
        logger.info(f"Closing trade {trade.id} for {signal.pair} at {signal.price}")
        trade.notes = (trade.notes or "") + f" | CLOSE triggered by signal #{signal.id}"
        try:
            from services.trade_executor import close_trade_market
            await close_trade_market(trade.id, float(signal.price), reason="close_signal")
        except Exception as e:
            logger.error(f"Executor close failed for trade {trade.id}: {e}")


async def _get_available_fund(db) -> float:
    """
    Get current available trading fund.
    Uses latest FundSnapshot if available, else falls back to starting_capital.
    """
    from sqlalchemy import select, desc
    from models.db_models import FundSnapshot

    result = await db.execute(
        select(FundSnapshot).order_by(desc(FundSnapshot.snapshot_at)).limit(1)
    )
    snapshot = result.scalar_one_or_none()

    if snapshot:
        return float(snapshot.available)

    # Fallback: use configured starting capital
    capital = await get_config(db, "starting_capital") or "0"
    return float(capital)
