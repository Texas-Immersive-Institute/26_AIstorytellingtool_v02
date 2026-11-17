# Takes

Turns prompts, images and audio into generated videos with ComfyUI, then lets you choose and play back the ones you like in order.

## Language

**Shot**:
One slot in a sequence: an intended moment of the film that one or more takes compete to fill.
_Avoid_: clip, slot, job

**Take**:
One generated video belonging to a shot.
_Avoid_: output, result, render, artifact

**Voice reference**:
A recorded voice clip, plus the line to say, that Takes turns into the shot's soundtrack in the voice of the clip before animating the shot to it.
_Avoid_: voice take, voice clone, audio take

**Selected take**:
The single take that plays for its shot in the sequence.
_Avoid_: final, pick, circled take

**Upscaled take**:
A higher-quality re-render of another take in the same shot; it becomes the shot's selected take when it arrives and is marked as upscaled.
_Avoid_: derived take, final, HD version

**Continuation shot**:
A shot that carries on from the end of the shot before it, made by extending that shot's selected take.
_Avoid_: extension, part

**Sequence**:
The ordered list of shots, played back as their selected takes one after another.
_Avoid_: playlist, reel, timeline, queue
