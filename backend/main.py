"""
AutoCrypto Trader — Backend Entry Point
"""
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from loguru import logger

from db.database import init_db
from api.setup import router as setup_router
from api.health import router as health_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("AutoCrypto Trader starting…")
    await init_db()
    logger.info("DB ready")
    yield
    logger.info("AutoCrypto Trader shutdown")


app = FastAPI(
    title="AutoCrypto Trader",
    description="Automated crypto trading via TradingView + Delta Exchange",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS — allow setup UI served from nginx
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(health_router)
app.include_router(setup_router)

# Placeholder routers — added in later phases
# app.include_router(signal_router)
# app.include_router(trade_router)
# app.include_router(fund_router)
# app.include_router(report_router)
# app.include_router(alert_router)


@app.get("/")
async def root():
    return {
        "app": "AutoCrypto Trader",
        "version": "1.0.0",
        "docs": "/docs",
    }
