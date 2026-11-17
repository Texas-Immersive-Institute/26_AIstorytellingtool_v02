# Story

Authors a branching narrative outline and runs it with a live or simulated audience whose chat shapes the path, the dialogue and what the story remembers. Built to teach how audience-driven generative stories work.

## Outline

**Story project**:
Everything needed to reopen a story on another computer: outline, characters, assets and saved playthroughs. It grows as you work.
_Avoid_: save file, story file

**Scene**:
One box on the story graph; scenes are joined by paths, and branches may rejoin a later scene.
_Avoid_: passage, node, chapter

**Beat**:
One step inside a scene, holding what is seen, heard and said at that moment; an empty picture or audio slot can hold over from the beat before.
_Avoid_: shot, step, node, clip

**Hold**:
A beat's picture or audio slot set to keep whatever the beat before it had.
_Avoid_: reuse, carry-over, inherit

**Split**:
The point inside a scene where it divides into stacked lanes; exactly one lane plays, then the scene continues.
_Avoid_: branch, fork

**Lane**:
One of several stacked alternative runs of beats inside a scene, picked by an in-scene choice point or a story variable; lanes rejoin before the scene ends.
_Avoid_: track, branch, sub-path

**Choice point**:
A moment where the story pauses and the audience's chat decides which authored option, and so which path, comes next.
_Avoid_: vote, decision node, fork

**AI line**:
A line of dialogue the AI writes during a playthrough from an authored intent, with an authored default line to play instead when the AI is not used.
_Avoid_: generated line, dynamic line

**Default line**:
The authored line that stands in for an AI line.
_Avoid_: fallback, placeholder

**Influence window**:
A moment inside a scene where audience chat is ranked and the strongest messages become material for the next AI-written dialogue, without changing the path.
_Avoid_: chat window, prompt window

## Characters and memory

**Base profile**:
A character's authored description: personality, motivations, speaking style, what they know or hide. It never changes during a playthrough.
_Avoid_: character sheet, bio

**Story variable**:
A named value defined in the outline that choices and the audience can change, and that later scenes can read to vary what plays.
_Avoid_: flag, stat, state

**Live profile**:
Notes the AI adds about a character during a playthrough, kept beside the base profile and cleared for the next playthrough.
_Avoid_: dynamic profile, character memory

**Story memory**:
Free-form notes recorded during a playthrough (running jokes, established backstory, what the audience latched onto), mostly by the AI, and read when writing later dialogue. The outline can seed it and the operator can edit it.
_Avoid_: canon, lore, history

## Running

**Playthrough**:
One run of the story from start to finish, saved with its chat, scores, AI outputs, path and changes to variables and memory. It never changes the outline.
_Avoid_: session, performance, run

**Outline-only playthrough**:
A playthrough with the AI switched off, so every AI line plays its default line; used to check a story's structure.
_Avoid_: dry run, test mode

**Audience**:
The people (or the operator posing as them) sending chat messages during a playthrough.
_Avoid_: users, players, viewers

**Operator**:
The person running a playthrough from the host computer's Debug view.
_Avoid_: host, admin, teacher, GM

**Match score**:
How closely a message's meaning fits a choice-point option or an influence window's intent.
_Avoid_: similarity, relevance

**Weight**:
How much a message counts: its match score boosted by its thumbs-ups.
_Avoid_: votes, score

**Thumbs-up**:
An audience member's endorsement of someone else's message, which adds weight to that message.
_Avoid_: upvote, like

**Stage view**:
What the room watches, shown from the host computer: the story's pictures, dialogue and audio in visual-novel style.

**Chat view**:
What each audience member opens on their own device over the LAN to send messages and thumbs-ups.

**Debug view**:
The operator's view on the host computer of why the story is doing what it does: scores, weights, variables, memory and AI calls, with controls to steer the playthrough.
_Avoid_: admin panel, backend
