"""Talks to ComfyUI directly over its HTTP API (ADR-0006). Takes expects ComfyUI to be running
already, on 127.0.0.1:8188 unless settings say otherwise; it never starts ComfyUI itself.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

DEFAULT_URL = "http://127.0.0.1:8188"
# A node the H3 workflows use; if ComfyUI doesn't know it, this isn't the H3 ComfyUI.
MARKER_NODE = "H3PromptIDE"


class ComfyError(Exception):
    """ComfyUI refused something, or a run failed."""


class ComfyUnreachable(ComfyError):
    """Nothing answered at ComfyUI's address."""


class ComfyUI:
    def __init__(
        self,
        base_url: str = DEFAULT_URL,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout: float = 30.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.client_id = uuid.uuid4().hex
        self._http = httpx.AsyncClient(base_url=self.base_url, transport=transport, timeout=timeout)

    async def __aenter__(self) -> ComfyUI:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self._http.aclose()

    async def _call(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        try:
            response = await self._http.request(method, path, **kwargs)
        except httpx.TransportError as exc:
            raise ComfyUnreachable(f"No answer from ComfyUI at {self.base_url}") from exc
        if response.status_code >= 400:
            raise ComfyError(
                f"ComfyUI answered {response.status_code} to {path}: {response.text[:300]}"
            )
        return response

    async def system_stats(self) -> dict[str, Any]:
        return (await self._call("GET", "/system_stats")).json()

    async def has_node(self, class_type: str) -> bool:
        return class_type in ((await self._call("GET", f"/object_info/{class_type}")).json() or {})

    async def upload(self, path: Path, subfolder: str = "") -> dict[str, str]:
        """Copy a file into ComfyUI's input folder. /upload/image takes any media file."""
        with path.open("rb") as fh:
            response = await self._call(
                "POST",
                "/upload/image",
                files={"image": (path.name, fh, "application/octet-stream")},
                data={"overwrite": "false", "type": "input", "subfolder": subfolder},
            )
        body = response.json()
        return {
            "name": str(body.get("name") or path.name),
            "subfolder": str(body.get("subfolder") or subfolder),
        }

    async def queue_prompt(self, workflow: dict[str, Any]) -> str:
        try:
            response = await self._http.post(
                "/prompt", json={"prompt": workflow, "client_id": self.client_id}
            )
        except httpx.TransportError as exc:
            raise ComfyUnreachable(f"No answer from ComfyUI at {self.base_url}") from exc
        body = _json(response)
        if response.status_code >= 400 or body.get("node_errors"):
            raise ComfyError(
                _prompt_error(body) or f"ComfyUI refused the workflow ({response.status_code})"
            )
        if not body.get("prompt_id"):
            raise ComfyError(f"ComfyUI didn't return a prompt id: {body}")
        return str(body["prompt_id"])

    async def history(self, prompt_id: str) -> dict[str, Any] | None:
        """The finished run's record, or None while it is still queued or running."""
        body = (await self._call("GET", f"/history/{prompt_id}")).json() or {}
        return body.get(prompt_id)

    async def queue(self) -> tuple[set[str], set[str]]:
        """(running, pending) prompt ids."""
        body = (await self._call("GET", "/queue")).json() or {}

        def ids(key: str) -> set[str]:
            return {
                str(item[1])
                for item in body.get(key) or []
                if isinstance(item, list) and len(item) > 1
            }

        return ids("queue_running"), ids("queue_pending")

    async def cancel(self, prompt_id: str) -> None:
        """Drop it from the queue, or interrupt it if it is the one rendering (and only then)."""
        running, pending = await self.queue()
        if prompt_id in pending:
            await self._call("POST", "/queue", json={"delete": [prompt_id]})
        elif prompt_id in running:
            await self._call("POST", "/interrupt")

    async def download(self, file: dict[str, Any], dest: Path) -> int:
        params = {
            "filename": file["filename"],
            "subfolder": file.get("subfolder", ""),
            "type": file.get("type", "output"),
        }
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_name(dest.name + ".part")
        size = 0
        try:
            async with self._http.stream("GET", "/view", params=params) as response:
                if response.status_code >= 400:
                    raise ComfyError(
                        f"ComfyUI couldn't send {file['filename']} ({response.status_code})"
                    )
                with tmp.open("wb") as out:
                    async for chunk in response.aiter_bytes():
                        out.write(chunk)
                        size += len(chunk)
        except httpx.TransportError as exc:
            tmp.unlink(missing_ok=True)
            raise ComfyUnreachable(f"Lost ComfyUI while downloading {file['filename']}") from exc
        except BaseException:
            tmp.unlink(missing_ok=True)
            raise
        tmp.replace(dest)
        return size


def outputs_of(entry: dict[str, Any]) -> list[dict[str, Any]]:
    """Files a finished run saved. Video nodes report under "gifs", audio under "audio".
    Temp previews are dropped when the run also saved real outputs."""
    files: list[dict[str, Any]] = []
    for node_id, node_out in (entry.get("outputs") or {}).items():
        if not isinstance(node_out, dict):
            continue
        for key in ("images", "gifs", "audio", "files", "videos"):
            for item in node_out.get(key) or []:
                if isinstance(item, dict) and item.get("filename"):
                    files.append(
                        {
                            "filename": str(item["filename"]),
                            "subfolder": str(item.get("subfolder") or ""),
                            "type": str(item.get("type") or "output"),
                            "node_id": str(node_id),
                        }
                    )
    if any(f["type"] == "output" for f in files):
        files = [f for f in files if f["type"] == "output"]
    return files


def run_error(entry: dict[str, Any]) -> str | None:
    """The reason a finished run failed, or None if it succeeded."""
    status = entry.get("status") or {}
    if status.get("status_str") != "error":
        return None
    for kind, data in status.get("messages") or []:
        if kind == "execution_interrupted":
            return "The run was interrupted"
        if kind == "execution_error" and isinstance(data, dict):
            node = data.get("node_type") or data.get("node_id") or "a node"
            return f"{node} failed: {data.get('exception_message', '').strip() or 'unknown error'}"
    return "The run failed in ComfyUI"


def _json(response: httpx.Response) -> dict[str, Any]:
    try:
        body = response.json()
    except ValueError:
        return {"error": {"message": response.text[:300]}}
    return body if isinstance(body, dict) else {}


def _prompt_error(body: dict[str, Any]) -> str | None:
    parts: list[str] = []
    error = body.get("error")
    if isinstance(error, dict) and error.get("message"):
        parts.append(str(error["message"]))
    for node_id, info in (body.get("node_errors") or {}).items():
        for err in (info or {}).get("errors") or []:
            parts.append(
                f"node {node_id} ({info.get('class_type', '?')}): {err.get('message')} {err.get('details', '')}".strip()
            )
    return "; ".join(parts) or None


# -- is ComfyUI there, and is it the H3 one? ------------------------------------------------------


@dataclass
class ComfyStatus:
    url: str
    reachable: bool = False
    h3_nodes: bool = False
    ready: bool = False
    manual: bool = False  # the address came from settings
    version: str | None = None
    gpus: list[str] = field(default_factory=list)
    message: str = ""


async def check(
    manual_url: str | None, *, transport: httpx.AsyncBaseTransport | None = None
) -> ComfyStatus:
    url = (manual_url or DEFAULT_URL).rstrip("/")
    status = ComfyStatus(url=url, manual=bool(manual_url))
    async with ComfyUI(url, transport=transport, timeout=5.0) as comfy:
        try:
            stats = await comfy.system_stats()
        except ComfyError as exc:
            status.message = (
                f"ComfyUI isn't running at {url}. Start the H3 ComfyUI, then try again."
                if isinstance(exc, ComfyUnreachable)
                else f"Something at {url} answered, but not as ComfyUI: {exc}"
            )
            return status
        status.reachable = True
        system = stats.get("system") or {}
        status.version = system.get("comfyui_version")
        status.gpus = [str(d.get("name")) for d in stats.get("devices") or [] if d.get("name")]
        try:
            status.h3_nodes = await comfy.has_node(MARKER_NODE)
        except ComfyError as exc:
            status.message = f"ComfyUI answered but couldn't list its nodes: {exc}"
            return status
    if not status.h3_nodes:
        status.message = (
            f"The ComfyUI at {url} doesn't have the MiniMax H3 nodes. Point Takes at the "
            "H3 ComfyUI in settings, or install the H3 nodes there."
        )
    else:
        status.ready = True
        status.message = f"Connected to ComfyUI at {url}."
    return status
