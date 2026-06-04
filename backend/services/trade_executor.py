"""
Trade Executor
Connects to Delta Exchange API.
Places market orders, monitors fills, updates trade records.
Uses ccxt library which supports Delta Exchange.
"""
import asyncio
from decimal import Decimal
from datetime import datetime, timezone
from typing import Optional
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from db.database import AsyncSessionLocal
from models.db_models import Trade, TradeStatus, TradeDirection, Alert, AlertLevel
from config.config_manager import get_config
from sqlalchemy import select


# ── Exchange client (lazy init) ───────────────────────────────────────────────
_exchange = None


async def _get_exchange():
    """Get or create ccxt Delta Exchange client."""
    global _exchange
    if _exchange:
        return _exchange

    import ccxt.async_support as ccxt

    async with AsyncSessionLocal() as db:
        api_key    = await get_config(db, "delta_api_key") or ""
        api_secret = await get_config(db, "delta_api_secret") or ""
        testnet    = await get_config(db, "delta_testnet") or "true"

    if not api_key or not api_secret:
        raise ValueError("Delta Exchange API credentials not configured")

    _exchange = ccxt.delta({
        "apiKey":    api_key,
        "secret":    api_secret,
        "enableRateLimit": True,
    })

    if testnet == "true":
        _exchange.set_sandbox_mode(True)
        logger.info("Delta Exchange: TESTNET mode")
    else:
        logger.info("Delta Exchange: LIVE mode")

    return _exchange


def reset_exchange():
    """Call this after re-configuration to force reconnect."""
    global _exchange
    _exchange = None


# ── Public interface ──────────────────────────────────────────────────────────

async def execute_trade(trade_id: int):
    """
    Main entry point. Called by signal_processor after creating a PENDING trade.
    Places a market order, waits for fill, updates trade record.
    """
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Trade).where(Trade.id == trade_id))
        trade  = result.scalar_one_or_none()

        if not trade:
            logger.error(f"execute_trade: trade {trade_id} not found")
            return

        if trade.status != TradeStatus.PENDING:
            logger.warning(f"execute_trade: trade {trade_id} is {trade.status}, skipping")
            return

        try:
            order = await _place_market_order(
                pair      = str(trade.pair),
                direction = str(trade.direction.value),
                quantity  = float(trade.quantity),
            )

            # Update trade with exchange order details
            fill_price = float(order.get("average") or order.get("price") or 0)
            trade.exchange_order_id = str(order.get("id", ""))
            trade.status            = TradeStatus.OPEN
            trade.entry_price       = Decimal(str(round(fill_price, 8))) if fill_price else trade.entry_price

            await db.commit()
            logger.info(
                f"Trade {trade_id} OPENED | pair={trade.pair} "
                f"qty={trade.quantity} fill={fill_price} "
                f"order_id={trade.exchange_order_id}"
            )

            # Take fund snapshot after opening trade
            from services.fund_manager import take_fund_snapshot
            await take_fund_snapshot()

        except Exception as e:
            trade.status = TradeStatus.FAILED
            trade.notes  = (trade.notes or "") + f" | OPEN FAILED: {e}"
            await db.commit()
            await _create_alert(
                category = "trade",
                level    = AlertLevel.WARNING,
                message  = f"Failed to open trade {trade_id} for {trade.pair}: {e}",
            )
            logger.error(f"execute_trade {trade_id} failed: {e}", exc_info=True)


async def close_trade_market(trade_id: int, exit_price: float, reason: str = "signal"):
    """
    Close an open trade at market price.
    Called by risk_manager (stop-loss) or signal_processor (CLOSE signal).
    """
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Trade).where(Trade.id == trade_id))
        trade  = result.scalar_one_or_none()

        if not trade or trade.status != TradeStatus.OPEN:
            return

        try:
            # Closing a BUY = sell; closing a SELL = buy
            close_direction = "sell" if trade.direction == TradeDirection.BUY else "buy"
            order = await _place_market_order(
                pair      = str(trade.pair),
                direction = close_direction,
                quantity  = float(trade.quantity),
            )

            actual_exit = float(order.get("average") or order.get("price") or exit_price)
            entry       = float(trade.entry_price or actual_exit)

            if trade.direction == TradeDirection.BUY:
                pnl = (actual_exit - entry) * float(trade.quantity)
            else:
                pnl = (entry - actual_exit) * float(trade.quantity)

            pnl_pct = ((actual_exit - entry) / entry * 100) if entry > 0 else 0
            if trade.direction == TradeDirection.SELL:
                pnl_pct = -pnl_pct

            trade.status     = TradeStatus.CLOSED
            trade.exit_price = Decimal(str(round(actual_exit, 8)))
            trade.pnl        = Decimal(str(round(pnl, 2)))
            trade.pnl_pct    = Decimal(str(round(pnl_pct, 4)))
            trade.closed_at  = datetime.now(timezone.utc)
            trade.notes      = (trade.notes or "") + f" | CLOSED via {reason}"

            await db.commit()
            logger.info(
                f"Trade {trade_id} CLOSED | reason={reason} "
                f"exit={actual_exit} pnl={pnl:.2f} ({pnl_pct:.2f}%)"
            )

            # Update fund after close
            from services.fund_manager import take_fund_snapshot
            await take_fund_snapshot()

        except Exception as e:
            await _create_alert(
                category = "trade",
                level    = AlertLevel.WARNING,
                message  = f"Failed to close trade {trade_id}: {e}",
            )
            logger.error(f"close_trade_market {trade_id} failed: {e}", exc_info=True)


async def get_market_price(pair: str) -> Optional[float]:
    """Get current mid price for a pair."""
    try:
        exchange = await _get_exchange()
        symbol   = pair.replace("/", "/")   # ccxt format: BTC/USDT
        ticker   = await exchange.fetch_ticker(symbol)
        price    = ticker.get("last") or ticker.get("bid")
        return float(price) if price else None
    except Exception as e:
        logger.warning(f"get_market_price {pair} failed: {e}")
        return None


async def get_wallet_balance() -> Optional[float]:
    """Get USDT balance from Delta Exchange."""
    try:
        exchange = await _get_exchange()
        balance  = await exchange.fetch_balance()
        usdt     = balance.get("USDT", {})
        free     = usdt.get("free") or usdt.get("total") or 0
        return float(free)
    except Exception as e:
        logger.warning(f"get_wallet_balance failed: {e}")
        return None


# ── Private helpers ───────────────────────────────────────────────────────────

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type(Exception),
    reraise=True,
)
async def _place_market_order(pair: str, direction: str, quantity: float) -> dict:
    """
    Place a market order on Delta Exchange.
    Retries up to 3 times on failure.
    """
    exchange = await _get_exchange()
    symbol   = pair  # BTC/USDT
    side     = direction.lower()  # buy / sell

    logger.info(f"Placing {side.upper()} market order | {symbol} qty={quantity}")

    order = await exchange.create_order(
        symbol   = symbol,
        type     = "market",
        side     = side,
        amount   = quantity,
    )

    logger.info(
        f"Order placed | id={order.get('id')} status={order.get('status')} "
        f"filled={order.get('filled')} avg={order.get('average')}"
    )
    return order


async def _create_alert(category: str, level: AlertLevel, message: str):
    async with AsyncSessionLocal() as db:
        db.add(Alert(level=level, category=category, message=message))
        await db.commit()
