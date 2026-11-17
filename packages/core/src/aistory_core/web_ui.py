"""Serving a built UI (Vite's `dist`) from the app's server."""

from __future__ import annotations

from starlette.responses import Response
from starlette.staticfiles import StaticFiles
from starlette.types import Scope


class UIFiles(StaticFiles):
    """Static files where the HTML page is checked again on every load.

    Vite gives the scripts and styles new names on each build, but `index.html` keeps its name;
    without `no-cache` a browser may keep an old copy that loads the previous build's UI.
    """

    def __init__(self, directory: str | object) -> None:
        super().__init__(directory=directory, html=True)  # type: ignore[arg-type]

    async def get_response(self, path: str, scope: Scope) -> Response:
        response = await super().get_response(path, scope)
        if response.headers.get("content-type", "").startswith("text/html"):
            response.headers["Cache-Control"] = "no-cache"
        return response
