"""Precision market-hours macro and news event scheduler.

Eliminates 24/7 API polling waste by triggering news and multi-agent LLM consensus
strictly during high-liquidity, market-moving economic catalyst windows:
- 06:30 UTC: Pre-London Daily Baseline (Sets daily macro regime: risk-on/off, stagflation)
- 12:25 UTC: US Tier-1 Economic Event Window (CPI, NFP, PPI, GDP, Retail Sales)
- 14:25 UTC: US EIA Crude Oil Inventory Window (Wednesdays only — primary USOIL catalyst)
- 17:55 UTC: FOMC Rate Decision / Powell Speech (Select Wednesdays)
- 20:30 UTC: US Market Close & Performance Review

Also provides a Pre-News Blackout Guard to prevent opening fresh positions 5 minutes
before high-impact releases when Exness bid-ask spreads temporarily widen.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class MarketEventWindow:
    name: str
    target_time: time
    window_minutes: int
    days_of_week: list[int]  # 0=Mon, 1=Tue, 2=Wed, 3=Thu, 4=Fri
    high_impact: bool = True
    blackout_before_min: int = 5
    blackout_after_min: int = 5


# Institutional catalyst timetable (UTC)
SCHEDULED_WINDOWS: list[MarketEventWindow] = [
    # 06:30 UTC — Pre-London Daily Baseline
    MarketEventWindow(
        name="pre_london_baseline",
        target_time=time(6, 30),
        window_minutes=25,
        days_of_week=[0, 1, 2, 3, 4],
        high_impact=False,
        blackout_before_min=0,
        blackout_after_min=0,
    ),
    # 12:25 UTC — US Tier-1 Release Window (CPI / NFP / GDP usually 12:30 or 13:30 UTC)
    MarketEventWindow(
        name="us_tier1_macro",
        target_time=time(12, 25),
        window_minutes=20,
        days_of_week=[0, 1, 2, 3, 4],
        high_impact=True,
        blackout_before_min=5,
        blackout_after_min=10,
    ),
    # 14:25 UTC — US EIA Crude Inventories (Wednesdays only)
    MarketEventWindow(
        name="eia_crude_inventories",
        target_time=time(14, 25),
        window_minutes=15,
        days_of_week=[2],  # Wednesday only
        high_impact=True,
        blackout_before_min=5,
        blackout_after_min=10,
    ),
    # 17:55 UTC — FOMC / Fed Rate Decision (Wednesdays)
    MarketEventWindow(
        name="fomc_fed_decision",
        target_time=time(17, 55),
        window_minutes=25,
        days_of_week=[2],  # Wednesday
        high_impact=True,
        blackout_before_min=10,
        blackout_after_min=15,
    ),
    # 20:30 UTC — US Market Close Wrap
    MarketEventWindow(
        name="us_close_wrap",
        target_time=time(20, 30),
        window_minutes=30,
        days_of_week=[0, 1, 2, 3, 4],
        high_impact=False,
        blackout_before_min=0,
        blackout_after_min=0,
    ),
]


class MacroEventScheduler:
    """Manages precision-timed macro news retrieval and pre-news risk guards."""

    def __init__(self, windows: list[MarketEventWindow] | None = None) -> None:
        self.windows = windows or SCHEDULED_WINDOWS
        # Set of (date_str, event_name) to ensure each window executes only once per day
        self._completed_triggers: set[str] = set()

    def should_refresh_macro(self, now: datetime | None = None) -> tuple[bool, str]:
        """
        Check if the bot has entered a scheduled macro window that hasn't fired today.
        Returns: (should_run, event_name)
        """
        now = now or datetime.now(UTC)
        weekday = now.weekday()
        if weekday >= 5:  # Weekend
            return False, "weekend"

        date_str = now.strftime("%Y-%m-%d")
        now_time = now.time()

        for win in self.windows:
            if weekday not in win.days_of_week:
                continue

            event_key = f"{date_str}_{win.name}"
            if event_key in self._completed_triggers:
                continue

            # Check if current time is within [target_time, target_time + window_minutes]
            win_start = datetime.combine(now.date(), win.target_time, tzinfo=UTC)
            win_end = win_start + timedelta(minutes=win.window_minutes)

            if win_start <= now <= win_end:
                self._completed_triggers.add(event_key)
                logger.info(
                    "Macro Event Triggered: %s (Scheduled at %s UTC)",
                    win.name,
                    win.target_time.strftime("%H:%M"),
                )
                return True, win.name

        return False, "none"

    def is_pre_news_blackout(self, now: datetime | None = None) -> tuple[bool, str]:
        """
        Determines whether trading is inside a pre-news spread widening blackout.
        New market orders should be blocked during this window to avoid high slippage.
        """
        now = now or datetime.now(UTC)
        weekday = now.weekday()
        if weekday >= 5:
            return True, "weekend_closed"

        for win in self.windows:
            if not win.high_impact or weekday not in win.days_of_week:
                continue

            event_time = datetime.combine(now.date(), win.target_time, tzinfo=UTC)
            blackout_start = event_time - timedelta(minutes=win.blackout_before_min)
            blackout_end = event_time + timedelta(minutes=win.blackout_after_min)

            if blackout_start <= now <= blackout_end:
                return True, f"pre_news_blackout({win.name})"

        return False, "normal"

    def is_asset_market_open(self, asset: str, now: datetime | None = None) -> tuple[bool, str]:
        """
        Check if an asset's market is currently open for live order placement.
        - BTCUSD: Open 24/7/365.
        - XAUUSD, USOIL, EURUSD: Closed Friday ~21:00 UTC through Sunday ~22:00 UTC.
        """
        canon = asset.upper().rstrip("M")
        if "BTC" in canon:
            return True, "Open 24/7/365"

        now = now or datetime.now(UTC)
        weekday = now.weekday()
        current_time = now.time()

        # Weekend closures:
        # Friday after 21:00 UTC
        if weekday == 4 and current_time >= time(21, 0):
            return False, "Weekend Closed (Reopens Sun 22:00 UTC)"
        # Saturday all day
        if weekday == 5:
            return False, "Weekend Closed (Reopens Sun 22:00 UTC)"
        # Sunday before 21:05 UTC (EUR) or 22:00 UTC (XAU, USOIL)
        if weekday == 6:
            reopen_min = time(21, 5) if "EUR" in canon else time(22, 0)
            if current_time < reopen_min:
                return False, f"Weekend Closed (Reopens Sun {reopen_min.strftime('%H:%M')} UTC)"

        # Mon-Thu daily maintenance rollover break: 20:59 - 22:00 UTC for Gold and Oil
        if weekday in (0, 1, 2, 3) and (canon in ("XAUUSD", "USOIL")):
            if time(20, 59) <= current_time < time(22, 0):
                return False, "Daily Maintenance Break (Reopens 22:00 UTC)"

        return True, "Market Open"

    def is_market_down_hours(self, now: datetime | None = None) -> tuple[bool, str]:
        """
        Check if traditional financial markets are in down hours (weekend or daily rollover).
        During down hours, market quotes do not move and background LLM trend analysis is suspended.
        """
        now = now or datetime.now(UTC)
        weekday = now.weekday()
        current_time = now.time()

        # Weekend closure (Friday 21:00 UTC to Sunday 21:05 UTC)
        if weekday == 4 and current_time >= time(21, 0):
            return True, "Weekend Closure (Traditional markets closed)"
        if weekday == 5:
            return True, "Weekend Closure (Traditional markets closed)"
        if weekday == 6 and current_time < time(21, 5):
            return True, "Weekend Closure (Traditional markets closed)"

        # Daily maintenance rollover break: 20:59 - 22:00 UTC Mon-Thu
        if weekday in (0, 1, 2, 3) and (time(20, 59) <= current_time < time(22, 0)):
            return True, "Daily Rollover Maintenance Break"

        return False, "Market Active"

    def seconds_until_next_event(self, now: datetime | None = None) -> float:
        """Calculate seconds until the next upcoming scheduled window for low-CPU sleep."""
        now = now or datetime.now(UTC)
        today = now.date()
        upcoming = []

        for win in self.windows:
            event_dt = datetime.combine(today, win.target_time, tzinfo=UTC)
            if event_dt > now:
                upcoming.append((event_dt - now).total_seconds())

        if upcoming:
            return min(upcoming)

        # No more events today, compute seconds until tomorrow 06:30 UTC
        tomorrow = today + timedelta(days=1)
        next_event = datetime.combine(tomorrow, time(6, 30), tzinfo=UTC)
        return max(60.0, (next_event - now).total_seconds())


# Global singleton scheduler
macro_scheduler = MacroEventScheduler()
