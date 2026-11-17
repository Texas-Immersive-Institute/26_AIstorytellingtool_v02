"""Renders takes in ComfyUI strictly one at a time.

A single worker takes queued takes and sees each one through before the next: for a voice
reference, speak the line in that voice first; upload the references; fill in the stage's
recipe; queue it; wait for it to finish; copy the saved files into the project. The GPU renders
one video at a time anyway, and waiting here rather than in ComfyUI's queue makes cancelling a
waiting take free (ADR-0006). Takes that were rendering when Takes closed are picked up again.
"""

from __future__ import annotations

import asyncio
import logging
import random
import shutil
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from takes_app.comfyui import (
    ComfyError,
    ComfyStatus,
    ComfyUI,
    ComfyUnreachable,
    outputs_of,
    run_error,
)
from takes_app.pack import Pack, PackError
from takes_app.stages import VOICE_STAGE, estimate_spoken_s, fit_duration
from takes_app.store import ProjectStore, StoreError, Take, TakeFile, TakeStatus, now

log = logging.getLogger(__name__)

VIDEO_SUFFIXES = (".mp4", ".webm", ".mov", ".mkv")
AUDIO_SUFFIXES = (".mp3", ".wav", ".flac", ".ogg", ".m4a")
MAX_SEED = 2**50  # the H3 seed input's maximum


class Cancelled(Exception):
    pass


async def probe_seconds(path: Path) -> float | None:
    """A media file's length from ffprobe, or None if ffprobe isn't installed or can't read it."""
    exe = shutil.which("ffprobe")
    if not exe:
        return None
    proc = await asyncio.create_subprocess_exec(
        exe, "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path),
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
    )  # fmt: skip
    out, _ = await proc.communicate()
    try:
        return float(out.decode().strip())
    except ValueError:
        return None


