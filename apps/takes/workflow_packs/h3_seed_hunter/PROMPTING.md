# MiniMax H3 prompting guide (for agents)

How to turn a plain request ("make her wave and say hi, happy tone, portrait") into
the `prompt` input of an H3 stage. Sources:
- the H3 Prompt IDE schema (`ComfyUI-H3-Prompt-IDE/web/h3_prompt_schema_core.mjs`);
- the Fantastic H3 Prompt Builder README;
- the prompts that worked in this pack's stage tests.

Rules marked **exact** are checked by those tools. Tips are working habits.

## 1. Pick the format from the stage

The first line of the prompt depends on the stage's frame mode. Copy it **exactly**.
`D` is the duration you set, with two decimals (see section 5).

| Stage | Format | First line |
|---|---|---|
| `*_first` | I2VA | `For the target video, at 0.00 seconds into the target video, <Picture 1> (from [Shot 1]) is fully referenced.` |
| `*_last` | L2VA | `How the reference pictures align with the target video — <Picture 1> (from [Shot N]) aligns with the D-second mark of the target video.` |
| `*_firstlast` | FL2VA | `How the reference pictures align with the target video — Picture 1 (from Shot 1) aligns with the 0.00-second mark of the target video; Picture 2 (from Shot N) aligns with the D-second mark of the target video.` |
| `video_extend_*` | T2VA | none: start directly with `integrated_multimodal_description:` |
| `voice_takes` | built for you | no prompt; set `line`, `tone` and `length_s` (section 7) |

`N` is the shot the frame belongs to: usually 1, or the last shot if there are cuts.
FL2VA writes `Picture 1` / `Shot 1` **without** angle brackets; I2VA and L2VA use them.

## 2. Body template

After the first line and a blank line, use these three sections **in this order,
each exactly once** (exact):

```text
<first line from the table, if any>

integrated_multimodal_description: [Shot 1] <style sentence>. <who is on screen and what they look like>. <what happens, in order>. <camera>. In a <voice description> (S1), with <pacing>, she says: <d>[English] Exact words here.</d> <lip-sync and gesture timing>.

overall_soundscape:
<diegetic sound: room tone, footsteps, wind, crowd>

non_diegetic_music:
N/A
```

- `non_diegetic_music` is music that isn't in the scene (score). `N/A` when there is
  none. Describe genre, tempo and mood when there is.
- `overall_soundscape` is everything else you hear. Don't leave it empty. For
  `*_audio` stages, describe what the forced audio contains, such as "a woman speaking
  clearly, quiet room".

## 3. Turning a request into the description

Work through the request in this order and write one sentence (or a few) for each:

1. **Style:** medium and look, e.g. "Expressive hand-drawn 2D animation, clean
   white background." Keep it the same across a project so takes match.
2. **Subject:** who is in `<Picture 1>`. Restate the details that must stay fixed
   (hair, eyes, outfit, markings, proportions) and add "Keep her face, outfit and
   proportions consistent."
3. **Action beats:** what happens, in time order, as concrete verbs: "notices the
   viewer, eyebrows lift, raises her right hand, two quick waves". Include the
   secondary motion that sells it: "sleeve bounces", "hair swings". One clear idea
   per clip works better than a list of unrelated actions.
4. **Camera:** framing and movement, e.g. "full-body, static camera" or "slow
   push-in to a medium close-up". If the user says nothing, choose a static
   camera matching the reference framing.
5. **Speech** (if any): see section 4.
6. **Ending:** where things settle on the last frame, e.g. "She finishes facing the
   viewer, smiling." For `*_last` and `*_firstlast`, describe the motion arriving at
   that picture.

Reference every media file you loaded by its token, and don't load files you
never mention: unmentioned media still affects the result and costs time. With
`pack refs`, tokens follow the order you pass the files: `--picture` gives
`<Picture 1>`, `<Picture 2>`; then `--video`; then `--audio`.

## 4. Dialogue and voice

- Spoken words go inside `<d>…</d>` and start with a language marker:
  `<d>[English] Hi there!</d>` (exact). Other markers include `[Spanish]`,
  `[Japanese]`, `[French]` and `[German]`. Tags are **case-sensitive**: `<d>` and `</d>`.
- Give each speaker an ID and introduce the voice once: `In a bright, warm feminine
  voice (S1), with natural conversational pacing, she says: <d>[English] …</d>`. A
  second speaker is `(S2)`.
- Then tie gestures to phrases. Your working prompts did this, and it improves lip
  sync: "Synchronize her mouth clearly with every word. On 'Hi!' she waves; on 'my
  name is…' she touches her chest."
