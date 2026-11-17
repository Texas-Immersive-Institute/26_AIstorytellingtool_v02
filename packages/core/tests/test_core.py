from pathlib import Path

from aistory_core.access import is_lan, is_loopback
from aistory_core.paths import app_data_dir
from aistory_core.settings_file import load_model, save_model
from pydantic import BaseModel


class Sample(BaseModel):
    name: str = "x"
    count: int = 0


def test_loopback_and_lan():
    assert is_loopback("127.0.0.1")
    assert is_loopback("::1")
    assert not is_loopback("192.168.1.20")
    assert is_lan("192.168.1.20")
    assert is_lan("10.0.0.5")
    assert not is_lan("127.0.0.1")
    assert not is_lan("8.8.8.8")
    assert not is_lan(None)
    assert not is_lan("not-an-ip")


def test_app_data_dir_override(tmp_path, monkeypatch):
    monkeypatch.setenv("AISTORY_DATA_DIR", str(tmp_path))
    assert app_data_dir("story") == tmp_path / "story"
    assert (tmp_path / "story").is_dir()


def test_settings_roundtrip(tmp_path: Path):
    path = tmp_path / "config.json"
    assert load_model(path, Sample) == Sample()
    save_model(path, Sample(name="y", count=3))
    assert load_model(path, Sample) == Sample(name="y", count=3)
    assert not list(tmp_path.glob(".config.json.*"))


def test_ui_page_is_checked_again_on_every_load(tmp_path):
    from aistory_core.web_ui import UIFiles
    from starlette.applications import Starlette
    from starlette.testclient import TestClient

    (tmp_path / "index.html").write_text("<html></html>")
    (tmp_path / "app-1a2b.js").write_text("x")
    app = Starlette()
    app.mount("/", UIFiles(tmp_path))
    client = TestClient(app)
    assert client.get("/").headers["cache-control"] == "no-cache"
    assert "cache-control" not in client.get("/app-1a2b.js").headers
