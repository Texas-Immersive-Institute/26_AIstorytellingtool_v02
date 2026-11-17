"""Story projects on disk. Each project is a folder:

<projects folder>/<slug>/
    story.json        the outline (model.Story)
    assets/           pictures, video and audio used by beats and portraits
    playthroughs/     saved playthroughs (written by the runner)
"""

from __future__ import annotations

import io
import json
import re
import shutil
import zipfile
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

from aistory_core.settings_file import write_text_atomic
from pydantic import BaseModel

from story_app.model import Story, new_story

STORY_FILE = "story.json"
ASSETS_DIR = "assets"
PLAYTHROUGHS_DIR = "playthroughs"

PICTURE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg"}
VIDEO_EXT = {".mp4", ".webm", ".mov"}
AUDIO_EXT = {".mp3", ".wav", ".ogg", ".m4a"}
ASSET_EXT = PICTURE_EXT | VIDEO_EXT | AUDIO_EXT
MAX_ZIP_BYTES = 2 * 1024**3
PLAYTHROUGH_ID = re.compile(r"[A-Za-z0-9_-]{1,64}")


class StoreError(Exception):
    """A request the store refuses (bad name, missing project, unsafe path)."""


class NotFound(StoreError):
    pass


class ProjectSummary(BaseModel):
    slug: str
    title: str
    description: str
    scene_count: int
    updated_at: str


class PlaythroughSummary(BaseModel):
    id: str
    started_at: str
    mode: str
    ended: bool
    path: list[str]
    messages: int


class AssetInfo(BaseModel):
    path: str  # "assets/<name>", as stored in story.json
    kind: str  # picture | video | audio
    size: int


def asset_kind(name: str) -> str | None:
    ext = Path(name).suffix.lower()
    if ext in PICTURE_EXT:
        return "picture"
    if ext in VIDEO_EXT:
        return "video"
    if ext in AUDIO_EXT:
        return "audio"
    return None