- **Voice-over** (speaker off screen): say so, and that on-screen lips stay closed.
- **Interrupted speech:** put `<|cutoff|>` where the line is cut off, inside the
  `<d>` span (exact).
- **Singing:** wrap lyrics in `<|lyrics_start|>` … `<|lyrics_end|>` (balanced, exact).
- **`*_audio` stages:** the forced audio is the exact soundtrack. Write the same words
  in `<d>` that the audio says, and set the duration to the audio's length.
- Match the duration to the speech. About 2.5–3 spoken words per second, plus
  pauses and gestures, is a reasonable start (estimate).

## 5. Durations

H3 makes 17n+5 frames at 24 fps, and the workflow rounds your seconds **up** to the
next valid count. Use these values for `duration_s` and in the L2VA/FL2VA first
line, so the stated end time matches the real video:

| Seconds | 5.17 | 5.88 | 6.58 | 7.29 | 8.00 | 8.71 | 9.42 | 10.13 | 10.83 | 11.54 | 12.25 | 12.96 | 13.67 | 14.38 | 15 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Frames | 124 | 141 | 158 | 175 | 192 | 209 | 226 | 243 | 260 | 277 | 294 | 311 | 328 | 345 | 362 |

The trained range is about 5–15 s. For an extension, `duration_s` is the new part only.

## 6. Several shots (cuts)

- `[Shot 1]` has no timestamp. Every later shot starts with an exact timestamp:
  `[Shot 2] At 00:03.000, close-up on her hands…` (exact `At MM:SS.mmm,`). Numbers
  go up by one, and times must increase and stay inside the duration.
- Most clips here are one shot. Only add cuts when the request asks for them.
- Keep each shot as one flowing passage. The prompt tools treat stray line breaks as
  cuts, so don't start a new line with something that reads like a new shot.

## 7. Stage notes

- **`video_extend_*`:** start the description with "Continue seamlessly from the
  previous scene." and restate the identity details to preserve. Then describe only
  what happens next. `<Video 1>` is the clip being continued.
