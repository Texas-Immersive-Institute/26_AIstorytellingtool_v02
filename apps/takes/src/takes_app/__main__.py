"""takestool: run Takes in its own window, or check that ComfyUI is ready.

takestool              start the server on 127.0.0.1:8778 and open the Takes window
takestool --browser    open Takes in your web browser instead of its own window
takestool --no-window  run the server only (e.g. for `npm run dev`)
takestool check        check that the H3 ComfyUI is running and can render
"""

from __future__ import annotations

import argparse
import asyncio
import json
import threading
import time
import webbrowser
from dataclasses import asdict

import httpx

WINDOW_SIZE = (1440, 920)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="takestool", description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command")
    check = sub.add_parser("check", help="check that the H3 ComfyUI is running and ready")
    check.add_argument("--url", help="check this address instead of the configured one")
    parser.add_argument("--port", type=int, default=None)
    show = parser.add_mutually_exclusive_group()
    show.add_argument("--browser", action="store_true", help="open in the web browser")
    show.add_argument("--no-window", action="store_true", help="run the server only")
    args = parser.parse_args(argv)

    from takes_app.settings import load_settings

    settings = load_settings()

    if args.command == "check":
        from takes_app.comfyui import check as check_comfy

        status = asyncio.run(check_comfy(args.url or settings.comfyui_url))
        print(json.dumps(asdict(status), indent=2))
        raise SystemExit(0 if status.ready else 1)

    import uvicorn

    from takes_app.api import create_app

    port = args.port or settings.port
    url = f"http://127.0.0.1:{port}/"

    if takes_running(url):
        # Takes is already running (e.g. its window was opened twice): show another window.
        print(f"Takes is already running at {url}")
        if not args.no_window:
            show_ui(url, browser=args.browser)
        return

    config = uvicorn.Config(create_app(settings), host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    print(f"Takes is running at {url}")

    if args.no_window:
        server.run()
        return

    thread = threading.Thread(target=server.run, name="takes-server", daemon=True)
    thread.start()
    while not server.started:
        if not thread.is_alive():
            raise SystemExit(f"Takes couldn't start on port {port}; is something else using it?")
        time.sleep(0.05)

    if show_ui(url, browser=args.browser):
        # The window was closed: stop the server, letting the generator save its state.
        server.should_exit = True
        thread.join(timeout=15)
    else:
        print("Close this window or press Ctrl+C to stop Takes.")
        try:
            thread.join()
        except KeyboardInterrupt:
            server.should_exit = True
            thread.join(timeout=15)


def takes_running(url: str) -> bool:
    try:
        return httpx.get(url + "api/health", timeout=1).json().get("service") == "takes"
    except (httpx.HTTPError, ValueError):
        return False


def show_ui(url: str, *, browser: bool) -> bool:
    """Open Takes in its own window and wait until it is closed (True), or in the web browser
    (False) when asked to or when no desktop window can be shown here."""
    if not browser:
        try:
            import webview

            webview.create_window(
                "Takes", url, width=WINDOW_SIZE[0], height=WINDOW_SIZE[1], min_size=(960, 640)
            )
            webview.start()
            return True
        except Exception as exc:  # no GUI backend (e.g. missing WebView2): fall back
            print(f"Couldn't open the Takes window ({exc}); opening your browser instead.")
    webbrowser.open(url)
    return False


if __name__ == "__main__":
    main()
