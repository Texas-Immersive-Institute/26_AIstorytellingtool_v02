"""storytool: run the Story server.

storytool                 serve on 127.0.0.1 (host only) and open the browser
storytool --lan           also listen on the LAN so audience devices can open the chat
storytool schema OUT      write the story.json JSON Schema (used to generate TS types)
"""

from __future__ import annotations

import argparse
import json
import threading
import webbrowser
from pathlib import Path


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="storytool", description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command")
    schema = sub.add_parser("schema", help="write the story.json JSON Schema")
    schema.add_argument("out", type=Path)
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--lan", action="store_true", help="listen on all interfaces for LAN chat")
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args(argv)

    if args.command == "schema":
        from story_app.model import Story

        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(
            json.dumps(Story.model_json_schema(mode="serialization"), indent=2) + "\n",
            encoding="utf-8",
        )
        return

    import uvicorn

    from story_app.api import create_app
    from story_app.settings import load_settings

    settings = load_settings()
    port = args.port or settings.port
    host = "0.0.0.0" if args.lan else "127.0.0.1"
    url = f"http://127.0.0.1:{port}/"
    if not args.no_browser:
        threading.Timer(1.2, lambda: webbrowser.open(url)).start()
    print(f"Story is running at {url}" + (" (LAN chat enabled)" if args.lan else ""))
    uvicorn.run(
        create_app(settings, lan=args.lan, port=port), host=host, port=port, log_level="warning"
    )


if __name__ == "__main__":
    main()
