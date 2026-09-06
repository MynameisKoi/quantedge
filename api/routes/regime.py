from fastapi import APIRouter

from data.news.newsapi_client import NewsAPIClient
from macro.regime_classifier import regime_classifier

router = APIRouter()


@router.get("/regime/current")
async def current_regime():
    return regime_classifier.current.as_dict()


@router.post("/regime/refresh")
async def refresh_regime():
    headlines = await NewsAPIClient().headlines()
    regime_classifier.update_context(headlines=headlines)
    result = await regime_classifier.refresh()
    return result.as_dict()
