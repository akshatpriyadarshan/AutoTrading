"""
Signal Receiver — Webhook API
Receives POST from TradingView Pine Script alerts.
Validates → saves to DB → queues for trade executor.
"""
import json
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Request, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from db.database import get_db
from models.db_models import Signal, SignalSource, TradeDirection
from models.schemas import WebhookSignal, SignalResponse
from services.signal_validator import validate_signal
from services.signal_processor import process_signal

router = APIRouter(prefix="/api/signals", tags=["signals"])


@router.post("/webhook")
async def receive_webhook(
    payload: WebhookSignal,
    background_tasks: BackgroundTasks,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    TradingView webhook endpoint.
    Pine Script alert message format (JSON):
    {
      "secret": "your_webhook_secret",
      "signal": "BUY",
      "pair":   "BTCUSDT",
      "price":  {{close}},
      "atr":    {{ta.atr(14)}},
      "timestamp": "{{time}}"
    }
    """
    client_ip = request.client.host
    logger.info(f"Webhook received | pair={payload.pair} signal={payload.signal} price={payload.price} from={client_ip}")

    # Normalise pair format: BTCUSDT → BTC/USDT
    pair = normalise_pair(payload.pair)

    # Map signal string to direction
    direction_map = {"BUY": TradeDirection.BUY, "SELL": TradeDirection.SELL}

    # Validate
    result = await validate_signal(
        db=db,
        secret=payload.secret,
        direction=payload.signal,
        pair=pair,
        price=payload.price,
        atr=payload.atr,
    )

    # Save signal to DB (whether valid or not — full audit trail)
    signal = Signal(
        source=SignalSource.TRADINGVIEW,
        direction=direction_map.get(payload.signal.upper(), TradeDirection.BUY),
        pair=pair,
        price=payload.price,
        atr=payload.atr,
        raw_payload=payload.model_dump_json(),
        processed=False,
        rejected=not result.ok,
        reject_reason=result.reason if not result.ok else None,
    )
    db.add(signal)
    await db.flush()          # get signal.id before commit
    await db.commit()
    await db.refresh(signal)

    if not result.ok:
        logger.warning(f"Signal rejected | id={signal.id} reason={result.reason}")
        # Return 200 to TradingView (don't want retries on expected rejects)
        return {
            "accepted": False,
            "signal_id": signal.id,
            "reason": result.reason,
        }

    logger.info(f"Signal accepted | id={signal.id} pair={pair} direction={payload.signal}")

    # Handle CLOSE signal separately (close existing position)
    if payload.signal.upper() == "CLOSE":
        background_tasks.add_task(process_signal, signal.id, is_close=True)
    else:
        background_tasks.add_task(process_signal, signal.id, is_close=False)

    return {
        "accepted": True,
        "signal_id": signal.id,
        "pair": pair,
        "direction": payload.signal.upper(),
        "price": payload.price,
    }


@router.get("/", response_model=list[SignalResponse])
async def list_signals(
    limit: int = 50,
    pair: str = None,
    db: AsyncSession = Depends(get_db),
):
    """Return recent signals (for dashboard)."""
    from sqlalchemy import select, desc
    from models.db_models import Signal as SignalModel

    q = select(SignalModel).order_by(desc(SignalModel.received_at)).limit(limit)
    if pair:
        q = q.where(SignalModel.pair == pair.upper())
    result = await db.execute(q)
    return result.scalars().all()


@router.get("/{signal_id}", response_model=SignalResponse)
async def get_signal(signal_id: int, db: AsyncSession = Depends(get_db)):
    from sqlalchemy import select
    result = await db.execute(select(Signal).where(Signal.id == signal_id))
    sig = result.scalar_one_or_none()
    if not sig:
        raise HTTPException(status_code=404, detail="Signal not found")
    return sig


# ── Helpers ───────────────────────────────────────────────────────────────────

def normalise_pair(pair: str) -> str:
    """
    Normalise pair to ASSET/QUOTE format.
    BTCUSDT → BTC/USDT
    BTC-USDT → BTC/USDT
    BTC/USDT → BTC/USDT (unchanged)
    """
    pair = pair.upper().strip()
    if "/" in pair:
        return pair
    if "-" in pair:
        return pair.replace("-", "/")
    # Common quote currencies — try to split
    for quote in ("USDT", "USDC", "BUSD", "BTC", "ETH", "BNB"):
        if pair.endswith(quote) and len(pair) > len(quote):
            base = pair[: -len(quote)]
            return f"{base}/{quote}"
    return pair  # fallback — return as-is
