import json

import pytest
from pydantic import ValidationError
from takes_app.comfyui import check, outputs_of, run_error
from takes_app.pack import Pack, PackError
from takes_app.stages import (
    ASPECT_RATIOS,
    GenerateRequest,
    estimate_spoken_s,
    fit_duration,
    stage_for,
)

PIC = {"kind": "picture", "name": "a.png", "subfolder": "minimax_h3"}


@pytest.fixture(scope="module")
def pack():
    return Pack()


def test_toggles_pick_the_stage(pack):
    assert stage_for("first", "native", False) == "video_1take_native_first"
    assert stage_for("last", "clip", False) == "video_1take_audio_last"
    assert stage_for("firstlast", "native", True) == "video_upscale_native_firstlast"
    # every toggle combination exists in the pack
    assert stage_for("none", "native", False) == "video_1take_native_none"
    for frames in ("none", "first", "last", "firstlast"):
        for audio in ("native", "clip"):
            for upscale in (False, True):
                pack.stage(stage_for(frames, audio, upscale))


def test_request_checks_inputs_against_toggles():
    GenerateRequest(prompt="p", pictures=["a"])
    GenerateRequest(prompt="p", frames="firstlast", pictures=["a", "b"])
    assert GenerateRequest(prompt="p", frames="none").stage == "video_1take_native_none"
    with pytest.raises(ValidationError, match="uses no pictures"):
        GenerateRequest(prompt="p", frames="none", pictures=["a"])
    with pytest.raises(ValidationError, match="first and a last frame"):
        GenerateRequest(prompt="p", frames="firstlast", pictures=["a"])
    with pytest.raises(ValidationError, match="audio clip"):
        GenerateRequest(prompt="p", audio="clip", pictures=["a"])
    with pytest.raises(ValidationError, match="video size"):
        GenerateRequest(prompt="p", pictures=["a"], aspect_ratio="5:4")
    with pytest.raises(ValidationError, match="voice reference"):
        GenerateRequest(prompt="p", audio="voice", pictures=["a"])
    voiced = GenerateRequest(
        prompt="p", audio="voice", pictures=["a"], voice={"clip": "v", "line": "Hi."}
    )
    assert voiced.stage == "video_1take_audio_first" and voiced.media_ids() == ["a", "v"]
    with pytest.raises(ValidationError, match="only used with 'voice reference'"):
        GenerateRequest(prompt="p", pictures=["a"], voice={"clip": "v", "line": "Hi."})


def test_lengths_snap_up_to_h3_lengths():
    assert fit_duration(2.0) == 5.17
    assert fit_duration(6.2) == 6.58
    assert fit_duration(8.0) == 8.0
    assert fit_duration(40) == 15.0
    assert estimate_spoken_s("The lamp is out.") == 2.08


def test_voice_stage_inputs_exist(pack):
    stage = pack.stage("voice_takes")
    for name in (
        "voice_ref_file",
        "line",
        "tone",
        "length_s",
        "seed",
        "voice_ref_start_s",
        "voice_ref_duration_s",
    ):
        stage.param(name)
    assert stage.param("voice_ref_file").upload_subfolder == "minimax_h3"


def test_pack_sizes_match_takes_options(pack):
    sizes = pack.stage("video_1take_native_first").param("aspect_ratio").enum_options
    assert tuple(sizes) == ASPECT_RATIOS


def test_filling_a_recipe_sets_bound_inputs_only(pack):
    stage = pack.stage("video_1take_native_first")
    wf = pack.fill(
        stage.id,
        {"prompt": "A keeper.", "references": [PIC], "duration_s": 5.17, "seed": 7},
        run_id="job1",
    )
    get = lambda name: wf[stage.param(name).node_id]["inputs"][stage.param(name).input_name]  # noqa: E731
    assert get("prompt") == "A keeper."
    assert get("duration_s") == 5.17
    assert get("seed") == 7
    assert get("output_final") == "h3/job1/final"  # {run_id} names this run's output folder
    assert get("take") == "a"  # value_map: take 1 renders on the seed itself
    state = json.loads(get("references"))
    assert state == [
        {
            "kind": "picture",
            "file": "minimax_h3/a.png [input]",
            "name": "a.png",
            "uid": "ref0",
            "has_audio": False,
            "audio_mode": "off",
        }
    ]
    # each fill starts from a fresh copy of the recipe
    again = pack.fill(stage.id, {"prompt": "x", "references": [PIC]}, run_id="j2")
    assert again[stage.param("prompt").node_id]["inputs"]["prompt"] == "x"
    assert get("prompt") == "A keeper."


