"""HTTP API for the Story app (host-only except chat; see access.py)."""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Literal

from aistory_core.ai import AiError, AiSettings, Backend, ask_json, check_all, choose_backend
from aistory_core.embeddings import DEFAULT_MODEL_MB, EmbeddingModel
from aistory_core.paths import suggested_projects_dir
from fastapi import APIRouter, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from story_app import __version__
from story_app.access import AccessMiddleware
from story_app.checks import Issue, check_story
from story_app.live_api import live_router
from story_app.matching import EmbeddingMatcher, LexicalMatcher, Matcher
from story_app.model import Story
from story_app.runner import RunError, RunManager
from story_app.settings import AppSettings, load_settings, models_dir, save_settings
from story_app.store import (
    STORY_FILE,
    AssetInfo,
    NotFound,
    PlaythroughSummary,
    ProjectStore,
    ProjectSummary,
    StoreError,
)

APP_DIR = Path(__file__).resolve().parents[2]  # apps/story
REPO_ROOT = APP_DIR.parents[1]


def examples_dir() -> Path:
    override = os.environ.get("STORY_EXAMPLES_DIR")
    return Path(override) if override else REPO_ROOT / "examples"


class SetupRequired(Exception):
    pass


class SettingsOut(BaseModel):
    projects_dir: str | None
    suggested_projects_dir: str
    port: int


class SettingsIn(BaseModel):
    projects_dir: str


class CreateProject(BaseModel):
    title: str


class Created(BaseModel):
    slug: str


class ProjectOut(BaseModel):
    slug: str
    story: Story
    issues: list[Issue]


class Saved(BaseModel):
    issues: list[Issue]


class ExampleOut(BaseModel):
    name: str
    title: str
    description: str


class WhoAmI(BaseModel):
    is_host: bool


class StartRun(BaseModel):
    mode: Literal["live", "outline_only"] = "live"


