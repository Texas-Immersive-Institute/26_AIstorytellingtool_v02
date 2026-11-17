import io
import zipfile

import pytest
from conftest import EXAMPLE
from story_app.store import NotFound, ProjectStore, StoreError, slugify


def test_create_list_load_save(tmp_path):
    store = ProjectStore(tmp_path)
    slug = store.create("My First Story!")
    assert slug == "my-first-story"
    assert store.create("My First Story!") == "my-first-story-2"
    story = store.load(slug)
    story.description = "edited"
    store.save(slug, story)
    assert store.load(slug).description == "edited"
    assert [p.slug for p in store.list()] == ["my-first-story", "my-first-story-2"]


def test_missing_project(tmp_path):
    with pytest.raises(NotFound):
        ProjectStore(tmp_path).load("nope")


@pytest.mark.parametrize("bad", ["..", "../x", "a/b", "a\\b", "C:x", ""])
def test_rejects_unsafe_project_names(tmp_path, bad):
    with pytest.raises(StoreError):
        ProjectStore(tmp_path).project_dir(bad)


def test_assets(tmp_path):
    store = ProjectStore(tmp_path)
    slug = store.create("s")
    a = store.add_asset(slug, "../../evil name.PNG", b"x")
    assert a.path == "assets/evil-name.png" and a.kind == "picture"
    b = store.add_asset(slug, "evil name.png", b"y")
    assert b.path == "assets/evil-name-2.png"
    assert store.asset_exists(slug, a.path)
    assert {x.path for x in store.list_assets(slug)} == {a.path, b.path}
    with pytest.raises(StoreError):
        store.add_asset(slug, "script.exe", b"x")
    for bad in ["../story.json", "assets/../story.json", "/etc/passwd", "story.json"]:
        with pytest.raises(StoreError):
            store.asset_file(slug, bad)


def test_copy_example_and_zip_roundtrip(tmp_path):
    store = ProjectStore(tmp_path / "projects")
    slug = store.copy_from(EXAMPLE)
    assert slug == "the-lighthouse-keeper"
    data = store.export_zip(slug)
    new_slug = store.import_zip(data)
    assert new_slug == "the-lighthouse-keeper-2"
    assert store.load(new_slug) == store.load(slug)
    assert store.asset_exists(new_slug, "assets/mara.svg")


def test_import_zip_skips_path_escapes(tmp_path):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("s/story.json", '{"title": "Zipped"}')
        zf.writestr("s/../../escaped.txt", "nope")
        zf.writestr("s/assets/ok.png", "png")
    store = ProjectStore(tmp_path / "projects")
    slug = store.import_zip(buf.getvalue())
    assert store.asset_exists(slug, "assets/ok.png")
    assert not (tmp_path / "escaped.txt").exists()
    assert not (tmp_path / "projects" / "escaped.txt").exists()


def test_import_rejects_non_zip(tmp_path):
    with pytest.raises(StoreError):
        ProjectStore(tmp_path).import_zip(b"not a zip")


def test_slugify():
    assert slugify("  Hello, World  ") == "hello-world"
    assert slugify("???") == "story"
