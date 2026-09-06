"""Test news and quote retrieval from NewsAPI and Massive (formerly Polygon.io) APIs."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.settings import settings
from data.feeds.massive_feed import MassiveFeed
from data.news.massive_news_client import MassiveNewsClient
from data.news.newsapi_client import NewsAPIClient


async def test_newsapi():
    print("\n" + "=" * 65)
    print("TEST 1: NewsAPI.org Client")
    print("=" * 65)
    client = NewsAPIClient()
    is_cfg = client.is_configured()
    print(f"Key configured: {'YES (Valid key detected)' if is_cfg else 'NO / Placeholder'}")

    headlines = await client.headlines(query="federal reserve OR inflation OR OPEC OR gold", page_size=5)
    print(f"Result ({len(headlines)} headlines):")
    for i, h in enumerate(headlines, 1):
        print(f"  {i}. {h}")
    return len(headlines) > 0


async def test_massive_api():
    print("\n" + "=" * 65)
    print("TEST 2: Massive.com (formerly Polygon.io) Client")
    print("=" * 65)
    client = MassiveNewsClient()
    feed = MassiveFeed()
    is_cfg = client.is_configured()
    print(f"Key configured: {'YES (Valid key detected)' if is_cfg else 'NO / Placeholder'}")
    print(f"Active Base URL: {client.PRIMARY_BASE} (fallback: {client.FALLBACK_BASE})")

    articles = await client.fetch_news(limit=5)
    print(f"Market News ({len(articles)} articles):")
    for i, art in enumerate(articles, 1):
        title = art.get("title")
        pub = (art.get("publisher") or {}).get("name") or "Unknown"
        utc = art.get("published_utc") or ""
        print(f"  {i}. [{pub}] {title} ({utc})")

    # Test quote feed
    quote = await feed.last_quote("EURUSD")
    print(f"\nLive Quote Test (EURUSD): {quote}")

    return len(articles) > 0


async def main():
    print("=" * 65)
    print("QUANTEDGE FINANCIAL NEWS & MARKET DATA API TEST")
    print("=" * 65)
    newsapi_ok = await test_newsapi()
    massive_ok = await test_massive_api()
    print("\n" + "=" * 65)
    print(f"SUMMARY: NewsAPI={'READY' if newsapi_ok else 'OFFLINE'} | Massive={'READY' if massive_ok else 'OFFLINE'}")
    print("=" * 65)


if __name__ == "__main__":
    asyncio.run(main())
