"""
Pydantic schemas for request/response validation
"""
from datetime import datetime
from decimal import Decimal
from typing import Optional, List
from pydantic import BaseModel, EmailStr, field_validator, model_validator
import re


# ──────────────────────────────────────────────────────────────────────────────
# Setup / Config
# ──────────────────────────────────────────────────────────────────────────────

class SetupRequest(BaseModel):
    # Exchange
    delta_api_key: str
    delta_api_secret: str
    delta_testnet: bool = True

    # TradingView
    tradingview_webhook_secret: str

    # Email
    email_address: str
    smtp_host: str
    smtp_port: int = 587
    smtp_user: str
    smtp_password: str
    smtp_use_tls: bool = True

    # Trading params
    starting_capital: float
    risk_per_trade_pct: float = 2.0
    stop_loss_type: str = "fixed"        # "fixed" | "atr"
    stop_loss_fixed_pct: float = 2.0
    max_drawdown_pct: float = 15.0
    trading_pairs: str = "BTC/USDT,ETH/USDT"
    max_open_trades: int = 3
    profit_lock_threshold: float = 100.0
    profit_lock_pct: float = 25.0

    @field_validator("risk_per_trade_pct")
    @classmethod
    def risk_range(cls, v):
        if not 0.5 <= v <= 10:
            raise ValueError("Risk per trade must be between 0.5% and 10%")
        return v

    @field_validator("stop_loss_type")
    @classmethod
    def sl_type(cls, v):
        if v not in ("fixed", "atr"):
            raise ValueError("stop_loss_type must be 'fixed' or 'atr'")
        return v

    @field_validator("starting_capital")
    @classmethod
    def capital_positive(cls, v):
        if v <= 0:
            raise ValueError("starting_capital must be > 0")
        return v


class SetupResponse(BaseModel):
    success: bool
    message: str
    webhook_url: Optional[str] = None


class ConfigResponse(BaseModel):
    key: str
    value: Optional[str]
    is_secret: bool


class BotStatusResponse(BaseModel):
    active: bool
    setup_complete: bool
    delta_testnet: bool
    trading_pairs: List[str]
    starting_capital: float
    risk_per_trade_pct: float
    max_open_trades: int
    uptime_since: Optional[datetime]


# ──────────────────────────────────────────────────────────────────────────────
# Signals
# ──────────────────────────────────────────────────────────────────────────────

class WebhookSignal(BaseModel):
    """Payload sent by TradingView Pine Script webhook."""
    secret: str
    signal: str          # "BUY" | "SELL" | "CLOSE"
    pair: str
    price: float
    atr: Optional[float] = None
    timestamp: Optional[str] = None

    @field_validator("signal")
    @classmethod
    def signal_upper(cls, v):
        v = v.upper()
        if v not in ("BUY", "SELL", "CLOSE"):
            raise ValueError("signal must be BUY, SELL, or CLOSE")
        return v


class SignalResponse(BaseModel):
    id: int
    direction: str
    pair: str
    price: float
    processed: bool
    received_at: datetime

    class Config:
        from_attributes = True


# ──────────────────────────────────────────────────────────────────────────────
# Trades
# ──────────────────────────────────────────────────────────────────────────────

class TradeResponse(BaseModel):
    id: int
    pair: str
    direction: str
    status: str
    quantity: float
    entry_price: Optional[float]
    exit_price: Optional[float]
    stop_loss_price: Optional[float]
    pnl: Optional[float]
    pnl_pct: Optional[float]
    opened_at: datetime
    closed_at: Optional[datetime]

    class Config:
        from_attributes = True


# ──────────────────────────────────────────────────────────────────────────────
# Fund
# ──────────────────────────────────────────────────────────────────────────────

class FundResponse(BaseModel):
    total_balance: float
    available: float
    locked_25pct: float
    in_trades: float
    starting_fund: float
    pnl_today: float
    pnl_total: float
    pnl_total_pct: float
    milestone_hit: bool
    snapshot_at: datetime

    class Config:
        from_attributes = True


# ──────────────────────────────────────────────────────────────────────────────
# Reports
# ──────────────────────────────────────────────────────────────────────────────

class DailyReportResponse(BaseModel):
    report_date: datetime
    starting_fund: float
    ending_fund: float
    locked_fund: float
    trades_count: int
    winning_trades: int
    losing_trades: int
    pnl_day: float
    pnl_total: float
    email_sent: bool

    class Config:
        from_attributes = True


# ──────────────────────────────────────────────────────────────────────────────
# Alerts
# ──────────────────────────────────────────────────────────────────────────────

class AlertResponse(BaseModel):
    id: int
    level: str
    category: str
    message: str
    resolved: bool
    created_at: datetime

    class Config:
        from_attributes = True


# ──────────────────────────────────────────────────────────────────────────────
# Health
# ──────────────────────────────────────────────────────────────────────────────

class HealthResponse(BaseModel):
    status: str
    db: bool
    setup_complete: bool
    bot_active: bool
    version: str = "1.0.0"
