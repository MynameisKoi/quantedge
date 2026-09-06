from fastapi import APIRouter

from api.routes.analytics import router as analytics_router
from api.routes.bridge import router as bridge_router
from api.routes.config import router as config_router
from api.routes.copilot import router as copilot_router
from api.routes.portfolio import router as portfolio_router
from api.routes.regime import router as regime_router
from api.routes.signals import router as signals_router
from api.routes.trades import router as trades_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(analytics_router, tags=["Analytics"])
api_router.include_router(portfolio_router, tags=["Portfolio"])
api_router.include_router(signals_router, tags=["Signals"])
api_router.include_router(trades_router, tags=["Trades"])
api_router.include_router(regime_router, tags=["Regime"])
api_router.include_router(copilot_router, tags=["Copilot"])
api_router.include_router(config_router, tags=["Emergency"])
api_router.include_router(bridge_router, tags=["Bridge"])
