"""Unit tests for Massive.com feed and news client (Polygon.io rebrand)."""

import pytest
from data.feeds.massive_feed import MassiveFeed
from data.feeds.polygon_feed import PolygonFeed
from data.news.massive_news_client import MassiveNewsClient
from data.news.newsapi_client import NewsAPIClient


def test_massive_feed_alias():
    assert PolygonFeed is MassiveFeed
    feed = MassiveFeed(api_key="mock_test_key")
    assert feed.api_key == "mock_test_key"
    assert feed.is_configured() is True
    assert "massive.com" in feed.PRIMARY_BASE
    assert "polygon.io" in feed.FALLBACK_BASE


def test_massive_feed_offline_stub():
    feed = MassiveFeed(api_key="")
    assert feed.is_configured() is False


@pytest.mark.asyncio
async def test_massive_news_client_offline():
    client = MassiveNewsClient(api_key="")
    assert client.is_configured() is False
    articles = await client.fetch_news(limit=3)
    assert len(articles) == 3
    assert any("Federal Reserve" in a["title"] for a in articles)

    headlines = await client.headlines(limit=2)
    assert len(headlines) == 3


@pytest.mark.asyncio
async def test_newsapi_client_offline():
    client = NewsAPIClient(api_key="")
    assert client.is_configured() is False
    headlines = await client.headlines()
    assert len(headlines) == 3
    assert "Fed holds rates steady amid sticky inflation" in headlines
