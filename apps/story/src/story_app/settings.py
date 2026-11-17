"""Story app settings, kept in %LOCALAPPDATA%/AIStoryTool/story/config.json."""

from __future__ import annotations

from pathlib import Path

from aistory_core.ai import AiSettings
from aistory_core.paths import app_data_dir
from aistory_core.settings_file import load_model, save_model
from pydantic import BaseModel, Field

APP_NAME = "story"
DEFAULT_PORT = 8777


class AppSettings(BaseModel):
    projects_dir: str | None = None  # chosen on first start
    port: int = Field(default=DEFAULT_PORT, ge=1024, le=65535)
    ai: AiSettings = Field(default_factory=AiSettings)


def settings_path() -> Path:
    return app_data_dir(APP_NAME) / "config.json"


def models_dir() -> Path:
    """Downloaded local models, shared by the apps (e.g. the embedding model for matching)."""
    return app_data_dir("models")


def load_settings() -> AppSettings:
    return load_model(settings_path(), AppSettings)


def save_settings(settings: AppSettings) -> None:
    save_model(settings_path(), settings)