def slugify(title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return slug[:60] or "story"


class ProjectStore:
    def __init__(self, root: Path):
        self.root = root

    # --- projects ---------------------------------------------------------------

    def list(self) -> list[ProjectSummary]:
        if not self.root.is_dir():
            return []
        out = []
        for folder in sorted(self.root.iterdir()):
            story_file = folder / STORY_FILE
            if not story_file.is_file():
                continue
            try:
                data = json.loads(story_file.read_text(encoding="utf-8-sig"))
            except (OSError, ValueError):
                continue
            out.append(
                ProjectSummary(
                    slug=folder.name,
                    title=str(data.get("title") or folder.name),
                    description=str(data.get("description") or ""),
                    scene_count=len(data.get("scenes") or []),
                    updated_at=_mtime(story_file),
                )
            )
        return out

    def create(self, title: str) -> str:
        story = new_story(title.strip() or "Untitled story")
        slug = self._free_slug(slugify(story.title))
        self.save(slug, story, create=True)
        return slug

    def load(self, slug: str) -> Story:
        path = self.project_dir(slug) / STORY_FILE
        if not path.is_file():
            raise NotFound(f"No story project '{slug}'.")
        return Story.model_validate_json(path.read_text(encoding="utf-8-sig"))

    def save(self, slug: str, story: Story, *, create: bool = False) -> None:
        folder = self.project_dir(slug)
        if not create and not (folder / STORY_FILE).is_file():
            raise NotFound(f"No story project '{slug}'.")
        (folder / ASSETS_DIR).mkdir(parents=True, exist_ok=True)
        write_text_atomic(folder / STORY_FILE, story.model_dump_json(indent=2) + "\n")

    def project_dir(self, slug: str) -> Path:
        if not slug or slug in {".", ".."} or "/" in slug or "\\" in slug or ":" in slug:
            raise StoreError(f"Invalid project name '{slug}'.")
        folder = (self.root / slug).resolve()
        if folder.parent != self.root.resolve():
            raise StoreError(f"Invalid project name '{slug}'.")
        return folder

    def copy_from(self, source: Path, title: str | None = None) -> str:
        """Copy a project folder (an example) into the projects folder."""
        story = Story.model_validate_json((source / STORY_FILE).read_text(encoding="utf-8-sig"))
        slug = self._free_slug(slugify(title or story.title))
        shutil.copytree(source, self.project_dir(slug))
        return slug

    # --- assets -----------------------------------------------------------------

    def asset_file(self, slug: str, rel: str) -> Path:
        """Resolve 'assets/<name>' to a file inside the project, refusing anything outside."""
        pure = PurePosixPath(rel)
        if (
            pure.is_absolute()
            or ".." in pure.parts
            or not pure.parts
            or pure.parts[0] != ASSETS_DIR
        ):
            raise StoreError(f"Invalid asset path '{rel}'.")
        folder = self.project_dir(slug)
        path = (folder / Path(*pure.parts)).resolve()
        if not path.is_relative_to((folder / ASSETS_DIR).resolve()):
            raise StoreError(f"Invalid asset path '{rel}'.")
        return path

    def asset_exists(self, slug: str, rel: str) -> bool:
        try:
            return self.asset_file(slug, rel).is_file()
        except StoreError:
            return False

    def list_assets(self, slug: str) -> list[AssetInfo]:
        folder = self.project_dir(slug) / ASSETS_DIR
        if not folder.is_dir():
            return []
        out = []
        for f in sorted(folder.rglob("*")):
            kind = asset_kind(f.name)
            if f.is_file() and kind:
                rel = f.relative_to(folder.parent).as_posix()
                out.append(AssetInfo(path=rel, kind=kind, size=f.stat().st_size))
        return out

    def add_asset(self, slug: str, filename: str, data: bytes) -> AssetInfo:
        if not (self.project_dir(slug) / STORY_FILE).is_file():
            raise NotFound(f"No story project '{slug}'.")
        name = Path(filename.replace("\\", "/")).name
        stem = re.sub(r"[^A-Za-z0-9._-]+", "-", Path(name).stem).strip("-.") or "asset"
        ext = Path(name).suffix.lower()
        kind = asset_kind(name)
        if kind is None:
            raise StoreError(f"Unsupported file type '{ext or name}'.")
        folder = self.project_dir(slug) / ASSETS_DIR
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / f"{stem}{ext}"
        n = 2
        while target.exists():
            target = folder / f"{stem}-{n}{ext}"
            n += 1
        target.write_bytes(data)
        return AssetInfo(path=f"{ASSETS_DIR}/{target.name}", kind=kind, size=len(data))

    # --- playthroughs ---------------------------------------------------------

    def _playthrough_file(self, slug: str, pid: str) -> Path:
        if not PLAYTHROUGH_ID.fullmatch(pid):
            raise StoreError(f"Invalid playthrough id '{pid}'.")
        return self.project_dir(slug) / PLAYTHROUGHS_DIR / f"{pid}.json"

    def save_playthrough(self, slug: str, pid: str, record: dict) -> None:
        text = json.dumps(record, indent=1) + "\n"
        write_text_atomic(self._playthrough_file(slug, pid), text)

    def has_playthrough(self, slug: str, pid: str) -> bool:
        return self._playthrough_file(slug, pid).is_file()

    def load_playthrough(self, slug: str, pid: str) -> dict:
        path = self._playthrough_file(slug, pid)
        if not path.is_file():
            raise NotFound(f"No playthrough '{pid}'.")
        return json.loads(path.read_text(encoding="utf-8"))

    def list_playthroughs(self, slug: str) -> list[PlaythroughSummary]:
        folder = self.project_dir(slug) / PLAYTHROUGHS_DIR
        files = sorted(folder.glob("*.json"), reverse=True) if folder.is_dir() else []
        out = []
        for f in files:
            if not PLAYTHROUGH_ID.fullmatch(f.stem):
                continue
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            final = data.get("final") or {}
            out.append(
                PlaythroughSummary(
                    id=f.stem,
                    started_at=str(data.get("started_at", "")),
                    mode=str(data.get("mode", "")),
                    ended=bool(data.get("ended")),
                    path=list(final.get("path") or []),
                    messages=sum(1 for e in data.get("events") or [] if e.get("type") == "message"),
                )
            )
        return out

    # --- zip --------------------------------------------------------------------

    def export_zip(self, slug: str) -> bytes:
        folder = self.project_dir(slug)
        if not (folder / STORY_FILE).is_file():
            raise NotFound(f"No story project '{slug}'.")
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for f in sorted(folder.rglob("*")):
                if f.is_file() and not f.name.startswith(".story.json."):
                    zf.write(f, f"{slug}/{f.relative_to(folder).as_posix()}")
        return buf.getvalue()

    def import_zip(self, data: bytes) -> str:
        try:
            zf = zipfile.ZipFile(io.BytesIO(data))
        except zipfile.BadZipFile as exc:
            raise StoreError("That file is not a zip.") from exc
        with zf:
            names = [i for i in zf.infolist() if not i.is_dir()]
            if sum(i.file_size for i in names) > MAX_ZIP_BYTES:
                raise StoreError("The zip is too large.")
            story_entries = [
                i.filename for i in names if PurePosixPath(i.filename).name == STORY_FILE
            ]
            if not story_entries:
                raise StoreError("The zip has no story.json.")
            prefix = str(PurePosixPath(min(story_entries, key=len)).parent)
            prefix = "" if prefix == "." else prefix + "/"
            story = Story.model_validate_json(zf.read(prefix + STORY_FILE))
            slug = self._free_slug(slugify(story.title))
            folder = self.project_dir(slug)
            folder.mkdir(parents=True)
            for info in names:
                if not info.filename.startswith(prefix):
                    continue
                rel = PurePosixPath(info.filename[len(prefix) :])
                if rel.is_absolute() or ".." in rel.parts or ":" in info.filename:
                    continue
                target = (folder / Path(*rel.parts)).resolve()
                if not target.is_relative_to(folder):
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(zf.read(info))
        return slug

    # --- helpers ----------------------------------------------------------------

    def _free_slug(self, base: str) -> str:
        self.root.mkdir(parents=True, exist_ok=True)
        slug, n = base, 2
        while (self.root / slug).exists():
            slug = f"{base}-{n}"
            n += 1
        return slug


def _mtime(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime, UTC).isoformat()
