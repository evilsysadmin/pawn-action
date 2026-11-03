# Pawn Action

**Pawn Action** is the standalone 2D run-and-gun game starring Matthias, built with Godot 4.

This repository is the new owner of the game previously developed as **Pawn Slug** inside [Chess Studio](https://github.com/evilsysadmin/chess-studio). The migration is incremental to avoid breaking the existing playable version.

## Ownership

- Godot 2D gameplay, campaign maps, enemy AI, animation and weapon systems live here.
- 2D sprite source, quality gates, Web export, release manifests and R2 publishing belong here.
- Chess Studio remains a launcher/link to the independent game once the new release is validated.
- Do not copy Chess Studio authentication, backend or unrelated UI into Pawn Action.

## Migration safety

The previous Web release and asset keys (including `pawn-slug-godot`) remain valid until a validated Pawn Action replacement is published and consumers have switched. Never delete source/CI from Chess Studio or repoint production before a headless Godot test, Web smoke, and visual acceptance have passed.

See [AGENTS.md](AGENTS.md) for repository instructions.
