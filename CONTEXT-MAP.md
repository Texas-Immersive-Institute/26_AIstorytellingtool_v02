# Context Map

## Contexts

- [Takes](./apps/takes/CONTEXT.md): generates video takes with the H3 ComfyUI and assembles chosen takes into a sequence
- [Story](./apps/story/CONTEXT.md): authors and runs audience-influenced branching narratives

## Relationships

- **Story → Takes** (planned): a story scene may request a shot from Takes; the merge design is not yet decided
- **Takes ↔ Story**: share a core package for media assets and the AI client (`packages/core`, planned)
