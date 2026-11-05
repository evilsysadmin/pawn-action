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
including `pawn-slug-godot`. Credential-less `check` and `publish --dry-run`
remain available. **Live writes fail closed** unless all these independent
conditions are met:

- `--confirm-publish` is supplied explicitly.
- `PAWN_ACTION_R2_PUBLISH_BUCKET` exactly matches the reviewed config's
  `bucket`; `PAWN_ACTION_R2_PUBLISH_DOMAIN` exactly matches its
  `customDomain` (hostname only, no `https://`).
- Dedicated `PAWN_ACTION_CLOUDFLARE_API_TOKEN` and
  `PAWN_ACTION_CLOUDFLARE_ACCOUNT_ID` are present in the **Pawn Action**
  publisher environment. Generic `CLOUDFLARE_API_TOKEN` and
  `CLOUDFLARE_ACCOUNT_ID` inherited from Chess Studio are **ignored**.

These are safeguards, **not** permission to cut over. The R2 configuration
is still copied from Chess Studio and points at the **shared bucket**.
**Live publication to that shared bucket or its public Chess Studio hostname
is now explicitly rejected, even if the operator provides matching approval
variables.** Dry-run and read-only verification remain available. The actual
protected staging delivery is owned by
[ShadowOps Infra](https://github.com/evilsysadmin/shadowops-infra), which
implements its own manual private-R2 admission/publisher. Neither repository
may repoint production or release on the strength of a CI-only review.
Any future independently owned release destination requires separate
least-privilege credentials, retention and rollback review, and explicit
browser/visual approval; `chess-studio-assets` is not an eligible direct
publish destination here. API-token scope and single-writer ownership
require external verification: matching environment variables prove neither.
No CI workflow in Pawn Action publishes to R2.

An existing `pawn-action/current.json` must validate before being updated.
Only a verified remote 404 is accepted as an absent pointer: 403, 500,
network errors and malformed JSON stop publication.

**New operator precondition (read-only first):**

```sh
# Uses dedicated Pawn Action credentials; does not publish or modify R2
python3 -S scripts/pawn_slug_godot_bundle.py inspect-current

# Copy the reported currentPointerSha256 (64 lowercase hex) or "absent".
# A missing or unreviewed value must fail before any Cloudflare write.
export EXPECTED_CURRENT_POINTER_SHA256='absent'  # example: *only* for verified first release
# This legacy direct publisher MUST NOT be run against the copied
# chess-studio-assets config. For staging, use shadowops-infra's guarded
# private-R2 admission after the visual/source approval gates instead.
# An isolated release workflow (if ever authorized) must still supply the
# reviewed expected-current-pointer-sha256 and its own single-writer control.
```

A live publication refuses a missing or stale expected fingerprint before
any write, and reads `current.json` **again immediately before updating**
it. If another publisher moved/repointed the pointer in between, publication
stops without overwriting the newer pointer (immutable release objects
already uploaded may remain for subsequent cleanup). A content-identical
release with a different `sourceSha` is still a distinct pointer update.

**This is not atomic distributed compare-and-swap.** The interval between
the final GET and PUT still requires **one designated pointer writer**.
The separate Cloudflare token scope, shared-bucket GC exclusion for
`pawn-action/`, retention and rollback must be verified externally.
No CI workflow publishes to R2; these protections are not permission to
cut over, and never permit writing the Chess Studio legacy pointer.

## Visual review before migration merge

The Godot/Web CI artifact includes SHA-bound desktop, animation-closeup,
movement and touch contact sheets under `review/`. These are real Chromium
screenshots but **not visual approval**: compare them against an approved,
provenance-bound Chess Studio baseline before moving extraction PR #1 out
of Draft. See [visual migration review](docs/visual-migration-review.md).
