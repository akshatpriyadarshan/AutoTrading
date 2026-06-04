"""Trades API"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from models.db_models import Trade, TradeStatus
from models.schemas import TradeResponse
from db.database import get_db

router = APIRouter(prefix="/api/trades", tags=["trades"])


@router.get("/", response_model=list[TradeResponse])
async def list_trades(limit: int = 50, status: str = None, db: AsyncSession = Depends(get_db)):
    q = select(Trade).order_by(desc(Trade.opened_at)).limit(limit)
    if status:
        try:
            q = q.where(Trade.status == TradeStatus(status))
        except ValueError:
            raise HTTPException(400, f"Invalid status: {status}")
    result = await db.execute(q)
    return result.scalars().all()


@router.get("/open", response_model=list[TradeResponse])
async def open_trades(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Trade).where(Trade.status == TradeStatus.OPEN))
    return result.scalars().all()


@router.get("/{trade_id}", response_model=TradeResponse)
async def get_trade(trade_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Trade).where(Trade.id == trade_id))
    t = result.scalar_one_or_none()
    if not t:
        raise HTTPException(404, "Trade not found")
    return t
