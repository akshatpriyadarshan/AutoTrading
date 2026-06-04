"""
AutoCrypto Trader — Main Application
All phases wired: signals, risk, fund, trades, reports, alerts.
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from db.database import init_db
from api.setup        import router as setup_router
from api.health       import router as health_router
from api.signals      import router as signal_router
from api.test_signals import router as test_router
from api.trades       import router as trades_router
from api.fund         import router as fund_router
from api.alerts       import router as alerts_router
from api.engine       import router as engine_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("AutoCrypto Trader starting…")
    await init_db()
    logger.info("DB ready")

    # Start background schedulers (risk manager, alerts, fund snapshots, daily report)
    from services.scheduler import start_all, stop_all
    await start_all()

    yield

    await stop_all()
    logger.info("AutoCrypto Trader stopped")


app = FastAPI(
    title       = "AutoCrypto Trader",
    description = "Automated crypto trading — TradingView + Delta Exchange",
    version     = "3.0.0",
    lifespan    = lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins     = ["*"],
    allow_credentials = True,
    allow_methods     = ["*"],
    allow_headers     = ["*"],
)

app.include_router(health_router)
app.include_router(setup_router)
app.include_router(signal_router)
app.include_router(test_router)
app.include_router(trades_router)
app.include_router(fund_router)
app.include_router(alerts_router)
app.include_router(engine_router)


@app.get("/")
async def root():
    return {"app": "AutoCrypto Trader", "version": "3.0.0", "docs": "/docs"}
