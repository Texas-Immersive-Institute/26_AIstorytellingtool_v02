"""HTTP API for Takes. It listens on 127.0.0.1 only: Takes is a desktop app for this computer.

Handlers that touch projects are async so they run on the event loop, the same thread as the
generator: one writer for project.json at a time.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import asdict
from pathlib import Path
from typing import Any

import httpx
from aistory_core.paths import suggested_projects_dir
from aistory_core.web_ui import UIFiles
from fastapi import APIRouter, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from takes_app import __version__
from takes_app.comfyui import DEFAULT_URL, ComfyStatus, ComfyUI, check
from takes_app.generator import Generator, probe_seconds, to_24fps
from takes_app.pack import Pack, PackError
from takes_app.settings import AppSettings, save_settings
from takes_app.stages import ASPECT_RATIOS, DURATIONS, GenerateRequest
from takes_app.store import (
    UNFINISHED,
    MediaInfo,
    NotFound,
    Project,
    ProjectStore,
    ProjectSummary,
    Shot,
    StoreError,
    Take,
)

MAX_UPLOAD_BYTES = 500 * 1024 * 1024
APP_DIR = Path(__file__).resolve().parents[2]  # apps/takes


class SetupRequired(Exception):
    pass


class SettingsOut(BaseModel):
    projects_dir: str | None
    suggested_projects_dir: str
    comfyui_url: str | None
    default_comfyui_url: str


class SettingsIn(BaseModel):
    """Only the fields sent are changed. An empty comfyui_url means the default address."""

    projects_dir: str | None = None
    comfyui_url: str | None = None


class CreateProject(BaseModel):
    title: str


class ProjectOut(BaseModel):
    slug: str
    project: Project


class ProjectPatch(BaseModel):
    title: str


class ShotIn(BaseModel):
    title: str = ""
    notes: str = ""
    after: str | None = None  # place it after this shot; None = at the end


class ShotPatch(BaseModel):
    title: str | None = None
    notes: str | None = None


class ShotOrder(BaseModel):
    shots: list[str]  # every shot id, in the new sequence order


def create_app(
    settings: AppSettings,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
    poll_s: float = 5.0,
    probe=probe_seconds,
    retime=to_24fps,
) -> FastAPI:
    """`transport`, `probe` and `retime` let tests stand in for ComfyUI, ffprobe and ffmpeg."""
    stores: dict[str, ProjectStore] = {}

    def store() -> ProjectStore:
        if not settings.projects_dir:
            raise SetupRequired()
        return stores.setdefault(settings.projects_dir, ProjectStore(Path(settings.projects_dir)))

    async def connect() -> ComfyStatus:
        return await check(settings.comfyui_url, transport=transport)

    pack = Pack()
    generator = Generator(
        store=store,
        pack=pack,
        connect=connect,
        # A stand-in ComfyUI (tests) has no websocket to watch.
        make_comfy=lambda url: ComfyUI(url, transport=transport, watch_progress=transport is None),
        probe=probe,
        retime=retime,
        poll_s=poll_s,
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        if settings.projects_dir:
            generator.resume()
        generator.start()
        yield
        await generator.stop()

    app = FastAPI(title="Takes", version=__version__, lifespan=lifespan)
    app.state.generator = generator
    api = APIRouter(prefix="/api")

    # -- app, settings, ComfyUI ----------------------------------------------------------------

    @api.get("/health")
    def health() -> dict[str, str]:
        return {"service": "takes", "version": __version__}

    def settings_out() -> SettingsOut:
        return SettingsOut(
            projects_dir=settings.projects_dir,
            suggested_projects_dir=str(suggested_projects_dir("Takes")),
            comfyui_url=settings.comfyui_url,
            default_comfyui_url=DEFAULT_URL,
        )

    @api.get("/settings", response_model=SettingsOut)
    async def get_settings() -> SettingsOut:
        return settings_out()

    @api.put("/settings", response_model=SettingsOut)
    async def put_settings(body: SettingsIn) -> SettingsOut:
        sent = body.model_fields_set
        if "projects_dir" in sent:
            raw = (body.projects_dir or "").strip().strip('"')
            folder = Path(raw).expanduser()
            if not raw or not folder.is_absolute():
                raise HTTPException(
                    400, "Use a full folder path, e.g. C:\\Users\\you\\Documents\\Takes"
                )
            try:
                folder.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                raise HTTPException(400, f"Can't use that folder: {exc}") from exc
            first = settings.projects_dir is None
            settings.projects_dir = str(folder)
            if first:
                generator.resume()
        if "comfyui_url" in sent:
            url = (body.comfyui_url or "").strip().rstrip("/")
            if url and not url.startswith(("http://", "https://")):
                raise HTTPException(400, "ComfyUI's address starts with http:// or https://")
            settings.comfyui_url = url or None
        save_settings(settings)
        return settings_out()

    @api.get("/comfyui")
    async def comfyui() -> dict[str, Any]:
        """Is the H3 ComfyUI running and ready to render?"""
        return asdict(await connect())

    @api.get("/options")
    def options() -> dict[str, Any]:
        return {
            "frames": ["first", "last", "firstlast", "none"],
            "audio": ["native", "clip", "voice"],
            "aspect_ratios": list(ASPECT_RATIOS),
            "durations": list(DURATIONS),
        }

    # -- projects ------------------------------------------------------------------------------

    @api.get("/projects", response_model=list[ProjectSummary])
    async def list_projects() -> list[ProjectSummary]:
        return store().list()

    @api.post("/projects", response_model=ProjectOut, status_code=201)
    async def create_project(body: CreateProject) -> ProjectOut:
        slug = store().create(body.title)
        return ProjectOut(slug=slug, project=store().load(slug))

    @api.get("/projects/{slug}", response_model=ProjectOut)
    async def get_project(slug: str) -> ProjectOut:
        return ProjectOut(slug=slug, project=store().load(slug))

    @api.patch("/projects/{slug}", response_model=ProjectOut)
    async def rename_project(slug: str, body: ProjectPatch) -> ProjectOut:
        project = store().load(slug)
        project.title = body.title.strip() or project.title
        store().save(slug)
        return ProjectOut(slug=slug, project=project)

    @api.post("/projects/{slug}/media", response_model=MediaInfo, status_code=201)
    async def upload_media(slug: str, file: UploadFile = File(...)) -> MediaInfo:
        store().load(slug)
        data = await file.read(MAX_UPLOAD_BYTES + 1)
        if len(data) > MAX_UPLOAD_BYTES:
            raise HTTPException(413, "That file is larger than 500 MB")
        if not data:
            raise HTTPException(400, "That file is empty")
        return store().add_media(slug, file.filename or "file", data)

    @api.get("/projects/{slug}/media/{media_id}")
    async def media_file(slug: str, media_id: str) -> FileResponse:
        return FileResponse(store().media_path(slug, media_id))

    # -- shots (the sequence) ------------------------------------------------------------------

    @api.post("/projects/{slug}/shots", response_model=Shot, status_code=201)
    async def add_shot(slug: str, body: ShotIn) -> Shot:
        project = store().load(slug)
        shot = Shot(title=body.title.strip() or f"Shot {len(project.shots) + 1}", notes=body.notes)
        at = len(project.shots)
        if body.after:
            at = project.shots.index(project.shot(body.after)) + 1
        project.shots.insert(at, shot)
        store().save(slug)
        return shot

    @api.patch("/projects/{slug}/shots/{shot_id}", response_model=Shot)
    async def edit_shot(slug: str, shot_id: str, body: ShotPatch) -> Shot:
        shot = store().load(slug).shot(shot_id)
        if body.title is not None:
            shot.title = body.title.strip() or shot.title
        if body.notes is not None:
            shot.notes = body.notes
        store().save(slug)
        return shot

    @api.put("/projects/{slug}/shot-order", response_model=ProjectOut)
    async def reorder_shots(slug: str, body: ShotOrder) -> ProjectOut:
        """Drag-to-reorder: the full list of shot ids in their new order."""
        project = store().load(slug)
        if sorted(body.shots) != sorted(s.id for s in project.shots):
            raise HTTPException(400, "Send every shot id exactly once")
        by_id = {s.id: s for s in project.shots}
        project.shots = [by_id[i] for i in body.shots]
        store().save(slug)
        return ProjectOut(slug=slug, project=project)

    @api.delete("/projects/{slug}/shots/{shot_id}", status_code=204)
    async def delete_shot(slug: str, shot_id: str) -> None:
        project = store().load(slug)
        shot = project.shot(shot_id)
        if any(t.status in UNFINISHED for t in shot.takes):
            raise HTTPException(409, "Cancel this shot's waiting or rendering takes first")
        for take in shot.takes:
            continuation = project.continued_by(take.id)
            if continuation:
                raise HTTPException(
                    409, f"“{continuation.title}” continues this shot; delete that shot first"
                )
        for take in shot.takes:
            store().delete_take_files(slug, take.id)
        project.shots.remove(shot)
        store().save(slug)

    # -- takes ---------------------------------------------------------------------------------

    def check_inputs(slug: str, request: GenerateRequest) -> None:
        for media_id in request.media_ids():
            store().media_path(slug, media_id)
        if request.continues:
            _, source = store().load(slug).find_take(request.continues)
            if source.status != "done":
                raise HTTPException(409, "Only a finished take can be extended")
        pack.stage(request.stage)

    @api.post("/projects/{slug}/shots/{shot_id}/takes", response_model=Take, status_code=202)
    async def generate(slug: str, shot_id: str, body: GenerateRequest) -> Take:
        shot = store().load(slug).shot(shot_id)
        if body.continues != shot.continues_take:
            raise HTTPException(
                400,
                f"This shot continues take {shot.continues_take}; send it as 'continues'"
                if shot.continues_take
                else "Only a continuation shot extends a take; use Extend on the take first",
            )
        check_inputs(slug, body)
        take = Take(request=body, stage=body.stage, upscaled=body.upscale)
        shot.takes.append(take)
        store().save(slug)
        generator.enqueue(slug, take.id)
        return take

    @api.post("/projects/{slug}/takes/{take_id}/upscale", response_model=Take, status_code=202)
    async def upscale_take(slug: str, take_id: str) -> Take:
        """Re-render this take on its seed and upscale it; the result becomes the selected take."""
        shot, source = store().load(slug).find_take(take_id)
        if source.status != "done" or source.upscaled:
            raise HTTPException(409, "Only a finished take that isn't upscaled yet can be upscaled")
        if source.request.continues and source.request.audio != "native":
            raise HTTPException(
                409,
                "An extension with your clip or a voice reference can't be upscaled: the pack's "
                "extend + upscale stage has native audio only",
            )
        changes: dict[str, Any] = {"upscale": True, "seed": source.seed}
        if source.request.audio == "voice":
            # Reuse the line already spoken, so the upscale has the same soundtrack.
            changes |= {"audio": "clip", "audio_clip": source.voice_audio, "voice": None}
        request = GenerateRequest.model_validate(source.request.model_dump() | changes)
        check_inputs(slug, request)
        take = Take(
            request=request,
            stage=request.stage,
            seed=source.seed,
            upscaled=True,
            source_take=source.id,
        )
        shot.takes.append(take)
        store().save(slug)
        generator.enqueue(slug, take.id)
        return take

    @api.post("/projects/{slug}/takes/{take_id}/extend", response_model=Shot, status_code=201)
    async def extend_take(slug: str, take_id: str) -> Shot:
        """A continuation shot right after this take's shot, carrying on from this take."""
        project = store().load(slug)
        shot, take = project.find_take(take_id)
        if take.status != "done" or not take.video:
            raise HTTPException(409, "Only a finished take can be extended")
        existing = project.continued_by(take.id)
        if existing:
            return existing
        new = Shot(title=f"{shot.title} (continued)", continues_take=take.id)
        project.shots.insert(project.shots.index(shot) + 1, new)
        store().save(slug)
        return new

    @api.post("/projects/{slug}/takes/{take_id}/select", response_model=Shot)
    async def select_take(slug: str, take_id: str) -> Shot:
        shot, take = store().load(slug).find_take(take_id)
        if take.status != "done":
            raise HTTPException(409, "Only a finished take can play in the sequence")
        shot.selected_take = take.id
        store().save(slug)
        return shot

    @api.post("/projects/{slug}/takes/{take_id}/cancel", response_model=Take)
    async def cancel_take(slug: str, take_id: str) -> Take:
        return generator.cancel(slug, take_id)

    @api.delete("/projects/{slug}/takes/{take_id}", status_code=204)
    async def delete_take(slug: str, take_id: str) -> None:
        shot, take = store().load(slug).find_take(take_id)
        if take.status in UNFINISHED:
            raise HTTPException(409, "Cancel this take before deleting it")
        continuation = store().load(slug).continued_by(take.id)
        if continuation:
            raise HTTPException(
                409, f"“{continuation.title}” continues this take; delete that shot first"
            )
        shot.takes.remove(take)
        store().delete_take_files(slug, take.id)
        if shot.selected_take == take.id:
            shot.reselect()
        store().save(slug)

    @api.get("/projects/{slug}/takes/{take_id}/video")
    async def take_video(slug: str, take_id: str) -> FileResponse:
        _, take = store().load(slug).find_take(take_id)
        if not take.video:
            raise HTTPException(404, "This take has no video yet")
        return FileResponse(store().take_dir(slug, take.id) / take.video)

    @api.get("/projects/{slug}/takes/{take_id}/files/{name}")
    async def take_file(slug: str, take_id: str, name: str) -> FileResponse:
        _, take = store().load(slug).find_take(take_id)
        if name not in {f.name for f in take.files}:
            raise HTTPException(404, "No such file")
        return FileResponse(store().take_dir(slug, take.id) / name)

    app.include_router(api)

    @app.exception_handler(SetupRequired)
    async def _setup(_r: Request, _e: SetupRequired) -> JSONResponse:
        return JSONResponse(
            {"detail": "Choose a projects folder first.", "code": "setup_required"}, 409
        )

    @app.exception_handler(NotFound)
    async def _not_found(_r: Request, exc: NotFound) -> JSONResponse:
        return JSONResponse({"detail": str(exc), "code": "not_found"}, 404)

    @app.exception_handler(StoreError)
    async def _store(_r: Request, exc: StoreError) -> JSONResponse:
        return JSONResponse({"detail": str(exc)}, 400)

    @app.exception_handler(PackError)
    async def _pack(_r: Request, exc: PackError) -> JSONResponse:
        return JSONResponse({"detail": str(exc)}, 400)

    # The UI (apps/takes/web, built with `npm run build`), when it has been built.
    dist = Path(os.environ.get("TAKES_WEB_DIST", APP_DIR / "web" / "dist"))
    if (dist / "index.html").is_file():
        app.mount("/", UIFiles(dist), name="web")
    return app