class Generator:
    def __init__(
        self,
        *,
        store: Callable[[], ProjectStore],
        pack: Pack,
        connect: Callable[[], Awaitable[ComfyStatus]],
        make_comfy: Callable[[str], ComfyUI] = ComfyUI,
        probe: Callable[[Path], Awaitable[float | None]] = probe_seconds,
        poll_s: float = 5.0,
        max_wait_s: float = 3 * 3600,
        unreachable_grace: int = 12,
    ):
        self.store = store
        self.pack = pack
        self.connect = connect
        self.make_comfy = make_comfy
        self.probe = probe
        self.poll_s = poll_s
        self.max_wait_s = max_wait_s
        self.unreachable_grace = unreachable_grace
        self._queue: asyncio.Queue[tuple[str, str]] = asyncio.Queue()
        self._worker: asyncio.Task[None] | None = None

    # -- lifecycle -----------------------------------------------------------------------------

    def start(self) -> None:
        if self._worker is None or self._worker.done():
            self._worker = asyncio.create_task(self._work(), name="takes-generator")

    async def stop(self) -> None:
        if self._worker:
            self._worker.cancel()
            try:
                await self._worker
            except asyncio.CancelledError:
                pass
            self._worker = None

    def resume(self) -> int:
        """Queue again every take that was waiting or rendering when Takes last stopped."""
        found = self.store().unfinished()
        for slug, take_id in found:
            self.enqueue(slug, take_id)
        return len(found)

    def enqueue(self, slug: str, take_id: str) -> None:
        self._queue.put_nowait((slug, take_id))
        self.start()

    def cancel(self, slug: str, take_id: str) -> Take:
        store = self.store()
        shot, take = store.load(slug).find_take(take_id)
        if take.status == "queued":
            self._finish(take, "cancelled")
            store.save(slug)
        elif take.status in ("preparing", "voicing", "rendering"):
            take.cancel_requested = True  # the worker stops it before queueing or cancels the run
        return take

    # -- the worker ----------------------------------------------------------------------------

    async def _work(self) -> None:
        while True:
            slug, take_id = await self._queue.get()
            try:
                store = self.store()
                shot, take = store.load(slug).find_take(take_id)
            except StoreError:
                self._queue.task_done()
                continue  # the project or take was removed while it waited
            try:
                if take.status not in ("done", "failed", "cancelled"):
                    await self._generate(store, slug, take)
                    if take.status == "done":
                        shot.take_done(take)
            except Cancelled:
                self._finish(take, "cancelled")
            except (ComfyError, PackError, StoreError) as exc:
                self._fail(take, str(exc))
            except asyncio.CancelledError:
                self._fail(take, "Takes stopped before this take finished")
                raise
            except Exception as exc:  # keep the worker alive for the next take
                log.exception("take %s failed", take.id)
                self._fail(take, f"Unexpected error: {exc}")
            finally:
                try:
                    store.save(slug)
                except StoreError:
                    pass
                self._queue.task_done()

    @staticmethod
    def _finish(take: Take, status: TakeStatus) -> None:
        take.status = status
        take.finished_at = now()

    def _fail(self, take: Take, message: str) -> None:
        if take.status not in ("done", "cancelled"):
            take.error = message
            self._finish(take, "failed")

    async def _generate(self, store: ProjectStore, slug: str, take: Take) -> None:
        def status(value: TakeStatus) -> None:
            take.status = value
            store.save(slug)

        resuming = bool(take.prompt_id) and take.status in ("rendering", "downloading")
        if not resuming:
            take.prompt_id = None
            status("preparing")
        ready = await self.connect()
        if not ready.ready:
            raise ComfyError(ready.message)

        async with self.make_comfy(ready.url) as comfy:
            if not resuming:
                req = take.request
                if take.seed is None:
                    take.seed = req.seed if req.seed is not None else random.randrange(MAX_SEED)
                if req.audio == "voice" and take.voice_audio is None:
                    status("voicing")
                    take.voice_audio = await self._speak(comfy, store, slug, take)
                workflow = await self._video_workflow(comfy, store, slug, take)
                if take.cancel_requested:
                    raise Cancelled
                take.prompt_id = await comfy.queue_prompt(workflow)
                status("rendering")

            entry = await self._wait(comfy, take, take.prompt_id or "")
            status("downloading")
            take.files = await self._collect(comfy, entry, store.take_dir(slug, take.id))
            take.error = None
            self._finish(take, "done")

    async def _video_workflow(
        self, comfy: ComfyUI, store: ProjectStore, slug: str, take: Take
    ) -> dict[str, Any]:
        req = take.request
        subfolder = self.pack.stage(take.stage).param("references").upload_subfolder or ""
        audio = req.audio_clip if req.audio == "clip" else take.voice_audio
        duration = req.duration_s
        if audio:
            # The forced soundtrack sets the length; H3 lengths come in fixed steps.
            seconds = await self.probe(store.media_path(slug, audio))
            if seconds is None and req.voice:
                seconds = req.voice.spoken_s or estimate_spoken_s(req.voice.line)
            if seconds is not None:
                duration = fit_duration(seconds)
        take.duration_s = duration
        references: list[dict[str, Any]] = []
        for kind, media_id in [
            *(("picture", m) for m in req.pictures),
            *([("audio", audio)] if audio else []),
        ]:
            uploaded = await comfy.upload(store.media_path(slug, media_id), subfolder)
            references.append({"kind": kind, **uploaded})
        return self.pack.fill(
            take.stage,
            {
                "prompt": req.prompt,
                "references": references,
                "duration_s": duration,
                "aspect_ratio": req.aspect_ratio,
                "seed": take.seed,
            },
            run_id=take.id,
        )

    async def _speak(self, comfy: ComfyUI, store: ProjectStore, slug: str, take: Take) -> str:
        """Say the line in the voice reference's voice; returns the spoken take's media id.
        The voice stage makes three takes; v1 uses take 1 (voice-take picking is out of v1)."""
        voice = take.request.voice
        assert voice is not None
        stage = self.pack.stage(VOICE_STAGE)
        uploaded = await comfy.upload(
            store.media_path(slug, voice.clip), stage.param("voice_ref_file").upload_subfolder or ""
        )
        values: dict[str, Any] = {
            "voice_ref_file": uploaded,
            "line": voice.line,
            "tone": voice.tone,
            "length_s": voice.spoken_s or estimate_spoken_s(voice.line),
            "seed": take.seed,
        }
        if voice.clip_start_s is not None:
            values["voice_ref_start_s"] = voice.clip_start_s
        if voice.clip_length_s is not None:
            values["voice_ref_duration_s"] = voice.clip_length_s
        workflow = self.pack.fill(VOICE_STAGE, values, run_id=f"{take.id}-voice")
        if take.cancel_requested:
            raise Cancelled
        prompt_id = await comfy.queue_prompt(workflow)
        entry = await self._wait(comfy, take, prompt_id)
        audio = [f for f in outputs_of(entry) if f["filename"].lower().endswith(AUDIO_SUFFIXES)]
        if not audio:
            raise ComfyError("The voice run finished but saved no audio")
        first = next((f for f in audio if "take1" in f["filename"].lower()), audio[0])
        media_id = f"{take.id}-voice-{first['filename']}"
        await comfy.download(first, store.project_dir(slug) / "media" / media_id)
        return media_id

    async def _wait(self, comfy: ComfyUI, take: Take, prompt_id: str) -> dict[str, Any]:
        """ComfyUI's record of the finished run. Raises Cancelled if the take was cancelled."""
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self.max_wait_s
        misses = 0
        cancel_sent = False
        while True:
            try:
                if take.cancel_requested and not cancel_sent:
                    cancel_sent = True
                    await comfy.cancel(prompt_id)
                entry = await comfy.history(prompt_id)
                if entry is not None:
                    if take.cancel_requested and run_error(entry):
                        raise Cancelled
                    error = run_error(entry)
                    if error:
                        raise ComfyError(error)
                    return entry
                if cancel_sent:
                    running, pending = await comfy.queue()
                    if prompt_id not in running | pending:
                        raise Cancelled
                misses = 0
            except ComfyUnreachable:
                # ComfyUI may be restarting; keep trying for a while before giving up.
                misses += 1
                if misses > self.unreachable_grace:
                    raise
            if loop.time() > deadline:
                raise ComfyError(
                    f"The run is still going after {self.max_wait_s / 60:.0f} minutes; "
                    "check ComfyUI's queue"
                )
            await asyncio.sleep(self.poll_s)

    async def _collect(self, comfy: ComfyUI, entry: dict[str, Any], folder: Path) -> list[TakeFile]:
        outputs = outputs_of(entry)
        if not outputs:
            raise ComfyError("The run finished but saved no files")
        files: list[TakeFile] = []
        for output in outputs:
            name = output["filename"].replace("\\", "/").rsplit("/", 1)[-1]
            size = await comfy.download(output, folder / name)
            files.append(TakeFile(name=name, size=size))
        videos = [f for f in files if f.name.lower().endswith(VIDEO_SUFFIXES)]
        main = next((f for f in videos if f.name.lower().startswith("final")), None) or (
            videos[0] if videos else None
        )
        if main:
            main.main = True
        return files
