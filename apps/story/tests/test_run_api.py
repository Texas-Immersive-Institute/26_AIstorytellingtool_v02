import pytest
from conftest import EXAMPLE, no_ai
from fastapi.testclient import TestClient
from story_app.api import create_app
from story_app.settings import AppSettings


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("STORY_EXAMPLES_DIR", str(EXAMPLE.parent))
    monkeypatch.setenv("STORY_WEB_DIST", str(tmp_path / "no-dist"))
    app = create_app(
        AppSettings(projects_dir=str(tmp_path / "projects")), embeddings=None, choose_ai=no_ai
    )
    with TestClient(app, client=("127.0.0.1", 50000), base_url="http://127.0.0.1:8777") as c:
        yield c


def copy_example(client) -> str:
    return client.post("/api/v1/examples/lighthouse/copy").json()["slug"]


def control(client, action, **kw):
    r = client.post("/api/v1/run/control", json={"action": action, **kw})
    assert r.status_code == 200, r.text
    return r.json()


def skip_to_window(client, kind):
    for _ in range(50):
        snap = client.get("/api/v1/run").json()
        if snap["window"] and snap["window"]["kind"] == kind:
            return snap
        control(client, "skip")
    raise AssertionError(f"no {kind} window")


def test_no_playthrough_yet(client):
    snap = client.get("/api/v1/run").json()
    assert snap["active"] is False and snap["version"] == 0 and snap["epoch"] > 0
    r = client.post("/api/v1/run/control", json={"action": "skip"})
    assert r.status_code == 409


def test_full_playthrough_over_http(client):
    slug = copy_example(client)
    snap = client.post(f"/api/v1/projects/{slug}/playthroughs", json={"mode": "live"}).json()
    assert snap["active"] and snap["scene"]["id"] == "storm" and snap["line"]["text"]
    pid = snap["playthrough_id"]

    skip_to_window(client, "influence")
    msg = client.post("/api/v1/run/messages", json={"author": "ana", "text": "Pickles"}).json()
    assert client.post(f"/api/v1/run/messages/{msg['id']}/thumbs", json={"voter": "ben"}).json()[
        "ok"
    ]
    control(client, "skip")
    assert client.get("/api/v1/run").json()["variables"]["dog_name"] == "Pickles"

    snap = skip_to_window(client, "choice")
    assert [o["id"] for o in snap["window"]["options"]] == ["storm_let_in", "storm_turn_away"]
    client.post("/api/v1/run/messages", json={"author": "ana", "text": "let him in"})
    snap = client.get("/api/v1/run").json()
    assert snap["window"]["options"][0]["total"] > 0
    control(client, "add_time", seconds=10)
    control(client, "close_window")
    assert client.get("/api/v1/run").json()["path"] == ["storm", "fire"]

    memory = client.post(
        "/api/v1/run/memory", json={"text": "The dog is called Pickles now."}
    ).json()
    assert client.patch(f"/api/v1/run/memory/{memory['id']}", json={"pinned": True}).json()["ok"]

    control(client, "pause")
    assert client.get("/api/v1/run").json()["status"] == "paused"
    control(client, "resume")

    for _ in range(80):
        snap = client.get("/api/v1/run").json()
        if snap["status"] == "ended":
            break
        if snap["window"] and snap["window"]["kind"] == "choice":
            control(client, "force_option", option_id=snap["window"]["options"][0]["id"])
        else:
            control(client, "skip")
    assert snap["status"] == "ended" and snap["path"][-1] == "dawn"

    saved = client.get(f"/api/v1/projects/{slug}/playthroughs").json()
    assert saved[0]["id"] == pid and saved[0]["ended"] and saved[0]["messages"] == 2
    record = client.get(f"/api/v1/projects/{slug}/playthroughs/{pid}").json()
    assert record["story"]["title"] == "The Lighthouse Keeper"
    assert record["final"]["variables"]["dog_name"] == "Pickles"
    assert any(e["type"] == "memory_added" for e in record["events"])


def test_refuses_to_start_a_story_with_errors(client):
    slug = copy_example(client)
    story = client.get(f"/api/v1/projects/{slug}").json()["story"]
    story["start_scene"] = "missing"
    client.put(f"/api/v1/projects/{slug}", json=story)
    r = client.post(f"/api/v1/projects/{slug}/playthroughs", json={})
    assert r.status_code == 400 and "Fix 1 error" in r.json()["detail"]


def test_stop_saves_and_lan_cannot_control(client):
    slug = copy_example(client)
    client.post(f"/api/v1/projects/{slug}/playthroughs", json={"mode": "outline_only"})
    lan = TestClient(client.app, client=("192.168.1.50", 1), base_url="http://192.168.1.10")
    assert lan.post("/api/v1/run/control", json={"action": "skip"}).status_code == 403
    assert lan.get("/api/v1/run").status_code == 403
    snap = client.post("/api/v1/run/stop").json()
    assert snap["status"] == "ended"
    saved = client.get(f"/api/v1/projects/{slug}/playthroughs").json()
    assert saved[0]["mode"] == "outline_only" and saved[0]["ended"]


def test_back_to_back_playthroughs_get_their_own_files(client):
    slug = copy_example(client)
    first = client.post(f"/api/v1/projects/{slug}/playthroughs", json={}).json()["playthrough_id"]
    second = client.post(f"/api/v1/projects/{slug}/playthroughs", json={}).json()["playthrough_id"]
    assert first != second
    assert {p["id"] for p in client.get(f"/api/v1/projects/{slug}/playthroughs").json()} == {
        first,
        second,
    }
