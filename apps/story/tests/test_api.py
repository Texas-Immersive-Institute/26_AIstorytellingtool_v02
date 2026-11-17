import pytest
from conftest import EXAMPLE, no_ai
from fastapi.testclient import TestClient
from story_app.api import create_app
from story_app.settings import AppSettings


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("STORY_EXAMPLES_DIR", str(EXAMPLE.parent))
    monkeypatch.setenv("STORY_WEB_DIST", str(tmp_path / "no-dist"))
    app = create_app(AppSettings(), embeddings=None, choose_ai=no_ai)
    # TestClient's default peer is "testclient"; act as the host computer.
    return TestClient(app, client=("127.0.0.1", 50000), base_url="http://127.0.0.1:8777")


def test_setup_required_then_projects(client, tmp_path):
    r = client.get("/api/v1/projects")
    assert r.status_code == 409 and r.json()["code"] == "setup_required"
    assert client.get("/api/v1/settings").json()["projects_dir"] is None
    assert client.put("/api/v1/settings", json={"projects_dir": "relative"}).status_code == 400
    folder = tmp_path / "Stories"
    r = client.put("/api/v1/settings", json={"projects_dir": str(folder)})
    assert r.status_code == 200 and folder.is_dir()
    assert client.get("/api/v1/projects").json() == []


def test_project_lifecycle(client, tmp_path):
    client.put("/api/v1/settings", json={"projects_dir": str(tmp_path / "p")})
    examples = client.get("/api/v1/examples").json()
    assert [e["name"] for e in examples] == ["lighthouse"]
    slug = client.post("/api/v1/examples/lighthouse/copy").json()["slug"]
    got = client.get(f"/api/v1/projects/{slug}").json()
    assert got["story"]["title"] == "The Lighthouse Keeper" and got["issues"] == []
    story = got["story"]
    story["scenes"][0]["exit"]["choice"]["options"][0]["goes_to"] = "nowhere"
    saved = client.put(f"/api/v1/projects/{slug}", json=story).json()
    assert any("unknown scene 'nowhere'" in i["message"] for i in saved["issues"])
    assert client.put(f"/api/v1/projects/{slug}", json={"title": 3}).status_code == 422
    up = client.post(
        f"/api/v1/projects/{slug}/assets", files={"file": ("bg.png", b"png", "image/png")}
    )
    assert up.status_code == 201 and up.json()["path"] == "assets/bg.png"
    assert client.get(f"/api/v1/projects/{slug}/files/assets/bg.png").content == b"png"
    escape = client.get(f"/api/v1/projects/{slug}/files/assets/%2E%2E/story.json")
    assert escape.status_code in {400, 404}
    z = client.get(f"/api/v1/projects/{slug}/export")
    assert z.headers["content-type"] == "application/zip"
    imported = client.post("/api/v1/projects/import", files={"file": ("x.zip", z.content)})
    assert imported.status_code == 201
    assert len(client.get("/api/v1/projects").json()) == 2


def test_lan_devices_get_chat_only(client):
    lan = TestClient(client.app, client=("192.168.1.50", 1), base_url="http://192.168.1.10")
    assert lan.get("/api/v1/whoami").json() == {"is_host": False}
    assert lan.get("/api/v1/settings").status_code == 403
    assert lan.get("/api/v1/projects").status_code == 403
    assert client.get("/api/v1/whoami").json() == {"is_host": True}


def test_rejects_public_peers_and_foreign_origins(client):
    outsider = TestClient(client.app, client=("8.8.8.8", 1), base_url="http://192.168.1.10")
    assert outsider.get("/api/v1/health").status_code == 403
    r = client.get("/api/v1/settings", headers={"Origin": "http://evil.example"})
    assert r.status_code == 403
    r = client.get("/api/v1/settings", headers={"Origin": "http://127.0.0.1:5174"})
    assert r.status_code == 200
    rebinding = TestClient(client.app, client=("127.0.0.1", 1), base_url="http://evil.example")
    assert rebinding.get("/api/v1/health").status_code == 400
