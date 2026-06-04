"""
Signal Validator
Validates signals from both webhook (external) and signal engine (internal).
Internal signals from the built-in engine skip the webhook secret check.
"""
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from models.db_models import Signal, TradeStatus, Trade, TradeDirection
from config.config_manager import get_config

SIGNAL_COOLDOWN_SECONDS = 60
INTERNAL_SOURCE = "internal"   # used by signal_engine to bypass secret check


class ValidationResult:
    def __init__(self, ok: bool, reason: str = ""):
        self.ok     = ok
        self.reason = reason

    def __bool__(self):
        return self.ok


async def validate_signal(
    db: AsyncSession,
    secret: str,
    direction: str,
    pair: str,
    price: float,
    atr: Optional[float],
    internal: bool = False,   # True = from built-in engine, skip secret check
) -> ValidationResult:

    # 1 ── Secret check (skipped for internal engine signals) ─────────────────
    if not internal:
        expected = await get_config(db, "tradingview_webhook_secret")
        if not expected:
            return ValidationResult(False, "Webhook secret not configured")
        import hmac
        if not hmac.compare_digest(str(secret), str(expected)):
            logger.warning(f"Invalid webhook secret for pair={pair}")
            return ValidationResult(False, "Invalid webhook secret")

    # 2 ── Bot active ──────────────────────────────────────────────────────────
    if await get_config(db, "bot_active") != "true":
        return ValidationResult(False, "Bot is not active")

    # 3 ── Setup complete ──────────────────────────────────────────────────────
    if await get_config(db, "setup_complete") != "true":
        return ValidationResult(False, "Setup not complete")

    # 4 ── Allowed pairs ───────────────────────────────────────────────────────
    pairs_raw    = await get_config(db, "trading_pairs") or ""
    allowed      = [p.strip().upper() for p in pairs_raw.split(",") if p.strip()]
    if allowed and pair.upper() not in allowed:
        return ValidationResult(False, f"{pair} not in allowed pairs")

    # 5 ── Direction ───────────────────────────────────────────────────────────
    if direction.upper() not in ("BUY", "SELL", "CLOSE"):
        return ValidationResult(False, f"Unknown direction: {direction}")

    # 6 ── Price ───────────────────────────────────────────────────────────────
    if not price or price <= 0:
        return ValidationResult(False, f"Invalid price: {price}")

    # 7 ── Cooldown ────────────────────────────────────────────────────────────
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=SIGNAL_COOLDOWN_SECONDS)
    recent = await db.execute(
        select(Signal).where(
            and_(
                Signal.pair       == pair.upper(),
                Signal.received_at >= cutoff,
                Signal.rejected   == False,
            )
        ).order_by(Signal.received_at.desc()).limit(1)
    )
    if recent.scalar_one_or_none():
        return ValidationResult(False, f"Cooldown active for {pair} ({SIGNAL_COOLDOWN_SECONDS}s)")

    # 8 ── Max open trades (BUY only) ──────────────────────────────────────────
    if direction.upper() == "BUY":
        max_t  = int(await get_config(db, "max_open_trades") or "3")
        result = await db.execute(select(Trade).where(Trade.status == TradeStatus.OPEN))
        if len(result.scalars().all()) >= max_t:
            return ValidationResult(False, f"Max open trades reached ({max_t})")

        # No duplicate BUY for same pair
        dup = await db.execute(
            select(Trade).where(and_(
                Trade.pair      == pair.upper(),
                Trade.status    == TradeStatus.OPEN,
                Trade.direction == TradeDirection.BUY,
            ))
        )
        if dup.scalar_one_or_none():
            return ValidationResult(False, f"Already have open BUY for {pair}")

    return ValidationResult(True)
