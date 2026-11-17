"""Per-app data folders (settings live here; projects live wherever the user chooses)."""

from __future__ import annotations

import os
from pathlib import Path

SUITE_DIR_NAME = "AIStoryTool"
DATA_DIR_ENV = "AISTORY_DATA_DIR"


def local_app_data_root() -> Path:
    """%LOCALAPPDATA% on Windows, XDG data home elsewhere."""
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA")
        return Path(base) if base else Path.home() / "AppData" / "Local"
    xdg = os.environ.get("XDG_DATA_HOME")
    return Path(xdg) if xdg else Path.home() / ".local" / "share"


def app_data_dir(app: str) -> Path:
    """Data folder for one app, e.g. %LOCALAPPDATA%/AIStoryTool/story.

    AISTORY_DATA_DIR overrides the suite root (used by tests and portable setups).
    """
    override = os.environ.get(DATA_DIR_ENV, "").strip()
    root = Path(override) if override else local_app_data_root() / SUITE_DIR_NAME
    path = root / app
    path.mkdir(parents=True, exist_ok=True)
    return path


def suggested_projects_dir(app_label: str) -> Path:
    """Default offered on first start; the user may pick any folder."""
    docs = Path.home() / "Documents"
    base = docs if docs.is_dir() else Path.home()
    return base / f"AI {app_label} Projects"
