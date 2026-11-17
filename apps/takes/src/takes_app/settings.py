"""Takes settings, kept in %LOCALAPPDATA%/AIStoryTool/takes/config.json."""

from __future__ import annotations

from pathlib import Path

from aistory_core.paths import app_data_dir
from aistory_core.settings_file import load_model, save_model
from pydantic import BaseModel, Field

APP_NAME = "takes"
DEFAULT_PORT = 8778


class AppSettings(BaseModel):
    projects_dir: str | None = None  # chosen on first start (shots and takes, next milestone)
    port: int = Field(default=DEFAULT_PORT, ge=1024, le=65535)
    # Where the H3 ComfyUI listens. None = http://127.0.0.1:8188 on this computer.
    comfyui_url: str | None = None


def settings_path() -> Path:
    return app_data_dir(APP_NAME) / "config.json"


def data_dir() -> Path:
    return app_data_dir(APP_NAME)


def load_settings() -> AppSettings:
    return load_model(settings_path(), AppSettings)


def save_settings(settings: AppSettings) -> None:
    save_model(settings_path(), settings)
