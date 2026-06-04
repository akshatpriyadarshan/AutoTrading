"""
Pydantic schemas — simplified, no EmailStr dependency
"""
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, field_validator


# ── Setup ─────────────────────────────────────────────────────────────────────

class SetupRequest(BaseModel):
    # Exchange
    delta_api_key: str
    delta_api_secret: str
    delta_testnet: bool = True

    # TradingView webhook (optional — only needed if using manual webhooks)
    tradingview_webhook_secret: str = "not-used"

    # Email — plain str, no EmailStr (avoids email-validator dependency)
    email_address: str
    smtp_host: str
    smtp_port: int = 587
    smtp_user: str
    smtp_password: str
    smtp_use_tls: bool = True

    # Trading params — INR
    starting_capital: float           # in INR
    risk_per_trade_pct: float = 2.0
    stop_loss_type: str = "fixed"
    stop_loss_fixed_pct: float = 2.0
    max_drawdown_pct: float = 15.0
    trading_pairs: str = "BTC/USDT,ETH/USDT"
    max_open_trades: int = 3
    profit_lock_threshold: float = 100.0
    profit_lock_pct: float = 25.0
    candle_interval: str = "15m"   # 1m / 5m / 15m / 1h / 4h

    @field_validator("email_address")
    @classmethod
    def email_basic_check(cls, v):
        if "@" not in v or "." not in v.split("@")[-1]:
            raise ValueError("Please enter a valid email address")
        return v.strip()

    @field_validator("risk_per_trade_pct")
    @classmethod
    def risk_range(cls, v):
        if not 0.1 <= v <= 20:
            raise ValueError("Risk per trade must be between 0.1% and 20%")
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


class BotStatusResponse(BaseModel):
    active: bool
    setup_complete: bool
    delta_testnet: bool
    trading_pairs: List[str]
    starting_capital: float
    risk_per_trade_pct: float
    max_open_trades: int
    candle_interval: str = "15m"
    uptime_since: Optional[datetime] = None


# ── Signals ───────────────────────────────────────────────────────────────────

class WebhookSignal(BaseModel):
    secret: str
    signal: str
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
    model_config = {"from_attributes": True}


# ── Trades ────────────────────────────────────────────────────────────────────

class TradeResponse(BaseModel):
    id: int
    pair: str
    direction: str
    status: str
    quantity: float
    entry_price: Optional[float] = None
    exit_price: Optional[float] = None
    stop_loss_price: Optional[float] = None
    pnl: Optional[float] = None
    pnl_pct: Optional[float] = None
    opened_at: datetime
    closed_at: Optional[datetime] = None
    model_config = {"from_attributes": True}


# ── Fund ──────────────────────────────────────────────────────────────────────

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
    model_config = {"from_attributes": True}


# ── Reports ───────────────────────────────────────────────────────────────────

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
    model_config = {"from_attributes": True}


# ── Alerts ────────────────────────────────────────────────────────────────────

class AlertResponse(BaseModel):
    id: int
    level: str
    category: str
    message: str
    resolved: bool
    created_at: datetime
    model_config = {"from_attributes": True}


# ── Health ────────────────────────────────────────────────────────────────────

class HealthResponse(BaseModel):
    status: str
    db: bool
    setup_complete: bool
    bot_active: bool
    version: str = "1.0.0"
