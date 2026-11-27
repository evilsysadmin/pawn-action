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

This is the independent ShadowOps `evilsysadmin/pawn-action` repository. Respect the existing game, asset and delivery contracts; do not move game implementation back into Chess Studio.

## GitHub account routing (mandatory)

- For any operations on `evilsysadmin/*` repositories (reads, writes, PRs, checks, merges, and workflows), explicitly select the GitHub connection **ShadowOps** (profile `evilsysadmin`). If a tool exposes `link_id`, select the **current session's** ID corresponding to `link_name: ShadowOps`; never rely on the default when multiple connections are available.
- **Nullforge** (profile `nullforgeops`) is a separate account connection. Never use it for ShadowOps repositories or as a silent fallback. If ShadowOps fails, diagnose the explicit account selection before declaring GitHub disconnected.
- Verify the repository owner/name, PR head and CI before acting. Do not commit a `link_id`, token, or credentials; IDs can change after reconnection.

## Change discipline

- Keep changes small and reviewed through PRs. Do not treat successful tests as proof of a real staging deploy.
- Preserve source ownership, game rules and existing integration boundaries; infrastructure, DNS, Pages, protected Identity, and associated credentials belong to `evilsysadmin/shadowops-infra`.
