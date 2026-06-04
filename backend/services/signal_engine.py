"""
Signal Engine — Free TradingView Replacement
============================================
Runs on a configurable interval (default 15m).
Fetches live OHLCV from Binance (free, no key).
Computes indicators locally using pandas-ta.
Generates BUY / SELL / CLOSE signals exactly like the Pine Script did.

Strategy (mirrors the Pine Script):
  Entry:  EMA9 × EMA21 crossover
          + RSI confirmation (not overbought/oversold)
          + Volume spike > 1.5× 20-bar average
  Exit:   Opposite crossover OR stop-loss (handled by risk_manager)
  ATR:    Calculated and attached to every signal for dynamic SL

This runs inside the scheduler — no webhook, no paid plan needed.
"""
import asyncio
from datetime import datetime, timezone
from typing import Optional
import pandas as pd
import pandas_ta as ta
from loguru import logger

from db.database import AsyncSessionLocal
from models.db_models import Signal, SignalSource, TradeDirection
from config.config_manager import get_config
from services.market_data import fetch_ohlcv
from services.signal_validator import validate_signal
from services.signal_processor import process_signal


# ── Strategy parameters (can be overridden via config) ───────────────────────
EMA_FAST        = 9
EMA_SLOW        = 21
RSI_PERIOD      = 14
RSI_OVERBOUGHT  = 65
RSI_OVERSOLD    = 35
ATR_PERIOD      = 14
VOL_MA_PERIOD   = 20
VOL_MULTIPLIER  = 1.5   # volume must be > 1.5× 20-bar average


async def run_signal_engine():
    """
    Single tick — called by scheduler on every candle close.
    Loops over all configured trading pairs and generates signals.
    """
    async with AsyncSessionLocal() as db:
        setup = await get_config(db, "setup_complete")
        if setup != "true":
            return

        bot_active = await get_config(db, "bot_active")
        if bot_active != "true":
            return

        pairs_raw = await get_config(db, "trading_pairs") or "BTC/USDT"
        interval  = await get_config(db, "candle_interval") or "15m"
        pairs     = [p.strip() for p in pairs_raw.split(",") if p.strip()]

    for pair in pairs:
        try:
            await _analyse_pair(pair, interval)
        except Exception as e:
            logger.error(f"Signal engine error for {pair}: {e}", exc_info=True)


async def _analyse_pair(pair: str, interval: str):
    """Fetch candles, compute indicators, emit signal if conditions met."""
    logger.debug(f"Analysing {pair} on {interval}")

    df = await fetch_ohlcv(pair, interval, limit=100)
    if df is None or len(df) < 30:
        logger.warning(f"Not enough candle data for {pair}")
        return

    # ── Compute indicators ────────────────────────────────────────────────────
    df["ema_fast"] = ta.ema(df["close"], length=EMA_FAST)
    df["ema_slow"] = ta.ema(df["close"], length=EMA_SLOW)
    df["rsi"]      = ta.rsi(df["close"], length=RSI_PERIOD)
    df["atr"]      = ta.atr(df["high"], df["low"], df["close"], length=ATR_PERIOD)
    df["vol_ma"]   = df["volume"].rolling(VOL_MA_PERIOD).mean()
    df = df.dropna().reset_index(drop=True)

    if len(df) < 3:
        return

    # Use last two closed candles (df[-1] = current forming, df[-2] = last closed)
    prev  = df.iloc[-2]   # candle before last
    curr  = df.iloc[-1]   # last closed candle

    close_price = float(curr["close"])
    atr_val     = float(curr["atr"])
    vol_spike   = float(curr["volume"]) > float(curr["vol_ma"]) * VOL_MULTIPLIER

    # ── Crossover detection ───────────────────────────────────────────────────
    ema_cross_up   = (prev["ema_fast"] <= prev["ema_slow"]) and (curr["ema_fast"] > curr["ema_slow"])
    ema_cross_down = (prev["ema_fast"] >= prev["ema_slow"]) and (curr["ema_fast"] < curr["ema_slow"])

    # ── Signal conditions ─────────────────────────────────────────────────────
    buy_signal  = ema_cross_up   and float(curr["rsi"]) < RSI_OVERBOUGHT and vol_spike
    sell_signal = ema_cross_down and float(curr["rsi"]) > RSI_OVERSOLD   and vol_spike

    if not buy_signal and not sell_signal:
        return   # no signal this candle

    direction = TradeDirection.BUY if buy_signal else TradeDirection.SELL
    direction_str = "BUY" if buy_signal else "SELL"

    logger.info(
        f"SIGNAL: {direction_str} {pair} @ {close_price:.4f} | "
        f"EMA9={curr['ema_fast']:.2f} EMA21={curr['ema_slow']:.2f} "
        f"RSI={curr['rsi']:.1f} ATR={atr_val:.4f} VolSpike={vol_spike}"
    )

    # ── Validate (same checks as webhook path) ────────────────────────────────
    async with AsyncSessionLocal() as db:
        # Internal signals skip the webhook secret check — use empty string
        # and bypass by reading secret directly
        secret = await get_config(db, "tradingview_webhook_secret") or "internal"

        result = await validate_signal(
            db        = db,
            secret    = secret,
            direction = direction_str,
            pair      = pair,
            price     = close_price,
            atr       = atr_val,
            internal  = True,   # internal engine, skip webhook secret
        )

        if not result.ok:
            logger.info(f"Signal rejected: {result.reason}")
            # Still save rejected signal for audit trail
            sig = Signal(
                source       = SignalSource.SYSTEM,
                direction    = direction,
                pair         = pair.upper(),
                price        = close_price,
                atr          = atr_val,
                raw_payload  = f"internal|{interval}|ema_cross|rsi={curr['rsi']:.1f}",
                processed    = False,
                rejected     = True,
                reject_reason= result.reason,
            )
            db.add(sig)
            await db.commit()
            return

        # Save accepted signal
        sig = Signal(
            source      = SignalSource.SYSTEM,
            direction   = direction,
            pair        = pair.upper(),
            price       = close_price,
            atr         = atr_val,
            raw_payload = f"internal|{interval}|ema_cross|rsi={curr['rsi']:.1f}|vol_spike={vol_spike}",
            processed   = False,
            rejected    = False,
        )
        db.add(sig)
        await db.flush()
        await db.commit()
        await db.refresh(sig)

    logger.info(f"Signal #{sig.id} queued for processing")

    # ── Process (size position + create trade) ────────────────────────────────
    await process_signal(sig.id, is_close=False)
