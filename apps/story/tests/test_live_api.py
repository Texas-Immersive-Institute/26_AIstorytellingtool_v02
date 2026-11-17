import json
import time

import pytest
from aistory_core.ai import Availability, Backend
from conftest import EXAMPLE, no_ai
from fastapi.testclient import TestClient
from story_app.api import create_app
from story_app.live_api import chat_view
from story_app.settings import AppSettings


class ScriptedBackend(Backend):
    name = "ollama"
    label = "Scripted"

    def __init__(self):
        self.calls = []

    async def check(self):
        return Availability(backend="ollama", label=self.label, ok=True, detail="test")

    async def complete(self, system, prompt, timeout):
        self.calls.append(prompt)
        if "VARIABLE: dog_name" in prompt:
            return json.dumps({"value": "Biscuit the Brave"})
        return json.dumps({"line": "A line the AI wrote.", "memory": [], "profile": []})


def make_client(tmp_path, monkeypatch, *, lan=False, choose_ai=no_ai):
    monkeypatch.setenv("STORY_EXAMPLES_DIR", str(EXAMPLE.parent))
    monkeypatch.setenv("STORY_WEB_DIST", str(tmp_path / "no-dist"))
    app = create_app(
        AppSettings(projects_dir=str(tmp_path / "projects")),
        lan=lan,
        port=8777,
        embeddings=None,
        choose_ai=choose_ai,
    )
    return TestClient(app, client=("127.0.0.1", 50000), base_url="http://127.0.0.1:8777")


@pytest.fixture
def client(tmp_path, monkeypatch):
    with make_client(tmp_path, monkeypatch) as c:
        yield c


def start(client):
    slug = client.post("/api/v1/examples/lighthouse/copy").json()["slug"]
    client.post(f"/api/v1/projects/{slug}/playthroughs", json={"mode": "live"})
    return slug


def skip_to(client, kind):
    for _ in range(40):
        snap = client.get("/api/v1/run").json()
        if snap["window"] and snap["window"]["kind"] == kind:
            return snap
        client.post("/api/v1/run/control", json={"action": "skip"})
    raise AssertionError(kind)


def phone(client, ip="192.168.1.50"):
    return TestClient(client.app, client=(ip, 1), base_url="http://192.168.1.10:8777")


def test_chat_from_a_lan_device(client):
    start(client)
    skip_to(client, "choice")
    device = phone(client)
    state = device.get("/api/v1/chat/state").json()
    assert state["window"]["prompt"] == "Should Mara open the door?"
    assert [o["label"] for o in state["window"]["options"]] == ["Let him in", "Turn him away"]
    sent = device.post(
        "/api/v1/chat/messages",
        json={"participant": "phone-abc123", "name": "Ana", "text": "let him in"},
    )
    assert sent.status_code == 201
    other = phone(client, "192.168.1.51")
    msg_id = sent.json()["id"]
    assert other.post(
        f"/api/v1/chat/messages/{msg_id}/thumbs", json={"participant": "phone-xyz789"}
    ).json()["ok"]
    assert not device.post(
        f"/api/v1/chat/messages/{msg_id}/thumbs", json={"participant": "phone-abc123"}
    ).json()["ok"]
    state = device.get("/api/v1/chat/state").json()
    assert state["messages"][-1] == {
        "id": msg_id,
        "author": "Ana",
        "author_id": "phone-abc123",
        "text": "let him in",
        "thumbs": 1,
    }
    # the operator sees the scores; the audience doesn't
    assert client.get("/api/v1/run").json()["window"]["options"][0]["total"] > 0
    assert "variables" not in state and "scores" not in state["messages"][-1]
    # devices still can't reach the operator's controls
    assert device.post("/api/v1/run/control", json={"action": "skip"}).status_code == 403


