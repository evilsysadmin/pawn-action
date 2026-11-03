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

## R2 publisher ownership (pre-cutover)

The **runtime compatibility IDs remain legacy** (`pawn-slug-godot` bridge event,
`PAWN_SLUG_STAGE`, atlas logical IDs and existing sprite URLs). The **new Web
release namespace is separate**:

| Owner | Release objects | Mutable pointer |
| --- | --- | --- |
| Chess Studio (legacy rollback) | `pawn-slug-godot/releases/` | `pawn-slug-godot/current.json` |
| Pawn Action (new standalone) | `pawn-action/releases/` | `pawn-action/current.json` |

`scripts/pawn_slug_godot_bundle.py` checks and constructs immutable bundles
without credentials in dry-run mode:

```sh
python3 -S scripts/pawn_slug_godot_bundle.py self-test
python3 -S scripts/pawn_slug_godot_bundle.py check
python3 -S scripts/pawn_slug_godot_bundle.py publish --dry-run
```

The `publish` command rejects all prefixes except exactly `pawn-action`,
including `pawn-slug-godot`. Actual writes additionally require
`--confirm-publish`; this is **not** an authorization to run it during the
migration. The default R2 configuration is still copied from Chess Studio
and points at its **shared bucket**, so an independently owned/authorized
destination, credentials, release retention protection (including the live
Chess Studio cleanup policy), browser/visual approval, and rollback must be
confirmed before any live upload. No CI workflow publishes to R2.

An existing `pawn-action/current.json` must validate before being updated.
Only a verified remote 404 is accepted as an absent pointer: 403, 500,
network errors and malformed JSON stop publication. This does not implement
distributed compare-and-swap; ensure that only **one** designated publisher
can write the Pawn Action pointer, and never enable both repositories to
publish the legacy pointer.

## Visual review before migration merge

The Godot/Web CI artifact includes SHA-bound desktop, animation-closeup,
movement and touch contact sheets under `review/`. These are real Chromium
screenshots but **not visual approval**: compare them against an approved,
provenance-bound Chess Studio baseline before moving extraction PR #1 out
of Draft. See [visual migration review](docs/visual-migration-review.md).
