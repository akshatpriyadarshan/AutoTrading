"""
Health check endpoint
"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from db.database import get_db, check_db_connection
from config.config_manager import get_config
from models.schemas import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health(db: AsyncSession = Depends(get_db)):
    db_ok          = await check_db_connection()
    setup_complete = await get_config(db, "setup_complete") == "true"
    bot_active     = await get_config(db, "bot_active") == "true"
    return HealthResponse(
        status="ok" if db_ok else "degraded",
        db=db_ok,
        setup_complete=setup_complete,
        bot_active=bot_active,
    )
