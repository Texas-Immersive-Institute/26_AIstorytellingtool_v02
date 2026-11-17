"""Which H3 stages a take uses, from Takes' toggles (frame mode, audio, upscale).
Stage ids are the ones in workflow_packs/h3_seed_hunter/pack.json."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

Frames = Literal["first", "last", "firstlast"]
# native: the model makes the sound. clip: your audio file is the exact soundtrack (lip sync).
# voice: a voice reference; Takes first speaks the line in that voice, then animates to it.
Audio = Literal["native", "clip", "voice"]

VOICE_STAGE = "voice_takes"
ASPECT_RATIOS = (
    "1:1 (Square)",
    "2:3 (Portrait Photo)",
    "3:2 (Photo)",
    "3:4 (Portrait Standard)",
    "4:3 (Standard)",
    "9:16 (Portrait Widescreen)",
    "16:9 (Widescreen)",
    "21:9 (Ultrawide)",
)
DEFAULT_ASPECT = "9:16 (Portrait Widescreen)"
# H3 renders 17n+5 frames at 24 fps; these are the matching lengths (pack PROMPTING.md §5).
DURATIONS = (
    5.17,
    5.88,
    6.58,
    7.29,
    8.0,
    8.71,
    9.42,
    10.13,
    10.83,
    11.54,
    12.25,
    12.96,
    13.67,
    14.38,
    15.0,
)


def stage_for(frames: Frames, audio: Audio, upscale: bool) -> str:
    """The video stage. One take per generation (seed hunts are out of v1)."""
    takes = "upscale" if upscale else "1take"
    sound = "native" if audio == "native" else "audio"
    return f"video_{takes}_{sound}_{frames}"


def pictures_needed(frames: Frames) -> int:
    return 2 if frames == "firstlast" else 1


def fit_duration(seconds: float) -> float:
    """The shortest H3 length that holds `seconds` of sound (at least the trained 5.17 s)."""
    return next((d for d in DURATIONS if d >= seconds - 0.005), DURATIONS[-1])


def estimate_spoken_s(line: str) -> float:
    """About 2.7 spoken words a second plus a breath (a starting guess, PROMPTING.md §4)."""
    return min(15.0, max(1.0, round(len(line.split()) / 2.7 + 0.6, 2)))


class VoiceReference(BaseModel):
    """A recorded voice plus the line to say in it (glossary: Voice reference)."""

    clip: str  # media id of the recording; 15-45 s of clean speech works best
    line: str = Field(min_length=1)
    tone: str = ""  # e.g. "her tone is warm and amused"
    spoken_s: float | None = Field(default=None, ge=1, le=15)  # None = estimate from the line
    clip_start_s: float | None = Field(default=None, ge=0)
    clip_length_s: float | None = Field(default=None, ge=1, le=45)


class GenerateRequest(BaseModel):
    """One take for a shot. Media are ids returned by the project's media upload."""

    prompt: str = Field(min_length=1)
    frames: Frames = "first"
    audio: Audio = "native"
    upscale: bool = False
    # <Picture 1> is the first frame (or the last frame in "last" mode); with first+last,
    # <Picture 2> is the last frame.
    pictures: list[str] = Field(default_factory=list)
    audio_clip: str | None = None
    voice: VoiceReference | None = None
    # With your clip or a voice reference, Takes sets the length from the sound instead.
    duration_s: float = Field(default=6.58, ge=1, le=15)
    aspect_ratio: str = DEFAULT_ASPECT
    seed: int | None = Field(default=None, ge=0, le=1125899906842624)

    @model_validator(mode="after")
    def _inputs_match_toggles(self) -> GenerateRequest:
        need = pictures_needed(self.frames)
        if len(self.pictures) != need:
            which = "a first and a last frame" if need == 2 else "one picture"
            raise ValueError(f"This frame mode needs {which} ({len(self.pictures)} given)")
        if self.audio == "clip" and not self.audio_clip:
            raise ValueError("Choose the audio clip to animate to")
        if self.audio == "voice" and not self.voice:
            raise ValueError("Add the voice reference: a voice recording and the line to say")
        if self.audio != "clip" and self.audio_clip:
            raise ValueError("An audio clip is only used with 'your clip' audio")
        if self.audio != "voice" and self.voice:
            raise ValueError("A voice reference is only used with 'voice reference' audio")
        if self.aspect_ratio not in ASPECT_RATIOS:
            raise ValueError(f"Unknown video size {self.aspect_ratio!r}")
        return self

    @property
    def stage(self) -> str:
        return stage_for(self.frames, self.audio, self.upscale)

    def media_ids(self) -> list[str]:
        extra = [self.audio_clip] if self.audio_clip else []
        return [*self.pictures, *extra, *([self.voice.clip] if self.voice else [])]