def create_app(
    settings: AppSettings | None = None,
    *,
    lan: bool = False,
    port: int | None = None,
    embeddings: EmbeddingModel | None | Literal["default"] = "default",
    choose_ai: Callable[[], Awaitable[tuple[Backend | None, str]]] | None = None,
) -> FastAPI:
    """`lan`: the server listens on the LAN (storytool --lan), so phones can join the chat.
    `embeddings` and `choose_ai` exist so tests can run without local models or CLIs."""
    settings = settings or load_settings()
    if embeddings == "default":
        embeddings = EmbeddingModel(models_dir())

    async def default_choose_ai() -> tuple[Backend | None, str]:
        return await choose_backend(app.state.settings.ai)

    choose_ai = choose_ai or default_choose_ai

    def make_matcher() -> Matcher:
        if embeddings is not None and embeddings.status().ready:
            return EmbeddingMatcher(embeddings)
        return LexicalMatcher()

    runs = RunManager(
        choose_backend=lambda: choose_ai(),
        make_matcher=make_matcher,
        ai_timeout=lambda: app.state.settings.ai.timeout_s,
    )

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        yield
        await runs.stop()

    app = FastAPI(title="Story", version=__version__, lifespan=lifespan)
    app.state.settings = settings
    app.state.runs = runs
    app.state.port = port or settings.port
    app.add_middleware(AccessMiddleware)

    def store() -> ProjectStore:
        projects_dir = app.state.settings.projects_dir
        if not projects_dir:
            raise SetupRequired()
        return ProjectStore(Path(projects_dir))

    def project_out(st: ProjectStore, slug: str) -> ProjectOut:
        story = st.load(slug)
        issues = check_story(story, lambda rel: st.asset_exists(slug, rel))
        return ProjectOut(slug=slug, story=story, issues=issues)

    api = APIRouter(prefix="/api/v1")

    @api.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    @api.get("/whoami")
    def whoami(request: Request) -> WhoAmI:
        return WhoAmI(is_host=bool(request.scope["state"].get("is_host")))

    @api.get("/settings")
    def get_settings() -> SettingsOut:
        s: AppSettings = app.state.settings
        return SettingsOut(
            projects_dir=s.projects_dir,
            suggested_projects_dir=str(suggested_projects_dir("Story")),
            port=s.port,
        )

    @api.put("/settings")
    def put_settings(body: SettingsIn) -> SettingsOut:
        raw = body.projects_dir.strip().strip('"')
        if not raw:
            raise HTTPException(400, "Choose a projects folder.")
        folder = Path(raw).expanduser()
        if not folder.is_absolute():
            raise HTTPException(
                400, "Use a full folder path, e.g. C:\\Users\\you\\Documents\\Stories."
            )
        try:
            folder.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise HTTPException(400, f"Cannot use that folder: {exc}") from exc
        app.state.settings.projects_dir = str(folder)
        save_settings(app.state.settings)
        return get_settings()

    @api.get("/projects")
    def list_projects() -> list[ProjectSummary]:
        return store().list()

    @api.post("/projects", status_code=201)
    def create_project(body: CreateProject) -> Created:
        return Created(slug=store().create(body.title))

    @api.post("/projects/import", status_code=201)
    async def import_project(file: UploadFile = File(...)) -> Created:
        return Created(slug=store().import_zip(await file.read()))

    @api.get("/examples")
    def list_examples() -> list[ExampleOut]:
        root = examples_dir()
        out = []
        if root.is_dir():
            for folder in sorted(root.iterdir()):
                if (folder / STORY_FILE).is_file():
                    story = Story.model_validate_json(
                        (folder / STORY_FILE).read_text(encoding="utf-8-sig")
                    )
                    out.append(
                        ExampleOut(
                            name=folder.name, title=story.title, description=story.description
                        )
                    )
        return out

    @api.post("/examples/{name}/copy", status_code=201)
    def copy_example(name: str) -> Created:
        folder = examples_dir() / name
        if "/" in name or "\\" in name or ".." in name or not (folder / STORY_FILE).is_file():
            raise NotFound(f"No example '{name}'.")
        return Created(slug=store().copy_from(folder))

    @api.get("/projects/{slug}")
    def get_project(slug: str) -> ProjectOut:
        return project_out(store(), slug)

    @api.put("/projects/{slug}")
    def save_project(slug: str, story: Story) -> Saved:
        st = store()
        st.save(slug, story)
        return Saved(issues=check_story(story, lambda rel: st.asset_exists(slug, rel)))

    @api.get("/projects/{slug}/export")
    def export_project(slug: str) -> Response:
        data = store().export_zip(slug)
        return Response(
            data,
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="{slug}.zip"'},
        )

    @api.get("/projects/{slug}/assets")
    def list_assets(slug: str) -> list[AssetInfo]:
        return store().list_assets(slug)

    @api.post("/projects/{slug}/assets", status_code=201)
    async def upload_asset(slug: str, file: UploadFile = File(...)) -> AssetInfo:
        return store().add_asset(slug, file.filename or "asset", await file.read())

    @api.get("/projects/{slug}/files/{rel:path}")
    def get_file(slug: str, rel: str) -> FileResponse:
        path = store().asset_file(slug, rel)
        if not path.is_file():
            raise NotFound(f"No file '{rel}'.")
        return FileResponse(path)

    # --- playthroughs ------------------------------------------------------------

    @api.post("/projects/{slug}/playthroughs", status_code=201)
    async def start_playthrough(slug: str, body: StartRun) -> dict[str, Any]:
        st = store()
        story = st.load(slug)
        errors = [
            i
            for i in check_story(story, lambda rel: st.asset_exists(slug, rel))
            if i.level == "error"
        ]
        if errors:
            raise HTTPException(
                400,
                f"Fix {len(errors)} error{'s' if len(errors) != 1 else ''} in the story first: {errors[0].message}",
            )
        return await runs.start(st, slug, body.mode)

    @api.get("/projects/{slug}/playthroughs")
    def list_playthroughs(slug: str) -> list[PlaythroughSummary]:
        return store().list_playthroughs(slug)

    @api.get("/projects/{slug}/playthroughs/{pid}")
    def get_playthrough(slug: str, pid: str) -> dict[str, Any]:
        return store().load_playthrough(slug, pid)

    # --- AI and matching settings ------------------------------------------------

    @api.get("/settings/ai")
    def get_ai_settings() -> AiSettings:
        return app.state.settings.ai

    @api.put("/settings/ai")
    def put_ai_settings(body: AiSettings) -> AiSettings:
        app.state.settings.ai = body
        save_settings(app.state.settings)
        return body

    @api.get("/ai/status")
    async def ai_status() -> dict[str, Any]:
        """Which backends are ready, and which one a playthrough would use now."""
        ai: AiSettings = app.state.settings.ai
        backends = await check_all(ai)
        backend, reason = await choose_ai()
        return {
            "setting": ai.backend,
            "backends": [b.model_dump() for b in backends],
            "chosen": backend.label if backend else None,
            "reason": reason,
        }

    @api.post("/ai/test")
    async def ai_test() -> dict[str, Any]:
        """One tiny real call to the backend a playthrough would use, to see it works and how long it takes."""
        backend, reason = await choose_ai()
        if backend is None:
            return {"ok": False, "detail": reason}
        try:
            answer, seconds = await ask_json(
                backend,
                'You are a test. Answer with JSON only: {"ok": true, "line": "<a five-word greeting>"}',
                "Say hello.",
                app.state.settings.ai.timeout_s,
            )
        except AiError as exc:
            return {"ok": False, "backend": backend.label, "detail": str(exc)}
        return {
            "ok": True,
            "backend": backend.label,
            "seconds": round(seconds, 2),
            "answer": answer,
        }

    @api.get("/matching/status")
    async def matching_status() -> dict[str, Any]:
        if embeddings is None:
            return {
                "matcher": "word overlap",
                "model": None,
                "ready": False,
                "downloading": False,
                "detail": "Embedding matching is disabled.",
            }
        status = await asyncio.to_thread(embeddings.status)
        return {
            "matcher": "embeddings" if status.ready else "word overlap",
            **status.model_dump(),
            "size_mb": DEFAULT_MODEL_MB,
        }

    @api.post("/matching/download")
    async def matching_download() -> dict[str, Any]:
        """Download the embedding model (about 67 MB, from Hugging Face via fastembed)."""
        if embeddings is None:
            raise HTTPException(400, "Embedding matching is disabled.")
        status = embeddings.status()
        if not status.ready and not status.downloading:
            asyncio.get_running_loop().run_in_executor(None, embeddings.load, True)
            await asyncio.sleep(0.2)
        return await matching_status()

    app.include_router(api)
    app.include_router(live_router(runs, lan=lan, port=lambda: app.state.port))

    @app.exception_handler(RunError)
    async def _run_error(_r: Request, exc: RunError) -> JSONResponse:
        return JSONResponse({"detail": str(exc), "code": "no_playthrough"}, 409)

    @app.exception_handler(SetupRequired)
    async def _setup(_r: Request, _e: SetupRequired) -> JSONResponse:
        return JSONResponse(
            {"detail": "Choose a projects folder first.", "code": "setup_required"}, 409
        )

    @app.exception_handler(NotFound)
    async def _not_found(_r: Request, exc: NotFound) -> JSONResponse:
        return JSONResponse({"detail": str(exc), "code": "not_found"}, 404)

    @app.exception_handler(StoreError)
    async def _store_error(_r: Request, exc: StoreError) -> JSONResponse:
        return JSONResponse({"detail": str(exc), "code": "bad_request"}, 400)

    dist = Path(os.environ.get("STORY_WEB_DIST", APP_DIR / "web" / "dist"))
    if (dist / "index.html").is_file():
        app.mount("/", StaticFiles(directory=dist, html=True), name="web")
    return app
