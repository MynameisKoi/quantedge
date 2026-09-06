import numpy as np
import pandas as pd

from strategies.mtf.hierarchical_engine import MultiTimeframeTracker
from strategies.mtf.intraday_scalper import IntradayScalperStrategy


def _make_dummy_ohlc(n: int = 100, trend: float = 0.001) -> pd.DataFrame:
    close = 2000.0 * np.cumprod(1 + np.full(n, trend))
    high = close * 1.002
    low = close * 0.998
    open_ = np.roll(close, 1)
    open_[0] = 2000.0
    return pd.DataFrame({"open": open_, "high": high, "low": low, "close": close})


def test_mtf_htf_trend_detection():
    df_bull = _make_dummy_ohlc(n=220, trend=0.002)
    assert MultiTimeframeTracker.evaluate_htf_trend(df_bull) == "bullish"

    df_bear = _make_dummy_ohlc(n=220, trend=-0.002)
    assert MultiTimeframeTracker.evaluate_htf_trend(df_bear) == "bearish"


def test_mtf_synthesize_state():
    df_h4 = _make_dummy_ohlc(n=100, trend=0.001)
    df_m15 = _make_dummy_ohlc(n=50, trend=0.0005)
    df_m5 = _make_dummy_ohlc(n=30, trend=0.0002)

    state = MultiTimeframeTracker.synthesize_state(
        asset="XAUUSD",
        current_price=2350.0,
        df_h4=df_h4,
        df_m15=df_m15,
        df_m5=df_m5,
    )
    assert state.asset == "XAUUSD"
    assert state.htf_trend in ("bullish", "bearish", "ranging")
    assert state.alignment_score >= 0.0
    assert state.atr_m5 > 0.0


def test_session_killzone():
    ts_london = pd.Timestamp("2024-05-15 08:30:00")  # Wednesday 08:30 UTC -> London
    session, in_kz = MultiTimeframeTracker.evaluate_session_killzone(ts_london)
    assert session == "london"
    assert in_kz is True

    ts_ny = pd.Timestamp("2024-05-15 14:00:00")  # Wednesday 14:00 UTC -> Overlap
    session, in_kz = MultiTimeframeTracker.evaluate_session_killzone(ts_ny)
    assert session == "overlap"
    assert in_kz is True

    ts_asian = pd.Timestamp("2024-05-15 02:00:00")  # Wednesday 02:00 UTC -> Asian offhours
    session, in_kz = MultiTimeframeTracker.evaluate_session_killzone(ts_asian)
    assert session == "asian_offhours"
    assert in_kz is False


def test_intraday_scalper_signals():
    strategy = IntradayScalperStrategy()
    signals = strategy.compute_signals({"regime": "risk-on"})
    assert isinstance(signals, dict)
    for asset, sig in signals.items():
        assert "score" in sig
        assert "side" in sig
        assert "size_multiplier" in sig
        assert "q_value" in sig
        assert "state_key" in sig


def test_load_mt4_csv_format(tmp_path, monkeypatch):
    from backtest.engine import _load_or_generate_ohlc
    from pathlib import Path

    # Simulate an MT4 History Center CSV export
    csv_content = (
        "2024.01.02,00:00,2062.50,2065.10,2061.20,2064.80,154\n"
        "2024.01.02,00:05,2064.80,2066.00,2063.90,2065.20,120\n"
        "2024.01.02,00:10,2065.20,2067.50,2064.50,2066.80,180\n"
        "2024.01.02,00:15,2066.80,2068.10,2065.80,2067.40,140\n"
    )
    test_dir = tmp_path / "data" / "historical"
    test_dir.mkdir(parents=True)
    (test_dir / "XAUUSD_M5.csv").write_text(csv_content, encoding="utf-8")

    monkeypatch.chdir(tmp_path)
    res = _load_or_generate_ohlc("XAUUSD")
    assert "M5" in res
    assert "M15" in res
    assert "H4" in res
    assert len(res["M5"]) == 4