def test_chat_rate_limit_and_validation(client):
    start(client)
    device = phone(client)
    body = {"participant": "phone-abc123", "name": "Ana", "text": "hi"}
    assert device.post("/api/v1/chat/messages", json=body).status_code == 201
    assert device.post("/api/v1/chat/messages", json=body).status_code == 429
    time.sleep(0.45)
    assert device.post("/api/v1/chat/messages", json=body).status_code == 201
    assert (
        device.post("/api/v1/chat/messages", json={**body, "participant": "x"}).status_code == 400
    )
    assert device.post("/api/v1/chat/messages", json={**body, "text": "x" * 300}).status_code == 422


def test_chat_when_nothing_is_running(client):
    assert phone(client).get("/api/v1/chat/state").json()["active"] is False
    r = phone(client).post(
        "/api/v1/chat/messages", json={"participant": "phone-abc123", "name": "A", "text": "hi"}
    )
    assert r.status_code == 409


def test_chat_view_drops_hidden_messages():
    snap = {
        "active": True,
        "epoch": 1,
        "version": 2,
        "messages": [
            {
                "id": "m1",
                "author": "a",
                "text": "x",
                "thumbs": 0,
                "hidden": True,
                "scores": {"o": 1},
            }
        ],
    }
    assert chat_view(snap)["messages"] == []


def test_lan_info_and_qr(tmp_path, monkeypatch):
    with make_client(tmp_path, monkeypatch) as c:
        info = c.get("/api/v1/lan").json()
        assert info["listening"] is False and "start-story-lan.bat" in info["hint"]
        assert c.get("/api/v1/lan/qr.svg").status_code == 404
    monkeypatch.setattr("story_app.live_api.lan_addresses", lambda: ["192.168.1.10"])
    with make_client(tmp_path / "b", monkeypatch, lan=True) as c:
        info = c.get("/api/v1/lan").json()
        assert info["urls"] == ["http://192.168.1.10:8777/#/chat"]
        qr = c.get("/api/v1/lan/qr.svg")
        assert qr.headers["content-type"] == "image/svg+xml" and b"<svg" in qr.content


def test_tune_control(client):
    start(client)
    r = client.post(
        "/api/v1/run/control",
        json={"action": "tune", "thumbs_up_factor": 2.5, "match_threshold": 0.5},
    ).json()
    assert r["ok"] and r["tuning"] == {"thumbs_up_factor": 2.5, "match_threshold": 0.5}


def test_ai_backend_answers_in_the_background(tmp_path, monkeypatch):
    backend = ScriptedBackend()

    async def choose():
        return backend, "Scripted (test)"

    with make_client(tmp_path, monkeypatch, choose_ai=choose) as c:
        start(c)
        assert c.get("/api/v1/run").json()["ai"] == {
            "enabled": True,
            "label": "Scripted",
            "pending": None,
            "reason": "Scripted (test)",
        }
        skip_to(c, "influence")
        c.post("/api/v1/run/messages", json={"author": "ana", "text": "Biscuit the Brave"})
        c.post("/api/v1/run/control", json={"action": "close_window"})
        deadline = time.time() + 5
        while time.time() < deadline:
            snap = c.get("/api/v1/run").json()
            if snap["line"] and snap["line"]["source"] == "ai":
                break
            time.sleep(0.05)
        assert snap["variables"]["dog_name"] == "Biscuit the Brave"
        assert snap["line"]["text"] == "A line the AI wrote." and snap["line"]["source"] == "ai"
        assert len(backend.calls) == 2


def test_ai_settings_and_status(client, monkeypatch):
    s = client.get("/api/v1/settings/ai").json()
    assert s["backend"] == "auto" and s["ollama_model"] == "llama3.2:3b"
    s["backend"] = "none"
    assert client.put("/api/v1/settings/ai", json=s).json()["backend"] == "none"

    async def fake_check_all(settings):
        return [
            Availability(backend="ollama", label="Ollama (local)", ok=False, detail="not running")
        ]

    monkeypatch.setattr("story_app.api.check_all", fake_check_all)
    status = client.get("/api/v1/ai/status").json()
    assert status["backends"][0]["ok"] is False and status["reason"] == "AI is off in tests."
    assert client.post("/api/v1/ai/test").json() == {"ok": False, "detail": "AI is off in tests."}
    assert client.get("/api/v1/matching/status").json()["matcher"] == "word overlap"
