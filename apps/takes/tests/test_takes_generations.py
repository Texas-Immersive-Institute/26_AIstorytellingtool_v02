"""Projects, shots and takes through the API, rendered by a stand-in ComfyUI."""

import json
import time

import pytest
from fastapi.testclient import TestClient
from takes_app.api import create_app
from takes_app.pack import Pack
from takes_app.settings import AppSettings
from takes_app.stages import GenerateRequest
from takes_app.store import ProjectStore, Take

PACK = Pack()


def node_input(workflow, name, stage="video_1take_native_first"):
    param = PACK.stage(stage).param(name)
    return workflow[param.node_id]["inputs"][param.input_name]


async def six_point_two(_path):
    return 6.2  # what ffprobe would say a sound file lasts


RETIMED: list[tuple[str, str]] = []


async def fake_retime(src, dest):
    """Stands in for ffmpeg's 24 fps copy."""
    RETIMED.append((src.name, dest.name))
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(b"24 fps copy")


@pytest.fixture
def projects(tmp_path):
    return tmp_path / "projects"


def make_client(fake_comfy, projects_dir):
    settings = AppSettings(projects_dir=str(projects_dir) if projects_dir else None)
    app = create_app(
        settings,
        transport=fake_comfy.transport,
        poll_s=0.01,
        probe=six_point_two,
        retime=fake_retime,
    )
    return TestClient(app)


@pytest.fixture
def client(fake_comfy, projects):
    with make_client(fake_comfy, projects) as c:
        yield c


@pytest.fixture
def shot(client):
    """(slug, shot id) of a fresh project with one shot."""
    slug = client.post("/api/projects", json={"title": "Lighthouse"}).json()["slug"]
    shot_id = client.post(f"/api/projects/{slug}/shots", json={"title": "Lamp"}).json()["id"]
    return slug, shot_id


def upload(client, slug, name="ref.png", data=b"png bytes"):
    res = client.post(f"/api/projects/{slug}/media", files={"file": (name, data)})
    assert res.status_code == 201, res.text
    return res.json()["id"]


def generate(client, slug, shot_id, **body):
    res = client.post(f"/api/projects/{slug}/shots/{shot_id}/takes", json={"prompt": "p", **body})
    assert res.status_code == 202, res.text
    return res.json()["id"]


def project(client, slug):
    return client.get(f"/api/projects/{slug}").json()["project"]


def take_of(client, slug, take_id):
    for s in project(client, slug)["shots"]:
        for t in s["takes"]:
            if t["id"] == take_id:
                return s, t
    raise AssertionError(f"no take {take_id}")


