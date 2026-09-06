"""Shared MetaQuotes Common\\Files path helpers."""

from __future__ import annotations

import os
from pathlib import Path

from config.settings import settings


def default_bridge_dir() -> Path:
    """MT4 FILE_COMMON maps to MetaQuotes/Terminal/Common/Files."""
    if settings.bridge_file_dir:
        return Path(settings.bridge_file_dir)
    appdata = os.environ.get("APPDATA")
    if appdata:
        return Path(appdata) / "MetaQuotes" / "Terminal" / "Common" / "Files" / "quantedge"
    return Path.home() / "AppData" / "Roaming" / "MetaQuotes" / "Terminal" / "Common" / "Files" / "quantedge"