- **Scene chains (`video_extend_upscale_native`, one part per run):** each part
  continues the one before it. Measured on 2026-10-28; see the
  [extend + upscale validation](../../docs/h3-extend-upscale-validation-2026-10-28.md).
  - **Length:** keep `duration_s` at 8.00 on a 12 GB GPU. A longer part ran out of
    VRAM in the upscale pass.
  - **New footage:** each part adds `duration_s` minus the overlap. With 8.00 s and
    56 frames that's 5.67 s, and the line, the action and a beat after it must all fit.
  - **Dialogue:** plan at most one short line per part, about 10 spoken words. Lines
    of 15–16 words plus action got cut off. Split long speeches at a natural pause,
    and give silent action (walking off, getting up) its own part.
  - **Endings:** end each part on a finished line and a held pose, so the next part
    starts cleanly instead of mid-word.
  - **Props:** restate their current state in every part ("the cigarette in his right
    hand, the only one"). A chain produced a second cigarette.
  - **Identity:** add the character picture as `<Picture 1>` in every part and use
    the reference format (section 8) with `video continuation + reference
    generation`. Without it, one face drifted off-model.
  - **Camera:** a single described camera move worked well, e.g. "the camera swings
    around to the left, rotating to lead in front of her in a smooth tracking shot".
  - **Voices:** native audio picks a new voice each part. For a consistent voice,
    plan voice-cloned lines instead (`voice_takes`, then a `*_audio` stage).
- **`video_upscale_*` and `take`:** to upscale a 3-take result, reuse the exact
  same prompt, references, duration, size and seed, and set `take`. Any change
  creates a different video.
- **`voice_takes`:** no prompt; the workflow wraps your inputs in its own template.
  - `line`: just the words, no tags. Write pauses and emphasis as words ("Hmm…",
    "long pause").
  - `tone`: one sentence starting "her tone is …" / "his tone is …", e.g. "her tone
    is playful and kind, and she stresses the word 'enjoy'".
  - `length_s`: close to the spoken length; too long makes the voice babble.
  - Voice file: 15–45 s of clean speech from the person.

## 8. Reference format (advanced)

Use this when references play roles other than a first or last frame: a character
from several pictures, a style picture, or a voice-timbre clip. The H3 reference
format (Ref2VA) replaces the three sections with six, in this order (exact):

```text
subject_definitions:
<Subject 1> is the woman in <Picture 1>, with short black hair and a green jacket.
<Audio 1> is the voice-timbre reference for <Subject 1> (S1).

summary:
[reference generation + audio reference] One sentence about the scene.

retention_analysis:
<Picture 1>: fully_preserved - her face and outfit.
<Audio 1>: reference - its vocal timbre guides her delivery without copying the signal.

detailed_description:
One or two style sentences. [Shot 1] What happens, with <d>[English] …</d> speech.

overall_soundscape:
…

non_diegetic_music:
N/A
```

- `summary` starts with task types in this order: `video editing` or `video
  continuation`, then `keyframe completion`, then `reference generation`, then
  `audio reference` or `audio reuse`, joined with ` + ` (exact). A first or last
  frame counts as `keyframe completion`.
- Every `<Subject n>`, `<Picture n>`, `<Video n>` and `<Audio n>` you use is defined
  once in `subject_definitions` and has a `retention_analysis` row.
  - Picture markers: `fully_preserved`, `partially_preserved`, `attribute_transfer`,
    `weak_reference`.
  - Audio markers: `fully_copy`, `partially_copy`, `reference`, `weak_reference`.
- Don't add a first-line alignment to this format.
- Tested on 2026-10-28 with `video_extend_upscale_native`: summary
  `[video continuation + reference generation]`, `<Picture 1>: partially_preserved -
  the character designs … only, not its framing`, and `<Video 1>: fully_preserved -
  continue its scene … from its last frame`. `fully_preserved` is not a documented
  video marker, but it worked. Other combinations are untested.

## 9. Worked example (completed run, 2026-10-25)

Request: "the character notices the viewer, smiles, gives one small friendly wave
and says 'Hi! This is a test.' in a cheerful voice. Static camera, soft room tone,
no music." Stage `video_1take_native_first`, `9:16 (Portrait Widescreen)`, 5.17 s,
default seed, a full-body 2D cartoon character on white as `<Picture 1>` (`.webp`).
It finished in about 3 minutes and made one 480×864, 124-frame mp4 with audio.

```text
For the target video, at 0.00 seconds into the target video, <Picture 1> (from [Shot 1]) is fully referenced.

integrated_multimodal_description: [Shot 1] Expressive hand-drawn 2D cartoon animation with bold clean black outlines and flat cel shading, plain white background. The character from <Picture 1> stands full-body facing the viewer: long, messy dark purple hair with stray strands, rectangular glasses, sleepy half-lidded eyes with dark under-eye circles, a long open white lab coat with rolled-up sleeves over a white shirt and purple turtleneck, high-waisted black pants, black shoes, and white bandages wrapped around both forearms and the left hand. Keep the face, hair, outfit, bandages and proportions consistent. The character notices the viewer, eyebrows lift and the tired eyes open a little wider, then breaks into a warm smile, raises the right hand to shoulder height and gives one small friendly wave, the coat sleeve and loose hair strands swaying gently. Static camera, full-body framing matching the reference. In a bright, cheerful voice (S1), with light, natural pacing, the character says: <d>[English] Hi! This is a test.</d> Synchronize the mouth clearly with every word. On "Hi!" the single wave happens; on "This is a test." the hand lowers back to the side. The character finishes facing the viewer, smiling.

overall_soundscape:
Simple soft room tone: a quiet indoor space with a faint, even ambience. No other sounds.

non_diegetic_music:
N/A
```

What made it work:
- The whole description is one line, so the prompt tools don't read a stray line
  break as a cut.
- Identity details are written out from the picture, followed by the "Keep … consistent" sentence.
- There is one action beat (notice → smile → one wave), and it is tied to the
  speech: the wave on "Hi!", the hand lowering on the rest.
- The hand is named from the character's side ("the right hand"), and the
  free hand was chosen over the bandaged one.
- No voice gender was given. "the character" with "a bright, cheerful voice (S1)"
  lets the model pick the voice.
- Five spoken words fit easily in the shortest table length, 5.17 s.
- The user's "no music" became `N/A`, and the soundscape was still filled in.

## 10. Checklist before submit

- [ ] First line matches the stage (or is absent for extend).
- [ ] The three sections are present, in order, each once.
- [ ] Every loaded file is mentioned by its token, and every token has a file.
- [ ] Each speech span is `<d>[Language] …</d>`, with speaker IDs like `(S1)`.
- [ ] Duration comes from the table and matches any `D` in the first line, and the
      audio length on `*_audio` stages.
- [ ] Later shots carry `At MM:SS.mmm,` timestamps inside the duration.
- [ ] For an upscale of a take: identical inputs to the 3-take run, plus `take`.
- [ ] For a scene chain: each part's speech and action fit its new footage
      (section 7), and props are restated.
