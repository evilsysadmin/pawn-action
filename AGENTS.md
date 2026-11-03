# AGENTS.md — Pawn Action

Pawn Action is a standalone **2D Godot** run-and-gun game, extracted from Chess Studio. It owns its gameplay, maps, sprites, Web export and future releases. Chess Studio must be treated only as a launcher, not as the owner of this code.

## Workflows
- Read `games/pawn-slug-godot/AGENTS.md`, `docs/pawnslug-sprites.md`, `skills/godot-spritesheets/SKILL.md` and `skills/pawn-slug-runtime-smoke/SKILL.md` before editing runtime or art.
- Godot owns gameplay, simulation, rendering, collisions, projectiles, weapon changes and animation; Web shell is only the host.
- **Pawn Action** is the product name. Keep legacy `pawn-slug-godot` paths, R2 keys, event source `pawn-slug-godot`, `PAWN_SLUG_STAGE`, logical asset IDs and source contracts during the migration unless every consumer and rollback path is migrated together.
- Sprite source is 2D. Preserve Matthias' canonical body scale across weapons. Failed visual gates fail closed. Attach real before/after PNG captures for visual PRs; no auto-merge before visual acceptance.
- PRs start Draft, CI red/pending must be fixed before Ready; use native auto-merge when available **only after all required gates and visual review**.
- Release to R2 only after validating Godot headless, Web export, browser input/bridge and visual evidence. Avoid auto-publishing shared Chess Studio R2 pointers before ownership handoff.
- Changes should be incremental, reversible, and avoid introducing Chess Studio frontend/backend, Football, Chronicles or other subsystems.
