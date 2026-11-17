"""A stand-in for the H3 ComfyUI, speaking ComfyUI's HTTP API over httpx.MockTransport."""

from __future__ import annotations

import json
import re
from typing import Any

import httpx
import pytest


@pytest.fixture(autouse=True)
def _isolated_data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("AISTORY_DATA_DIR", str(tmp_path / "appdata"))


class FakeComfy:
    def __init__(self) -> None:
        self.running = True  # False: nothing answers (connection refused)
        self.h3_nodes = True
        self.uploads: list[tuple[str, str]] = []  # (name, subfolder)
        self.prompts: dict[str, dict[str, Any]] = {}  # prompt id -> workflow
        self.state: dict[str, dict[str, Any]] = {}  # prompt id -> {"polls", "fail", "done"}
        self.log: list[str] = []  # calls that change state, in order
        self.fail_next: str | None = None
        self.polls_to_finish = 2
        self.node_errors: dict[str, Any] | None = None
        self.transport = httpx.MockTransport(self.handle)

    def handle(self, request: httpx.Request) -> httpx.Response:
        if not self.running:
            raise httpx.ConnectError("refused", request=request)
        path, method = request.url.path, request.method
        ok = lambda body, status=200: httpx.Response(status, json=body)  # noqa: E731

        if path == "/system_stats":
            return ok(
                {"system": {"comfyui_version": "0.3.99"}, "devices": [{"name": "cuda:0 RTX"}]}
            )
        if m := re.fullmatch(r"/object_info/(\w+)", path):
            return ok({m[1]: {"input": {}}} if self.h3_nodes else {})
        if path == "/upload/image":
            body = request.content.decode("latin-1")
            name = re.search(r'filename="([^"]+)"', body)[1]
            sub = re.search(r'name="subfolder"\r\n\r\n([^\r]*)', body)[1]
            self.uploads.append((name, sub))
            return ok({"name": name, "subfolder": sub, "type": "input"})
        if path == "/prompt" and method == "POST":
            if self.node_errors:
                return ok(
                    {
                        "error": {"message": "Prompt outputs failed validation"},
                        "node_errors": self.node_errors,
                    },
                    400,
                )
            prompt_id = f"p{len(self.prompts) + 1}"
            self.prompts[prompt_id] = json.loads(request.content)["prompt"]
            self.state[prompt_id] = {
                "polls": 0,
                "fail": self.fail_next,
                "done": False,
                "removed": False,
            }
            self.fail_next = None
            self.log.append(f"queue {prompt_id}")
            return ok({"prompt_id": prompt_id, "number": 1, "node_errors": {}})
        if m := re.fullmatch(r"/history/(\w+)", path):
            st = self.state.get(m[1])
            if st is None or st["removed"]:
                return ok({})
            if not st["done"]:
                st["polls"] += 1
                if st["polls"] <= self.polls_to_finish:
                    return ok({})
                st["done"] = True
                self.log.append(f"done {m[1]}")
            return ok({m[1]: self._history(m[1], st)})
        if path == "/queue" and method == "GET":
            active = [pid for pid, st in self.state.items() if not st["done"] and not st["removed"]]
            return ok(
                {
                    "queue_running": [[0, pid, {}, {}] for pid in active[:1]],
                    "queue_pending": [[1, pid, {}, {}] for pid in active[1:]],
                }
            )
        if path == "/queue" and method == "POST":
            for pid in json.loads(request.content).get("delete", []):
                self.state[pid]["removed"] = True
                self.log.append(f"delete {pid}")
            return ok({})
        if path == "/interrupt":
            active = [pid for pid, st in self.state.items() if not st["done"] and not st["removed"]]
            if active:
                self.state[active[0]].update(done=True, fail="interrupted")
            self.log.append("interrupt")
            return ok({})
        if path == "/view":
            q = request.url.params
            return httpx.Response(
                200, content=f"bytes of {q['subfolder']}/{q['filename']}".encode()
            )
        return ok({"error": f"fake ComfyUI has no {method} {path}"}, 404)

    def _history(self, prompt_id: str, st: dict[str, Any]) -> dict[str, Any]:
        if st["fail"] == "interrupted":
            return {
                "status": {"status_str": "error", "messages": [["execution_interrupted", {}]]},
                "outputs": {},
            }
        if st["fail"]:
            return {
                "status": {
                    "status_str": "error",
                    "messages": [
                        [
                            "execution_error",
                            {"node_type": "KSampler", "exception_message": st["fail"]},
                        ]
                    ],
                },
                "outputs": {},
            }
        voice_folder = self.output_folder(prompt_id, "/take1")
        if voice_folder != "?":  # the voice stage saves three spoken takes
            return {
                "status": {"status_str": "success", "completed": True, "messages": []},
                "outputs": {
                    f"60{n}": {
                        "audio": [
                            {
                                "filename": f"take{n}_00001.mp3",
                                "subfolder": f"h3/{voice_folder}",
                                "type": "output",
                            }
                        ]
                    }
                    for n in (1, 2, 3)
                },
            }
        folder = f"h3/{self.output_folder(prompt_id)}"
        return {
            "status": {"status_str": "success", "completed": True, "messages": []},
            "outputs": {
                "500": {
                    "gifs": [
                        {
                            "filename": "final_00001-audio.mp4",
                            "subfolder": folder,
                            "type": "output",
                            "fullpath": "C:/x",
                        }
                    ]
                },
                "501": {
                    "gifs": [
                        {"filename": "preview_00001.mp4", "subfolder": folder, "type": "output"}
                    ]
                },
                "502": {"images": [{"filename": "tmp_0001.png", "subfolder": "", "type": "temp"}]},
            },
        }

    def output_folder(self, prompt_id: str, ending: str = "/final") -> str:
        """The run id Takes wrote into the recipe's output names (h3/{run_id}/final)."""
        for node in self.prompts.get(prompt_id, {}).values():
            for value in node.get("inputs", {}).values():
                if isinstance(value, str) and value.startswith("h3/") and value.endswith(ending):
                    return value.split("/")[1]
        return "?"


@pytest.fixture
def fake_comfy() -> FakeComfy:
    return FakeComfy()
