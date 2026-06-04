"""
Position Sizer
Calculates:
  - Stop-loss price (fixed % or ATR-based)
  - Position quantity (risk-based sizing)

Risk-based sizing formula:
  risk_amount   = available_fund * (risk_pct / 100)
  price_risk    = abs(entry_price - stop_loss_price)
  quantity      = risk_amount / price_risk

This ensures each trade risks exactly risk_pct% of the fund,
regardless of volatility or asset price.
"""
from typing import Optional
from loguru import logger


# ATR multiplier for stop-loss distance (industry standard: 1.5–2.0x ATR)
ATR_MULTIPLIER = 1.5

# Minimum stop-loss distance as % of price (safety floor)
MIN_SL_PCT = 0.5


def calculate_stop_loss(
    direction: str,
    entry_price: float,
    sl_type: str,
    sl_fixed_pct: float,
    atr: Optional[float] = None,
) -> float:
    """
    Calculate stop-loss price.

    Fixed:   SL = entry ± (entry * sl_fixed_pct / 100)
    ATR:     SL = entry ± (ATR * ATR_MULTIPLIER)
             Falls back to fixed if ATR not provided.

    BUY  → SL is below entry (long position protected from downside)
    SELL → SL is above entry (short position protected from upside)
    """
    direction = str(direction).upper()

    if sl_type == "atr" and atr and atr > 0:
        sl_distance = atr * ATR_MULTIPLIER
        logger.debug(f"ATR stop-loss | atr={atr} multiplier={ATR_MULTIPLIER} distance={sl_distance:.4f}")
    else:
        sl_distance = entry_price * (sl_fixed_pct / 100)
        if sl_type == "atr" and not atr:
            logger.warning("ATR stop-loss requested but ATR not in signal — using fixed %")

    # Enforce minimum distance
    min_distance = entry_price * (MIN_SL_PCT / 100)
    sl_distance = max(sl_distance, min_distance)

    if direction == "BUY":
        sl_price = entry_price - sl_distance
    else:
        sl_price = entry_price + sl_distance

    logger.debug(f"Stop-loss | dir={direction} entry={entry_price:.4f} sl={sl_price:.4f} dist={sl_distance:.4f}")
    return round(sl_price, 8)


def calculate_position_size(
    available_fund: float,
    risk_pct: float,
    entry_price: float,
    stop_loss_price: float,
) -> float:
    """
    Risk-based position sizing.
    Quantity = (Fund * Risk%) / |Entry - SL|

    Example:
      fund=$1000, risk=2%, entry=$50000, sl=$49000
      risk_amount = $20
      price_risk  = $1000
      quantity    = 20/1000 = 0.02 BTC
    """
    if available_fund <= 0:
        logger.warning("Position sizer: available_fund is 0")
        return 0.0

    if entry_price <= 0:
        logger.warning("Position sizer: entry_price is 0")
        return 0.0

    price_risk = abs(entry_price - stop_loss_price)

    if price_risk < 0.000001:
        logger.warning("Position sizer: price_risk near zero (entry == stop_loss?)")
        return 0.0

    risk_amount = available_fund * (risk_pct / 100)
    quantity    = risk_amount / price_risk

    # Safety: never risk more than 100% of fund in one trade
    max_quantity = available_fund / entry_price
    if quantity > max_quantity:
        logger.warning(
            f"Position sizer: calculated qty {quantity:.6f} exceeds max "
            f"{max_quantity:.6f} — capping"
        )
        quantity = max_quantity * 0.95  # 5% buffer

    logger.info(
        f"Position size | fund={available_fund:.2f} risk={risk_pct}% "
        f"entry={entry_price:.4f} sl={stop_loss_price:.4f} "
        f"risk_amount={risk_amount:.2f} qty={quantity:.6f}"
    )
    return round(quantity, 8)


def calculate_take_profit(
    direction: str,
    entry_price: float,
    stop_loss_price: float,
    rr_ratio: float = 2.0,
) -> float:
    """
    Calculate take-profit using Risk:Reward ratio.
    Default R:R = 1:2 (risk $1 to make $2).

    TP distance = SL distance * rr_ratio
    """
    sl_distance = abs(entry_price - stop_loss_price)
    tp_distance = sl_distance * rr_ratio
    direction   = str(direction).upper()

    if direction == "BUY":
        tp_price = entry_price + tp_distance
    else:
        tp_price = entry_price - tp_distance

    logger.debug(
        f"Take-profit | dir={direction} entry={entry_price:.4f} "
        f"tp={tp_price:.4f} rr={rr_ratio}"
    )
    return round(tp_price, 8)
