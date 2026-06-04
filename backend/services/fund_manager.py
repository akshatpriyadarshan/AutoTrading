"""
Fund Manager
Tracks the trading fund at all times.
Applies the 25% lock rule when profit milestone is hit.
Creates fund snapshots for reporting.
"""
from decimal import Decimal
from datetime import datetime, timezone
from loguru import logger

from db.database import AsyncSessionLocal
from models.db_models import FundSnapshot, Trade, TradeStatus, Alert, AlertLevel
from config.config_manager import get_config
from sqlalchemy import select, func


async def take_fund_snapshot() -> dict:
    """
    Calculate current fund state and save a snapshot.
    Called after every trade close and on schedule (hourly).
    Returns snapshot dict.
    """
    async with AsyncSessionLocal() as db:
        # Config
        starting_capital = float(await get_config(db, "starting_capital") or "0")
        lock_threshold   = float(await get_config(db, "profit_lock_threshold") or "100")
        lock_pct         = float(await get_config(db, "profit_lock_pct") or "25")

        # Try to get real balance from exchange
        total_balance = await _get_exchange_balance(db)
        if total_balance is None:
            # Fall back to last snapshot + PnL
            total_balance = await _estimate_balance_from_trades(db, starting_capital)

        # Calculate what's locked in open trades
        open_result = await db.execute(
            select(Trade).where(Trade.status == TradeStatus.OPEN)
        )
        open_trades  = open_result.scalars().all()
        in_trades    = sum(
            float(t.quantity) * float(t.entry_price or 0)
            for t in open_trades
        )

        # Total accumulated locked (from previous milestones)
        prev_snap = await _get_latest_snapshot(db)
        locked_so_far = float(prev_snap.locked_25pct) if prev_snap else 0.0

        available = max(0.0, total_balance - in_trades - locked_so_far)

        # PnL
        pnl_total = total_balance - starting_capital + locked_so_far
        pnl_pct   = (pnl_total / starting_capital * 100) if starting_capital > 0 else 0

        # Today's PnL
        today_pnl = await _todays_pnl(db)

        # Check profit milestone
        milestone_hit = False
        new_locked    = locked_so_far

        if starting_capital > 0:
            profit_pct = ((total_balance + locked_so_far - starting_capital) / starting_capital) * 100
            if profit_pct >= lock_threshold:
                # Check if we've already locked for this milestone level
                milestone_level = int(profit_pct // lock_threshold)
                last_level      = await _last_milestone_level(db)
                if milestone_level > last_level:
                    lock_amount = total_balance * (lock_pct / 100)
                    new_locked  = locked_so_far + lock_amount
                    available   = max(0.0, total_balance - in_trades - new_locked)
                    milestone_hit = True
                    logger.info(
                        f"MILESTONE HIT | profit={profit_pct:.1f}% "
                        f"locking ₹{lock_amount:,.2f} | "
                        f"total locked=₹{new_locked:,.2f}"
                    )
                    # Create info alert
                    alert = Alert(
                        level    = AlertLevel.INFO,
                        category = "milestone",
                        message  = (
                            f"Profit milestone reached! {profit_pct:.1f}% profit. "
                            f"Locked ₹{lock_amount:,.2f} ({lock_pct}%). "
                            f"Trading with ₹{available:,.2f}."
                        ),
                    )
                    db.add(alert)

        snap = FundSnapshot(
            total_balance = Decimal(str(round(total_balance, 2))),
            available     = Decimal(str(round(available, 2))),
            locked_25pct  = Decimal(str(round(new_locked, 2))),
            in_trades     = Decimal(str(round(in_trades, 2))),
            starting_fund = Decimal(str(round(starting_capital, 2))),
            pnl_today     = Decimal(str(round(today_pnl, 2))),
            pnl_total     = Decimal(str(round(pnl_total, 2))),
            milestone_hit = milestone_hit,
        )
        db.add(snap)
        await db.commit()
        await db.refresh(snap)

        return {
            "total_balance": total_balance,
            "available":     available,
            "locked":        new_locked,
            "in_trades":     in_trades,
            "pnl_today":     today_pnl,
            "pnl_total":     pnl_total,
            "pnl_pct":       round(pnl_pct, 2),
            "milestone_hit": milestone_hit,
        }


async def get_available_fund() -> float:
    """Quick helper — returns available trading fund."""
    async with AsyncSessionLocal() as db:
        snap = await _get_latest_snapshot(db)
        if snap:
            return float(snap.available)
        capital = await get_config(db, "starting_capital") or "0"
        return float(capital)


# ── Private helpers ───────────────────────────────────────────────────────────

async def _get_exchange_balance(db) -> float | None:
    """Try to get USDT balance from Delta Exchange. Safe to call before setup complete."""
    try:
        setup = await get_config(db, "setup_complete")
        if setup != "true":
            return None
        from services.trade_executor import get_wallet_balance
        return await get_wallet_balance()
    except Exception:
        return None


async def _estimate_balance_from_trades(db, starting_capital: float) -> float:
    """Estimate balance = starting + sum of all closed PnL."""
    result = await db.execute(
        select(func.sum(Trade.pnl))
        .where(Trade.status == TradeStatus.CLOSED)
        .where(Trade.pnl.isnot(None))
    )
    total_pnl = result.scalar() or 0
    return starting_capital + float(total_pnl)


async def _todays_pnl(db) -> float:
    """Sum PnL of trades closed today."""
    from datetime import date
    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    result = await db.execute(
        select(func.sum(Trade.pnl))
        .where(Trade.status == TradeStatus.CLOSED)
        .where(Trade.closed_at >= today)
        .where(Trade.pnl.isnot(None))
    )
    return float(result.scalar() or 0)


async def _get_latest_snapshot(db) -> FundSnapshot | None:
    result = await db.execute(
        select(FundSnapshot)
        .order_by(FundSnapshot.snapshot_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def _last_milestone_level(db) -> int:
    """How many milestone locks have been triggered so far."""
    result = await db.execute(
        select(func.count(FundSnapshot.id))
        .where(FundSnapshot.milestone_hit == True)
    )
    return int(result.scalar() or 0)
