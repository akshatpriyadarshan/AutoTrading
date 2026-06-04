"""Fund API"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from models.db_models import FundSnapshot, DailyReport
from models.schemas import FundResponse, DailyReportResponse
from db.database import get_db

router = APIRouter(prefix="/api/fund", tags=["fund"])


@router.get("/current", response_model=FundResponse)
async def current_fund(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(FundSnapshot).order_by(desc(FundSnapshot.snapshot_at)).limit(1)
    )
    snap = result.scalar_one_or_none()
    if not snap:
        from config.config_manager import get_config
        from datetime import datetime, timezone
        capital = float(await get_config(db, "starting_capital") or "0")
        return FundResponse(
            total_balance=capital, available=capital,
            locked_25pct=0, in_trades=0, starting_fund=capital,
            pnl_today=0, pnl_total=0, pnl_total_pct=0,
            milestone_hit=False, snapshot_at=datetime.now(timezone.utc)
        )
    sf = float(snap.starting_fund or 0)
    tb = float(snap.total_balance)
    lk = float(snap.locked_25pct)
    pnl_pct = ((tb + lk - sf) / sf * 100) if sf > 0 else 0
    return FundResponse(
        total_balance=tb, available=float(snap.available),
        locked_25pct=lk, in_trades=float(snap.in_trades),
        starting_fund=sf, pnl_today=float(snap.pnl_today),
        pnl_total=float(snap.pnl_total), pnl_total_pct=round(pnl_pct, 2),
        milestone_hit=snap.milestone_hit, snapshot_at=snap.snapshot_at
    )


@router.get("/reports", response_model=list[DailyReportResponse])
async def daily_reports(limit: int = 30, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(DailyReport).order_by(desc(DailyReport.report_date)).limit(limit)
    )
    return result.scalars().all()


@router.post("/snapshot")
async def trigger_snapshot():
    """Manually trigger a fund snapshot."""
    from services.fund_manager import take_fund_snapshot
    data = await take_fund_snapshot()
    return {"success": True, "snapshot": data}
