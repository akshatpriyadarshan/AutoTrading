"""
DB engine — supports both SQLite (local dev) and PostgreSQL (Docker/prod).
Detected automatically from DATABASE_URL env var.
"""
import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import text
from loguru import logger

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "sqlite+aiosqlite:///./data/autocrypto.db"   # safe local default
)

# Build engine kwargs — SQLite needs check_same_thread=False
is_sqlite = DATABASE_URL.startswith("sqlite")
engine_kwargs = dict(echo=False)
if not is_sqlite:
    engine_kwargs.update(pool_size=10, max_overflow=20, pool_pre_ping=True)
else:
    engine_kwargs["connect_args"] = {"check_same_thread": False}

engine = create_async_engine(DATABASE_URL, **engine_kwargs)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_db():
    """FastAPI dependency — yields a DB session per request."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db():
    """Create all tables on startup."""
    from models.db_models import Base
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info(f"DB ready ({DATABASE_URL.split('://')[0]})")


async def check_db_connection() -> bool:
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