def wait_for(client, slug, take_id, statuses=("done", "failed", "cancelled"), timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        _, take = take_of(client, slug, take_id)
        if take["status"] in statuses:
            return take
        time.sleep(0.02)
    raise AssertionError(f"take stuck at {take['status']}")


# -- first start and projects ------------------------------------------------------------------


def test_projects_folder_is_chosen_on_first_start(fake_comfy, projects):
    with make_client(fake_comfy, None) as client:
        res = client.get("/api/projects")
        assert res.status_code == 409 and res.json()["code"] == "setup_required"
        assert "AI Takes Projects" in client.get("/api/settings").json()["suggested_projects_dir"]
        assert (
            client.put("/api/settings", json={"projects_dir": "relative/path"}).status_code == 400
        )
        res = client.put("/api/settings", json={"projects_dir": str(projects)})
        assert res.json()["projects_dir"] == str(projects) and projects.is_dir()
        assert client.get("/api/projects").json() == []


def test_shots_can_be_added_renamed_reordered_and_deleted(client):
    slug = client.post("/api/projects", json={"title": "Night Watch"}).json()["slug"]
    assert slug == "night-watch"
    add = lambda **b: client.post(f"/api/projects/{slug}/shots", json=b).json()  # noqa: E731
    a, c = add(title="Arrival"), add()
    assert c["title"] == "Shot 2"
    b = add(title="Storm", after=a["id"])
    order = lambda: [s["title"] for s in project(client, slug)["shots"]]  # noqa: E731
    assert order() == ["Arrival", "Storm", "Shot 2"]

    client.patch(f"/api/projects/{slug}/shots/{c['id']}", json={"title": "Dawn", "notes": "wide"})
    bad = client.put(f"/api/projects/{slug}/shot-order", json={"shots": [a["id"]]})
    assert bad.status_code == 400
    client.put(f"/api/projects/{slug}/shot-order", json={"shots": [c["id"], a["id"], b["id"]]})
    assert order() == ["Dawn", "Arrival", "Storm"]

    assert client.delete(f"/api/projects/{slug}/shots/{b['id']}").status_code == 204
    assert order() == ["Dawn", "Arrival"]
    summary = client.get("/api/projects").json()
    assert summary[0]["title"] == "Night Watch" and summary[0]["shot_count"] == 2


def test_unknown_project_and_media_are_refused(client, shot):
    assert client.get("/api/projects/nope").status_code == 404
    slug, shot_id = shot
    res = client.post(
        f"/api/projects/{slug}/shots/{shot_id}/takes", json={"prompt": "p", "pictures": ["x"]}
    )
    assert res.status_code == 404 and "upload it to this project first" in res.json()["detail"]
    bad = client.post(f"/api/projects/{slug}/media", files={"file": ("notes.txt", b"hi")})
    assert bad.status_code == 400


# -- takes -------------------------------------------------------------------------------------


def test_a_take_renders_into_the_project_and_becomes_selected(client, shot, fake_comfy, projects):
    slug, shot_id = shot
    pic = upload(client, slug)
    take_id = generate(
        client,
        slug,
        shot_id,
        prompt="A keeper lights the lamp.",
        pictures=[pic],
        duration_s=5.17,
        seed=7,
    )
    take = wait_for(client, slug, take_id)
    assert take["status"] == "done", take
    assert take["stage"] == "video_1take_native_first" and take["seed"] == 7
    assert take["duration_s"] == 5.17

    assert fake_comfy.uploads == [(pic, "minimax_h3")]
    workflow = fake_comfy.prompts[take["prompt_id"]]
    assert node_input(workflow, "prompt") == "A keeper lights the lamp."
    assert node_input(workflow, "seed") == 7
    assert node_input(workflow, "output_final") == f"h3/{take_id}/final"

    # the files are copied into the project, the final video is the take, and it now plays
    folder = projects / slug / "takes" / take_id
    assert sorted(p.name for p in folder.iterdir()) == [
        "final_00001-audio.mp4",
        "preview_00001.mp4",
    ]
    assert [f["name"] for f in take["files"] if f["main"]] == ["final_00001-audio.mp4"]
    shot_now, _ = take_of(client, slug, take_id)
    assert shot_now["selected_take"] == take_id
    video = client.get(f"/api/projects/{slug}/takes/{take_id}/video")
    assert video.content == f"bytes of h3/{take_id}/final_00001-audio.mp4".encode()


def test_a_second_take_does_not_replace_the_selection_until_chosen(client, shot):
    slug, shot_id = shot
    pic = upload(client, slug)
    first = generate(client, slug, shot_id, pictures=[pic])
    second = generate(client, slug, shot_id, pictures=[pic])
    wait_for(client, slug, first)
    wait_for(client, slug, second)
    assert take_of(client, slug, second)[0]["selected_take"] == first
    assert (
        client.post(f"/api/projects/{slug}/takes/{second}/select").json()["selected_take"] == second
    )


def test_upscale_this_take_reuses_its_seed_and_becomes_selected(client, shot, fake_comfy):
    slug, shot_id = shot
    pic = upload(client, slug)
    source = wait_for(client, slug, generate(client, slug, shot_id, pictures=[pic]))
    res = client.post(f"/api/projects/{slug}/takes/{source['id']}/upscale")
    assert res.status_code == 202, res.text
    up = wait_for(client, slug, res.json()["id"])
    assert up["status"] == "done" and up["upscaled"] is True
    assert up["stage"] == "video_upscale_native_first" and up["source_take"] == source["id"]
    workflow = fake_comfy.prompts[up["prompt_id"]]
    assert node_input(workflow, "seed", up["stage"]) == source["seed"]
    assert node_input(workflow, "take", up["stage"]) == "a"  # take 1 = the seed itself
    assert take_of(client, slug, up["id"])[0]["selected_take"] == up["id"]
    again = client.post(f"/api/projects/{slug}/takes/{up['id']}/upscale")
    assert again.status_code == 409


def test_a_voice_reference_is_spoken_first_then_animated_to(client, shot, fake_comfy, projects):
    slug, shot_id = shot
    pic, voice = upload(client, slug), upload(client, slug, "mara.wav", b"wav")
    take_id = generate(
        client, slug, shot_id, audio="voice", pictures=[pic],
        voice={"clip": voice, "line": "The lamp is out.", "tone": "her tone is worried"},
    )  # fmt: skip
    take = wait_for(client, slug, take_id)
    assert take["status"] == "done", take
    assert take["stage"] == "video_1take_audio_first"
    assert fake_comfy.log == ["queue p1", "done p1", "queue p2", "done p2"]

    voice_wf = fake_comfy.prompts["p1"]
    assert node_input(voice_wf, "line", "voice_takes") == "The lamp is out."
    assert node_input(voice_wf, "tone", "voice_takes") == "her tone is worried"
    assert node_input(voice_wf, "voice_ref_file", "voice_takes") == f"minimax_h3/{voice}"
    assert node_input(voice_wf, "seed", "voice_takes") == take["seed"]

    # take 1 of the spoken line is kept in the project and forced in as <Audio 1>
    assert take["voice_audio"] == f"{take_id}-voice-take1_00001.mp3"
    assert (projects / slug / "media" / take["voice_audio"]).is_file()
    refs = json.loads(node_input(fake_comfy.prompts["p2"], "references", take["stage"]))
    assert [(r["kind"], r["name"]) for r in refs] == [
        ("picture", pic),
        ("audio", take["voice_audio"]),
    ]
    # the length comes from the spoken line (6.2 s here), rounded up to an H3 length
    assert take["duration_s"] == 6.58
    assert node_input(fake_comfy.prompts["p2"], "duration_s", take["stage"]) == 6.58

    up = wait_for(
        client, slug, client.post(f"/api/projects/{slug}/takes/{take_id}/upscale").json()["id"]
    )
    assert up["stage"] == "video_upscale_audio_first"
    assert up["request"]["audio"] == "clip" and up["request"]["audio_clip"] == take["voice_audio"]
    assert len(fake_comfy.prompts) == 3  # the line was not spoken again


def test_your_clip_sets_the_length(client, shot, fake_comfy):
    slug, shot_id = shot
    pic, clip = upload(client, slug), upload(client, slug, "line.mp3", b"mp3")
    take = wait_for(
        client, slug, generate(client, slug, shot_id, audio="clip", pictures=[pic], audio_clip=clip)
    )
    assert take["stage"] == "video_1take_audio_first" and take["duration_s"] == 6.58


def test_no_picture_runs_on_the_prompt_alone(client, shot, fake_comfy):
    slug, shot_id = shot
    take = wait_for(client, slug, generate(client, slug, shot_id, frames="none", seed=3))
    assert take["status"] == "done", take
    assert take["stage"] == "video_1take_native_none"
    assert fake_comfy.uploads == []
    workflow = fake_comfy.prompts[take["prompt_id"]]
    assert json.loads(node_input(workflow, "references", take["stage"])) == []
    assert not any(n["class_type"] == "MiniMaxH3AddGuide" for n in workflow.values())

    up = wait_for(
        client, slug, client.post(f"/api/projects/{slug}/takes/{take['id']}/upscale").json()["id"]
    )
    assert up["status"] == "done" and up["stage"] == "video_upscale_native_none"
    assert node_input(fake_comfy.prompts[up["prompt_id"]], "seed", up["stage"]) == 3

    clip = upload(client, slug, "line.mp3", b"mp3")
    voiced = wait_for(
        client, slug, generate(client, slug, shot_id, frames="none", audio="clip", audio_clip=clip)
    )
    assert voiced["stage"] == "video_1take_audio_none"
    refs = json.loads(
        node_input(fake_comfy.prompts[voiced["prompt_id"]], "references", voiced["stage"])
    )
    assert [r["kind"] for r in refs] == ["audio"]


def test_extend_makes_a_continuation_shot_that_plays_from_the_new_part(
    client, shot, fake_comfy, projects
):
    slug, shot_id = shot
    source = wait_for(
        client, slug, generate(client, slug, shot_id, pictures=[upload(client, slug)])
    )

    res = client.post(f"/api/projects/{slug}/takes/{source['id']}/extend")
    assert res.status_code == 201, res.text
    cont = res.json()
    assert cont["title"] == "Lamp (continued)" and cont["continues_take"] == source["id"]
    assert [s["id"] for s in project(client, slug)["shots"]] == [shot_id, cont["id"]]
    again = client.post(f"/api/projects/{slug}/takes/{source['id']}/extend").json()
    assert again["id"] == cont["id"]  # one continuation per take

    # a continuation shot's takes must say which take they continue, and take no pictures
    url = f"/api/projects/{slug}/shots/{cont['id']}/takes"
    assert client.post(url, json={"prompt": "p", "frames": "none"}).status_code == 400
    assert client.post(f"/api/projects/{slug}/shots/{shot_id}/takes", json={
        "prompt": "p", "frames": "none", "continues": source["id"]
    }).status_code == 400  # fmt: skip

    ext = wait_for(client, slug, generate(
        client, slug, cont["id"], frames="none", continues=source["id"], duration_s=8.0
    ))  # fmt: skip
    assert ext["status"] == "done", ext
    assert ext["stage"] == "video_extend_native"
    assert fake_comfy.uploads[-1] == ("final_00001-audio.mp4", "minimax_h3")
    refs = json.loads(node_input(fake_comfy.prompts[ext["prompt_id"]], "references", ext["stage"]))
    assert [r["kind"] for r in refs] == ["video"]
    # the stitched result plays from where the new part starts: the continued take's length
    assert ext["play_from_s"] == 6.2 and ext["duration_s"] == 6.2
    assert take_of(client, slug, ext["id"])[0]["selected_take"] == ext["id"]

    # upscaling an extension renders the new part only, on the same seed, and plays it whole
    up = wait_for(
        client, slug, client.post(f"/api/projects/{slug}/takes/{ext['id']}/upscale").json()["id"]
    )
    assert up["status"] == "done" and up["stage"] == "video_extend_upscale_native"
    assert up["play_from_s"] is None and up["seed"] == ext["seed"]
    assert take_of(client, slug, up["id"])[0]["selected_take"] == up["id"]
    assert RETIMED == []

    # extending an upscaled (48 fps) take sends H3 a 24 fps copy, removed afterwards
    cont2 = client.post(f"/api/projects/{slug}/takes/{up['id']}/extend").json()
    ext2 = wait_for(client, slug, generate(
        client, slug, cont2["id"], frames="none", continues=up["id"]
    ))  # fmt: skip
    assert ext2["status"] == "done", ext2
    assert RETIMED[-1] == ("final_00001-audio.mp4", "continued-24fps.mp4")
    assert fake_comfy.uploads[-1] == ("continued-24fps.mp4", "minimax_h3")
    assert not (projects / slug / "takes" / ext2["id"] / "continued-24fps.mp4").exists()
    order = [s["id"] for s in project(client, slug)["shots"]]
    assert order == [shot_id, cont["id"], cont2["id"]]

    # what a continuation depends on can't be deleted from under it
    assert client.delete(f"/api/projects/{slug}/takes/{source['id']}").status_code == 409
    assert client.delete(f"/api/projects/{slug}/shots/{shot_id}").status_code == 409
    assert client.delete(f"/api/projects/{slug}/shots/{cont2['id']}").status_code == 204


def test_extensions_with_your_audio_are_not_upscaled(client, shot):
    slug, shot_id = shot
    source = wait_for(client, slug, generate(client, slug, shot_id, frames="none"))
    cont = client.post(f"/api/projects/{slug}/takes/{source['id']}/extend").json()
    clip = upload(client, slug, "line.mp3", b"mp3")
    ext = wait_for(client, slug, generate(
        client, slug, cont["id"], frames="none", continues=source["id"], audio="clip",
        audio_clip=clip,
    ))  # fmt: skip
    assert ext["stage"] == "video_extend_audio" and ext["duration_s"] == 6.2
    res = client.post(f"/api/projects/{slug}/takes/{ext['id']}/upscale")
    assert res.status_code == 409 and "native audio only" in res.json()["detail"]


def test_a_failed_run_reports_the_node_error(client, shot, fake_comfy):
    slug, shot_id = shot
    fake_comfy.fail_next = "CUDA out of memory"
    take = wait_for(client, slug, generate(client, slug, shot_id, pictures=[upload(client, slug)]))
    assert take["status"] == "failed" and take["error"] == "KSampler failed: CUDA out of memory"
    assert take_of(client, slug, take["id"])[0]["selected_take"] is None


def test_a_refused_workflow_reports_why(client, shot, fake_comfy):
    slug, shot_id = shot
    fake_comfy.node_errors = {
        "365": {"class_type": "H3PromptIDE", "errors": [{"message": "Value not in list"}]}
    }
    take = wait_for(client, slug, generate(client, slug, shot_id, pictures=[upload(client, slug)]))
    assert (
        take["status"] == "failed" and "node 365 (H3PromptIDE): Value not in list" in take["error"]
    )


def test_comfyui_not_running_fails_with_the_reason(client, shot, fake_comfy):
    slug, shot_id = shot
    pic = upload(client, slug)
    fake_comfy.running = False
    take = wait_for(client, slug, generate(client, slug, shot_id, pictures=[pic]))
    assert take["status"] == "failed" and "isn't running" in take["error"]


def test_cancel_a_rendering_take(client, shot, fake_comfy):
    slug, shot_id = shot
    fake_comfy.polls_to_finish = 10_000
    take_id = generate(client, slug, shot_id, pictures=[upload(client, slug)])
    wait_for(client, slug, take_id, statuses=("rendering",))
    assert client.delete(f"/api/projects/{slug}/takes/{take_id}").status_code == 409
    assert client.delete(f"/api/projects/{slug}/shots/{shot_id}").status_code == 409
    client.post(f"/api/projects/{slug}/takes/{take_id}/cancel")
    assert wait_for(client, slug, take_id)["status"] == "cancelled"
    assert "interrupt" in fake_comfy.log


def test_cancel_a_waiting_take_never_reaches_comfyui(client, shot, fake_comfy):
    slug, shot_id = shot
    fake_comfy.polls_to_finish = 30
    pic = upload(client, slug)
    first, second = (
        generate(client, slug, shot_id, pictures=[pic]),
        generate(client, slug, shot_id, pictures=[pic]),
    )
    assert (
        client.post(f"/api/projects/{slug}/takes/{second}/cancel").json()["status"] == "cancelled"
    )
    wait_for(client, slug, first)
    assert fake_comfy.log == ["queue p1", "done p1"]


def test_deleting_the_selected_take_falls_back_to_the_newest_finished_one(client, shot, projects):
    slug, shot_id = shot
    pic = upload(client, slug)
    first = wait_for(client, slug, generate(client, slug, shot_id, pictures=[pic]))["id"]
    second = wait_for(client, slug, generate(client, slug, shot_id, pictures=[pic]))["id"]
    assert client.delete(f"/api/projects/{slug}/takes/{first}").status_code == 204
    assert not (projects / slug / "takes" / first).exists()
    assert take_of(client, slug, second)[0]["selected_take"] == second


def test_takes_left_unfinished_are_picked_up_on_the_next_start(fake_comfy, projects):
    store = ProjectStore(projects)
    slug = store.create("Resume")
    project = store.load(slug)
    from takes_app.store import Shot

    project.shots.append(shot := Shot(title="One"))
    request = GenerateRequest(prompt="p", pictures=["m.png"])
    (projects / slug / "media").mkdir(parents=True, exist_ok=True)
    (projects / slug / "media" / "m.png").write_bytes(b"png")
    # one take was rendering in ComfyUI when Takes closed, one was still waiting
    fake_comfy.prompts["p9"] = {}
    fake_comfy.state["p9"] = {"polls": 0, "fail": None, "done": False, "removed": False}
    rendering = Take(
        request=request, stage=request.stage, status="rendering", prompt_id="p9", seed=5
    )
    waiting = Take(request=request, stage=request.stage, status="queued")
    shot.takes += [rendering, waiting]
    store.save(slug)

    with make_client(fake_comfy, projects) as client:
        assert wait_for(client, slug, rendering.id)["status"] == "done"
        assert wait_for(client, slug, waiting.id)["status"] == "done"
        assert fake_comfy.log == ["done p9", "queue p2", "done p2"]  # p9 was not queued again


def test_comfyui_status_and_address(client):
    assert client.get("/api/comfyui").json()["ready"] is True
    assert client.put("/api/settings", json={"comfyui_url": "ftp://x"}).status_code == 400
    res = client.put("/api/settings", json={"comfyui_url": "http://192.168.1.20:8188/"})
    assert res.json()["comfyui_url"] == "http://192.168.1.20:8188"
    assert client.get("/api/comfyui").json()["manual"] is True
    assert client.put("/api/settings", json={"comfyui_url": ""}).json()["comfyui_url"] is None


def test_serves_the_built_ui_beside_the_api(fake_comfy, projects, tmp_path, monkeypatch):
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<title>Takes</title>", encoding="utf-8")
    monkeypatch.setenv("TAKES_WEB_DIST", str(dist))
    with make_client(fake_comfy, projects) as c:
        assert "<title>Takes</title>" in c.get("/").text
        assert c.get("/api/health").json()["service"] == "takes"
        assert c.get("/api/projects").json() == []
