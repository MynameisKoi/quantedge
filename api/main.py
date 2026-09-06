"""FastAPI entrypoint."""

from __future__ import annotations

import logging

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from api.routes import api_router
from config.settings import settings

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)

app = FastAPI(
    title="QuantEdge AI",
    description="Autonomous multi-asset trading system — Exness + OpenAI macro consensus",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)

# Mount static files and dashboard
dashboard_dir = Path("dashboard")
static_dir = dashboard_dir / "static"
static_dir.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


@app.get("/")
@app.get("/dashboard")
async def get_dashboard():
    index_path = dashboard_dir / "index.html"
    if index_path.exists():
        return FileResponse(str(index_path))
    return {"message": "QuantEdge Dashboard API online. index.html loading..."}


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "env": settings.app_env,
        "live_trading": settings.enable_live_trading,
    }
