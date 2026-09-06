"""Polygon.io compatibility alias -> maps to MassiveFeed."""

from __future__ import annotations

from data.feeds.massive_feed import MassiveFeed

# Polygon.io rebranded to Massive.com in late 2025.
# PolygonFeed is preserved for backwards compatibility.
PolygonFeed = MassiveFeed

__all__ = ["MassiveFeed", "PolygonFeed"]
