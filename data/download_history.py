"""CLI utility to download multi-month / multi-year historical data for QuantEdge assets."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger("quantedge.data_downloader")

YAHOO_SYMBOL_MAP = {
    "XAUUSD": "GC=F",
    "EURUSD": "EURUSD=X",
    "USOIL": "CL=F",
    "BTCUSD": "BTC-USD",
}


def download_history(
    asset: str = "XAUUSD",
    interval: str = "5m",
    period: str = "60d",
    output_dir: str = "data/historical",
) -> Path | None:
    """
    Download historical candles from Yahoo Finance and format for QuantEdge backtester.
    Note: Yahoo supports 1m up to 7d, 5m/15m/30m up to 60d, 1h up to 730d, 1d up to max.
    """
    try:
        import yfinance as yf
    except ImportError:
        logger.error("Please install yfinance: pip install yfinance")
        return None

    ticker = YAHOO_SYMBOL_MAP.get(asset.upper(), asset)
    logger.info("Fetching historical data for %s (%s) interval=%s period=%s...", asset, ticker, interval, period)

    data = yf.download(
        tickers=ticker,
        interval=interval,
        period=period,
        progress=False,
        auto_adjust=False,
    )

    if data.empty:
        logger.warning("No data returned for %s", asset)
        return None

    # Flatten multi-level columns if present in newer yfinance versions
    if isinstance(data.columns, pd.MultiIndex):
        data.columns = [col[0].lower() for col in data.columns]
    else:
        data.columns = [str(col).lower() for col in data.columns]

    # Standardize columns
    df = data[["open", "high", "low", "close"]].copy()
    if "volume" in data.columns:
        df["volume"] = data["volume"]
    else:
        df["volume"] = 100

    df.dropna(inplace=True)

    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    filename = out_path / f"{asset.upper()}_{interval.upper()}.csv"

    # Save to CSV with standard datetime index
    df.to_csv(filename)
    logger.info("Successfully saved %d bars to %s", len(df), filename)
    return filename


def main() -> None:
    parser = argparse.ArgumentParser(description="QuantEdge Historical Data Downloader")
    parser.add_argument("--asset", default="XAUUSD", choices=["XAUUSD", "EURUSD", "USOIL", "BTCUSD"])
    parser.add_argument("--interval", default="5m", choices=["1m", "5m", "15m", "30m", "1h", "1d"])
    parser.add_argument("--period", default="60d", help="Period (e.g. 7d, 60d, 1y, 2y, max)")
    args = parser.parse_args()

    download_history(asset=args.asset, interval=args.interval, period=args.period)


if __name__ == "__main__":
    main()
