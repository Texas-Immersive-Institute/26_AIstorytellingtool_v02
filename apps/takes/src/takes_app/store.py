"""Takes projects: one folder each in the projects folder chosen on first start.

<project>/project.json     title, shots in sequence order, each shot's takes and selected take
<project>/media/           reference pictures, audio clips and voice recordings
<project>/takes/<take id>/ the files a take's render saved (copied out of ComfyUI)

The server mutates projects only on its event loop, so there is one writer at a time.
"""

from __future__ import annotations

import json
import re
import shutil
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from aistory_core.settings_file import write_text_atomic
from pydantic import BaseModel, Field

from takes_app.stages import GenerateRequest

PROJECT_FILE = "project.json"
FORMAT_VERSION = 1
UNFINISHED = ("queued", "preparing", "voicing", "rendering", "downloading")

TakeStatus = Literal[
    "queued", "preparing", "voicing", "rendering", "downloading", "done", "failed", "cancelled"
]


class StoreError(Exception):
    pass


class NotFound(StoreError):
    pass


def now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


class TakeFile(BaseModel):
    name: str
    size: int
    main: bool = False  # the take itself (the final video), not a preview or side file


class Take(BaseModel):
    """One generated video for a shot, from the moment it is asked for."""

    id: str = Field(default_factory=lambda: new_id("take"))
    request: GenerateRequest
    stage: str
    status: TakeStatus = "queued"
    seed: int | None = None  # the seed it rendered with; upscaling re-renders on it
    upscaled: bool = False
    source_take: str | None = None  # for an upscaled take: the take it re-renders
    voice_audio: str | None = None  # media id of the line spoken from the voice reference
    duration_s: float | None = None  # the length it was rendered at
    prompt_id: str | None = None  # ComfyUI's id for the video run
    error: str | None = None
    files: list[TakeFile] = Field(default_factory=list)
    created_at: str = Field(default_factory=now)
    finished_at: str | None = None
    cancel_requested: bool = False

    @property
    def video(self) -> str | None:
        return next((f.name for f in self.files if f.main), None)


class Shot(BaseModel):
    id: str = Field(default_factory=lambda: new_id("shot"))
    title: str = ""
    notes: str = ""
    takes: list[Take] = Field(default_factory=list)
    selected_take: str | None = None

    def take(self, take_id: str) -> Take:
        found = next((t for t in self.takes if t.id == take_id), None)
        if found is None:
            raise NotFound(f"No take {take_id!r} in this shot")
        return found

    def take_done(self, take: Take) -> None:
        """A finished take is selected if the shot has none yet; an upscaled take always is."""
        if take.upscaled or self.selected_take is None:
            self.selected_take = take.id

    def reselect(self) -> None:
        """After removing the selected take: the newest finished take, or none."""
        done = [t for t in self.takes if t.status == "done"]
        self.selected_take = done[-1].id if done else None


class Project(BaseModel):
    format_version: int = FORMAT_VERSION
    title: str
    shots: list[Shot] = Field(default_factory=list)  # in sequence order
    created_at: str = Field(default_factory=now)

    def shot(self, shot_id: str) -> Shot:
        found = next((s for s in self.shots if s.id == shot_id), None)
        if found is None:
            raise NotFound(f"No shot {shot_id!r} in this project")
        return found

    def find_take(self, take_id: str) -> tuple[Shot, Take]:
        for shot in self.shots:
            for take in shot.takes:
                if take.id == take_id:
                    return shot, take
        raise NotFound(f"No take {take_id!r} in this project")


class ProjectSummary(BaseModel):
    slug: str
    title: str
    shot_count: int
    updated_at: str


class MediaInfo(BaseModel):
    id: str
    kind: Literal["picture", "video", "audio"]
    size: int


MEDIA_KINDS = {
    "picture": {".png", ".jpg", ".jpeg", ".webp", ".bmp"},
    "video": {".mp4", ".webm", ".mov", ".mkv"},
    "audio": {".mp3", ".wav", ".flac", ".ogg", ".m4a"},
}


