"""Alerts API"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from models.db_models import Alert
from models.schemas import AlertResponse
from db.database import get_db

router = APIRouter(prefix="/api/alerts", tags=["alerts"])


@router.get("/", response_model=list[AlertResponse])
async def list_alerts(limit: int = 50, unresolved_only: bool = False, db: AsyncSession = Depends(get_db)):
    q = select(Alert).order_by(desc(Alert.created_at)).limit(limit)
    if unresolved_only:
        q = q.where(Alert.resolved == False)
    result = await db.execute(q)
    return result.scalars().all()


@router.post("/{alert_id}/resolve")
async def resolve_alert(alert_id: int, db: AsyncSession = Depends(get_db)):
    from datetime import datetime, timezone
    from fastapi import HTTPException
    result = await db.execute(select(Alert).where(Alert.id == alert_id))
    alert  = result.scalar_one_or_none()
    if not alert:
        raise HTTPException(404, "Alert not found")
    alert.resolved    = True
    alert.resolved_at = datetime.now(timezone.utc)
    await db.commit()
    return {"success": True}