def test_no_picture_stages_drop_the_frame_guide(pack):
    audio = {"kind": "audio", "name": "a.mp3"}
    for sid in [s for s in pack.stages if s.endswith("_none")]:
        sound = [] if "native" in sid else [audio]
        wf = pack.fill(sid, {"prompt": "p", "references": sound}, run_id="j")
        first_id = sid.removesuffix("_none") + "_first"
        first = pack.fill(first_id, {"prompt": "p", "references": [PIC, *sound]}, run_id="j")
        assert not any(n["class_type"] == "MiniMaxH3AddGuide" for n in wf.values())
        # the guide and the picture resize that only fed it are gone; nothing else changed
        assert sorted(set(first) - set(wf)) == ["272", "274", "276"], sid
        assert first["272"]["inputs"]["positive"] == ["459", 0]
        assert wf["125:14"]["inputs"]["conditioning"] == ["459", 0], sid
        assert all(_links_resolve(wf)), sid
    assert {s for s in pack.stages if s.endswith("_none")} >= {
        "video_1take_native_none",
        "video_1take_audio_none",
        "video_upscale_native_none",
        "video_upscale_audio_none",
    }
    with pytest.raises(PackError, match="Reference media"):  # the audio is still needed
        pack.fill("video_1take_audio_none", {"prompt": "p", "references": []}, run_id="j")


def _links_resolve(wf):
    for node in wf.values():
        for v in node["inputs"].values():
            if isinstance(v, list) and len(v) == 2 and isinstance(v[1], int):
                yield str(v[0]) in wf


def test_pack_refuses_bad_values(pack):
    with pytest.raises(PackError, match="Prompt"):
        pack.fill("video_1take_native_first", {"references": [PIC]}, run_id="j")
    with pytest.raises(PackError, match="needs 1 audio"):
        pack.fill("video_1take_audio_first", {"prompt": "p", "references": [PIC]}, run_id="j")
    with pytest.raises(PackError, match="fixed by the workflow pack"):
        pack.fill(
            "video_1take_native_first",
            {"prompt": "p", "references": [PIC], "steps": 30},
            run_id="j",
        )
    with pytest.raises(PackError, match="no stage"):
        pack.stage("video_9takes")


def test_history_parsing():
    ok = {
        "status": {"status_str": "success"},
        "outputs": {
            "1": {"gifs": [{"filename": "final.mp4", "subfolder": "h3/x", "type": "output"}]},
            "2": {"images": [{"filename": "t.png", "subfolder": "", "type": "temp"}]},
        },
    }
    assert [f["filename"] for f in outputs_of(ok)] == ["final.mp4"]
    assert run_error(ok) is None
    bad = {
        "status": {
            "status_str": "error",
            "messages": [
                ["execution_error", {"node_type": "VAEDecode", "exception_message": "OOM "}]
            ],
        }
    }
    assert run_error(bad) == "VAEDecode failed: OOM"


async def test_ready_when_the_h3_comfyui_answers(fake_comfy):
    status = await check(None, transport=fake_comfy.transport)
    assert status.ready and status.reachable and status.h3_nodes and not status.manual
    assert status.url == "http://127.0.0.1:8188"
    assert status.version == "0.3.99" and status.gpus == ["cuda:0 RTX"]


async def test_says_to_start_comfyui_when_nothing_answers(fake_comfy):
    fake_comfy.running = False
    status = await check(None, transport=fake_comfy.transport)
    assert not status.reachable and not status.ready
    assert "isn't running" in status.message


async def test_tells_another_comfyui_apart(fake_comfy):
    fake_comfy.h3_nodes = False
    status = await check(None, transport=fake_comfy.transport)
    assert status.reachable and not status.ready
    assert "H3 nodes" in status.message


async def test_manual_address(fake_comfy):
    status = await check("http://10.0.0.5:8190/", transport=fake_comfy.transport)
    assert status.manual and status.url == "http://10.0.0.5:8190" and status.ready
