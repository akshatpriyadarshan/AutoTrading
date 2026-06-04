"""
Signal Test API
Allows dry-run signal firing without TradingView.
Useful for verifying the full webhook → validator → processor pipeline.
Only available when bot is in testnet mode.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from typing import Optional
from loguru import logger

from db.database import get_db
from config.config_manager import get_config
from services.signal_validator import validate_signal
from services.position_sizer import (
    calculate_stop_loss,
    calculate_position_size,
    calculate_take_profit,
)

router = APIRouter(prefix="/api/test", tags=["testing"])


class TestSignalRequest(BaseModel):
    pair: str = "BTC/USDT"
    signal: str = "BUY"          # BUY | SELL | CLOSE
    price: float = 65000.0
    atr: Optional[float] = 1200.0


class TestSignalResponse(BaseModel):
    validation_passed: bool
    rejection_reason: Optional[str]
    calculated: Optional[dict]


@router.post("/signal", response_model=TestSignalResponse)
async def test_signal(payload: TestSignalRequest, db: AsyncSession = Depends(get_db)):
    """
    Dry-run a signal through the full validation + sizing pipeline.
    Does NOT place any trade or fire webhooks.
    Returns what the system would do with this signal.
    """
    testnet = await get_config(db, "delta_testnet")
    if testnet != "true":
        raise HTTPException(
            status_code=403,
            detail="Test endpoint only available in testnet mode. Switch to testnet in setup."
        )

    # Get webhook secret for validation
    secret = await get_config(db, "tradingview_webhook_secret") or ""

    result = await validate_signal(
        db=db,
        secret=secret,           # use real secret so validation passes in test
        direction=payload.signal,
        pair=payload.pair,
        price=payload.price,
        atr=payload.atr,
    )

    if not result.ok:
        return TestSignalResponse(
            validation_passed=False,
            rejection_reason=result.reason,
            calculated=None,
        )

    # Simulate sizing
    sl_type      = await get_config(db, "stop_loss_type") or "fixed"
    sl_fixed_pct = float(await get_config(db, "stop_loss_fixed_pct") or "2")
    risk_pct     = float(await get_config(db, "risk_per_trade_pct") or "2")
    capital_raw  = await get_config(db, "starting_capital") or "1000"
    capital      = float(capital_raw)

    atr_val = float(payload.atr) if payload.atr else None
    sl_price = calculate_stop_loss(
        direction=payload.signal,
        entry_price=payload.price,
        sl_type=sl_type,
        sl_fixed_pct=sl_fixed_pct,
        atr=atr_val,
    )
    quantity = calculate_position_size(
        available_fund=capital,
        risk_pct=risk_pct,
        entry_price=payload.price,
        stop_loss_price=sl_price,
    )
    tp_price = calculate_take_profit(
        direction=payload.signal,
        entry_price=payload.price,
        stop_loss_price=sl_price,
    )

    risk_amount  = capital * (risk_pct / 100)
    trade_value  = quantity * payload.price

    return TestSignalResponse(
        validation_passed=True,
        rejection_reason=None,
        calculated={
            "pair":            payload.pair,
            "direction":       payload.signal,
            "entry_price":     payload.price,
            "stop_loss_price": sl_price,
            "take_profit_price": tp_price,
            "quantity":        quantity,
            "trade_value_usdt": round(trade_value, 2),
            "risk_amount_usdt": round(risk_amount, 2),
            "risk_pct":        risk_pct,
            "sl_type":         sl_type,
            "note":            "DRY RUN — no order placed",
        },
    )


@router.get("/ping")
async def ping():
    """Simple connectivity check."""
    return {"status": "ok", "message": "AutoCrypto backend reachable"}


@router.get("/config-check")
async def config_check(db: AsyncSession = Depends(get_db)):
    """Verify all required config keys are set (values masked)."""
    from config.config_manager import CONFIG_KEYS, get_all_config
    all_cfg = await get_all_config(db)

    missing = []
    present = []
    for key in CONFIG_KEYS:
        if key in all_cfg and all_cfg[key] not in (None, "", "***"):
            present.append(key)
        elif key in all_cfg and all_cfg[key] == "***":
            present.append(key)   # secret is set (masked)
        else:
            missing.append(key)

    return {
        "total_keys":   len(CONFIG_KEYS),
        "present":      len(present),
        "missing":      missing,
        "ready":        len(missing) == 0,
    }
