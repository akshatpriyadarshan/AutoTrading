"""
Market Data Fetcher
Fetches free live OHLCV candle data from Binance public API.
No API key required — public endpoints only.
Falls back to KuCoin if Binance unavailable.
"""
import asyncio
from typing import Optional
import pandas as pd
import httpx
from loguru import logger

BINANCE_BASE = "https://api.binance.com/api/v3"
KUCOIN_BASE  = "https://api.kucoin.com/api/v1"

INTERVAL_MAP = {
    "1m": "1m", "5m": "5m", "15m": "15m",
    "1h": "1h", "4h": "4h", "1d": "1d",
}


async def fetch_ohlcv(pair: str, interval: str = "15m", limit: int = 100) -> Optional[pd.DataFrame]:
    """
    Fetch OHLCV candles. Returns DataFrame or None.
    pair:     "BTC/USDT" or "BTCUSDT"
    interval: 1m / 5m / 15m / 1h / 4h / 1d
    """
    symbol   = pair.replace("/", "").upper()
    tf       = INTERVAL_MAP.get(interval, "15m")

    df = await _fetch_binance(symbol, tf, limit)
    if df is not None:
        return df

    logger.warning(f"Binance unavailable for {symbol} — trying KuCoin")
    df = await _fetch_kucoin(pair, tf, limit)
    if df is not None:
        return df

    logger.error(f"All data sources failed for {pair}")
    return None


async def fetch_current_price(pair: str) -> Optional[float]:
    """Quick ticker price — single call, no candle overhead."""
    symbol = pair.replace("/", "").upper()
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(f"{BINANCE_BASE}/ticker/price", params={"symbol": symbol})
            r.raise_for_status()
            return float(r.json()["price"])
    except Exception as e:
        logger.warning(f"fetch_current_price {pair}: {e}")
        return None


# ── Private helpers ───────────────────────────────────────────────────────────

async def _fetch_binance(symbol: str, interval: str, limit: int) -> Optional[pd.DataFrame]:
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(
                f"{BINANCE_BASE}/klines",
                params={"symbol": symbol, "interval": interval, "limit": limit},
            )
            r.raise_for_status()
            raw = r.json()

        df = pd.DataFrame(raw, columns=[
            "timestamp","open","high","low","close","volume",
            "close_time","quote_vol","trades","taker_buy_base",
            "taker_buy_quote","ignore"
        ])
        df = df[["timestamp","open","high","low","close","volume"]].copy()
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
        for col in ["open","high","low","close","volume"]:
            df[col] = df[col].astype(float)
        df = df.sort_values("timestamp").reset_index(drop=True)
        logger.debug(f"Binance: {symbol} {interval} {len(df)} candles")
        return df

    except Exception as e:
        logger.warning(f"Binance fetch failed {symbol}: {e}")
        return None


async def _fetch_kucoin(pair: str, interval: str, limit: int) -> Optional[pd.DataFrame]:
    # KuCoin uses different interval format
    kc_map = {"1m":"1min","5m":"5min","15m":"15min","1h":"1hour","4h":"4hour","1d":"1day"}
    symbol = pair.replace("/", "-").upper()   # BTC/USDT → BTC-USDT
    tf     = kc_map.get(interval, "15min")

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(
                f"{KUCOIN_BASE}/market/candles",
                params={"symbol": symbol, "type": tf},
            )
            r.raise_for_status()
            data = r.json().get("data", [])

        if not data:
            return None

        df = pd.DataFrame(data, columns=["timestamp","open","close","high","low","volume","amount"])
        df = df[["timestamp","open","high","low","close","volume"]].copy()
        df["timestamp"] = pd.to_datetime(df["timestamp"].astype(int), unit="s", utc=True)
        for col in ["open","high","low","close","volume"]:
            df[col] = df[col].astype(float)
        df = df.sort_values("timestamp").reset_index(drop=True)
        df = df.tail(limit).reset_index(drop=True)
        logger.debug(f"KuCoin: {symbol} {tf} {len(df)} candles")
        return df

    except Exception as e:
        logger.warning(f"KuCoin fetch failed {pair}: {e}")
        return None