def media_kind(name: str) -> str | None:
    suffix = Path(name).suffix.lower()
    return next((kind for kind, exts in MEDIA_KINDS.items() if suffix in exts), None)


def slugify(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:60] or "takes"


class ProjectStore:
    def __init__(self, root: Path):
        self.root = root
        self._open: dict[str, Project] = {}

    # -- projects ------------------------------------------------------------------------------

    def list(self) -> list[ProjectSummary]:
        out = []
        for folder in sorted(self.root.iterdir()) if self.root.is_dir() else []:
            path = folder / PROJECT_FILE
            if not path.is_file():
                continue
            try:
                data = json.loads(path.read_text(encoding="utf-8-sig"))
            except (OSError, ValueError):
                continue
            updated = datetime.fromtimestamp(path.stat().st_mtime, UTC).isoformat(
                timespec="seconds"
            )
            out.append(
                ProjectSummary(
                    slug=folder.name,
                    title=str(data.get("title") or folder.name),
                    shot_count=len(data.get("shots") or []),
                    updated_at=updated,
                )
            )
        return out

    def create(self, title: str) -> str:
        project = Project(title=title.strip() or "Untitled")
        slug, n = slugify(project.title), 2
        self.root.mkdir(parents=True, exist_ok=True)
        base = slug
        while (self.root / slug).exists():
            slug, n = f"{base}-{n}", n + 1
        self._open[slug] = project
        self.save(slug)
        return slug

    def load(self, slug: str) -> Project:
        if slug not in self._open:
            path = self.project_dir(slug) / PROJECT_FILE
            if not path.is_file():
                raise NotFound(f"No Takes project {slug!r}")
            self._open[slug] = Project.model_validate_json(path.read_text(encoding="utf-8-sig"))
        return self._open[slug]

    def save(self, slug: str) -> None:
        folder = self.project_dir(slug)
        (folder / "media").mkdir(parents=True, exist_ok=True)
        write_text_atomic(folder / PROJECT_FILE, self._open[slug].model_dump_json(indent=2) + "\n")

    def project_dir(self, slug: str) -> Path:
        if not slug or slug in {".", ".."} or any(c in slug for c in "/\\:"):
            raise StoreError(f"Invalid project name {slug!r}")
        folder = (self.root / slug).resolve()
        if folder.parent != self.root.resolve():
            raise StoreError(f"Invalid project name {slug!r}")
        return folder

    def unfinished(self) -> list[tuple[str, str]]:
        """(slug, take id) of takes that were waiting or rendering when Takes last stopped."""
        found = []
        for summary in self.list():
            for shot in self.load(summary.slug).shots:
                found += [(summary.slug, t.id) for t in shot.takes if t.status in UNFINISHED]
        return found

    # -- media ---------------------------------------------------------------------------------

    def add_media(self, slug: str, filename: str, data: bytes) -> MediaInfo:
        kind = media_kind(filename)
        if kind is None:
            raise StoreError("Takes uses pictures (png, jpg, webp, bmp), videos or audio files")
        safe = (
            re.sub(r"[^A-Za-z0-9._-]+", "_", Path(filename).name).strip("._")
            or f"file{Path(filename).suffix}"
        )
        media_id = f"{uuid.uuid4().hex[:8]}-{safe}"
        folder = self.project_dir(slug) / "media"
        folder.mkdir(parents=True, exist_ok=True)
        (folder / media_id).write_bytes(data)
        return MediaInfo(id=media_id, kind=kind, size=len(data))  # type: ignore[arg-type]

    def media_path(self, slug: str, media_id: str) -> Path:
        folder = (self.project_dir(slug) / "media").resolve()
        path = (folder / media_id).resolve()
        if path.parent != folder or not path.is_file():
            raise NotFound(f"Unknown media {media_id!r}; upload it to this project first")
        return path

    # -- takes ---------------------------------------------------------------------------------

    def take_dir(self, slug: str, take_id: str) -> Path:
        return self.project_dir(slug) / "takes" / take_id

    def delete_take_files(self, slug: str, take_id: str) -> None:
        shutil.rmtree(self.take_dir(slug, take_id), ignore_errors=True)
