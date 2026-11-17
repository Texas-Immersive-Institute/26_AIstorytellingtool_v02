# H3 Seed Hunter stage pack

API-format recipes for the MiniMax H3 Seed Hunter v2.5 workflow. They come from your
stage exports in ComfyUI (`user/default/workflows/agent_workflows_nonAPI/`), converted
with `app.ue_modified_prompt()` in the 8188 frontend because the built-in Export (API)
button fails on Use Everywhere links. The last-frame, first + last frame and
forced-audio variants switch those node groups in a copy of your export before
converting. Prompts, dialogue lines, tone text and reference files are stripped.
Agents supply them per run.

`pack.json` lists each stage, what it does, and its inputs, bound to node inputs.
[PROMPTING.md](PROMPTING.md) shows agents how to turn a plain request into an H3 prompt
for each stage.
Takes reads this folder directly and sends the filled-in recipes to ComfyUI itself
(`takes_app/pack.py`, ADR-0006 in this repo). This copy was taken from
`comfyui_apitool/workflow_packs/h3_seed_hunter` at commit `addce38` (2026-11-13); when the
pack changes there, copy it over again. Don't edit recipes by hand; re-convert from the UI
workflow when it changes.

## Stages

| Stage ids | What it does | Time |
|---|---|---|
| `voice_takes` | 3 mp3 takes of one line in a cloned voice | about 2–5 min |
| `video_1take_{native,audio}_{first,last,firstlast}` | 1 video at 0.4 MP, 24 fps | about 2–5 min |
| `video_3takes_{native,audio}_{first,last,firstlast}` | 3 takes on seeds s, s+1000, s+2000 | about 3× one take |
| `video_upscale_{native,audio}_{first,last,firstlast}` | 1 take → ~2 MP → RIFE 48 fps, one run | about 12 min |
| `video_extend_{native,audio}` | continue `<Video 1>` and stitch the new part on | about 2–5 min |
| `video_extend_upscale_native` | continue `<Video 1>`, upscale only the new part to ~2 MP, RIFE 48 fps; saves the new part alone (join it after `<Video 1>`); overlap editable (5, 22, 39 or 56 frames) | about 10 min for 8 s |

- `native`: H3 makes the soundtrack. `audio`: `<Audio 1>` is forced in as the exact
  soundtrack (lip sync).
- `first`: `<Picture 1>` is the first frame.
- `last`: `<Picture 1>` is the last frame. These recipes are rewired from your
  first + last export so the last-frame guide reads `<Picture 1>`, as H3's L2VA format
  expects.
- `firstlast`: `<Picture 1>` is the first frame and `<Picture 2>` is the last frame.

Your original exports are the `*_native_first`, `video_1take_audio_first`,
`video_3takes_audio_first`, `video_upscale_native_first`, `video_extend_native` and
`voice_takes` stages. The others were generated and have not been run yet, except
`video_extend_upscale_native`: `scripts/build_extend_upscale_recipe.py` derives it from
the extend and upscale exports (the UI has no extend + upscale combination). Re-run
the script after re-converting either one.

## What can change

| Editable | Locked (shown read-only in the UI) |
|---|---|
| prompt, reference media, duration, video size (aspect ratio), seed, LoRAs, take (1-take and upscale stages) | stage 1 megapixels 0.4, steps 6, sampler `er_sde`, scheduler `beta`, reference image size `max` |
| voice file + clip start/length, line, tone, spoken length, seed, vocal LoRAs | voice quality 2, audio steps 16, audio scheduler |
| | upscale 2 MP / 2 steps / denoise 0.4 / seed, RIFE 48 fps, extension overlap 22 frames, output names |

## Rules

- One upscale per run. To upscale take k of a 3-take run, use an upscale stage with
  the same inputs and seed, and set `take` to k.
- Extended clips can't be upscaled. Upscale each part on its own, then combine them.
- With your audio, set the duration to the audio's length.
