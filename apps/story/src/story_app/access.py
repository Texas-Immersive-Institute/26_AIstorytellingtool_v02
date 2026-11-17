"""Host-only by default. LAN devices may only load the UI and use the chat.

Stage, Debug and authoring belong to the host computer (see CONTEXT.md, Stage/Chat/Debug view).
"""

from __future__ import annotations

import ipaddress

from aistory_core.access import is_lan, is_loopback
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

DEV_ORIGINS = {"http://127.0.0.1:5174", "http://localhost:5174"}
LAN_API_PREFIXES = ("/api/v1/chat/", "/api/v1/whoami", "/api/v1/health")


def lan_may_access(path: str) -> bool:
    if path.startswith("/api/"):
        return path.startswith(LAN_API_PREFIXES)
    return path not in {"/docs", "/redoc", "/openapi.json"} and not path.startswith("/docs/")


class AccessMiddleware:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in {"http", "websocket"}:
            await self.app(scope, receive, send)
            return
        request = Request(scope)
        peer = request.client.host if request.client else None
        is_host = is_loopback(peer)
        scope.setdefault("state", {})["is_host"] = is_host

        async def reject(status: int, detail: str) -> None:
            if scope["type"] == "websocket":
                await send({"type": "websocket.close", "code": 4403})
                return
            await JSONResponse({"detail": detail}, status_code=status)(scope, receive, send)

        if not is_host and not is_lan(peer):
            await reject(403, "Only the host computer and devices on its LAN may connect.")
            return
        # Guard against DNS rebinding: the Host header must be an IP or localhost.
        hostname = request.url.hostname or ""
        try:
            ip = ipaddress.ip_address(hostname)
            valid_host = ip.is_loopback or ip.is_private
        except ValueError:
            valid_host = hostname == "localhost"
        if not valid_host:
            await reject(400, "Use localhost or the host's LAN IP address.")
            return
        origin = request.headers.get("origin")
        if origin:
            scheme = "ws" if scope["type"] == "websocket" else request.url.scheme
            same = origin.replace("http", scheme, 1) == f"{scheme}://{request.headers.get('host')}"
            if not (same or (is_host and origin in DEV_ORIGINS)):
                await reject(403, "Cross-origin requests are not allowed.")
                return
        if not is_host and not lan_may_access(request.url.path):
            await reject(403, "Only the host computer can do this.")
            return
        await self.app(scope, receive, send)
