from fastapi import APIRouter

from core.portfolio import portfolio

router = APIRouter()


@router.get("/portfolio/summary")
async def portfolio_summary():
    return portfolio.summary()
