# AGENTS.md — Pawn Action

This is the independent ShadowOps `evilsysadmin/pawn-action` repository. Respect the existing game, asset and delivery contracts; do not move game implementation back into Chess Studio.

## GitHub account routing (mandatory)

- For any operations on `evilsysadmin/*` repositories (reads, writes, PRs, checks, merges, and workflows), explicitly select the GitHub connection **ShadowOps** (profile `evilsysadmin`). If a tool exposes `link_id`, select the **current session's** ID corresponding to `link_name: ShadowOps`; never rely on the default when multiple connections are available.
- **Nullforge** (profile `nullforgeops`) is a separate account connection. Never use it for ShadowOps repositories or as a silent fallback. If ShadowOps fails, diagnose the explicit account selection before declaring GitHub disconnected.
- Verify the repository owner/name, PR head and CI before acting. Do not commit a `link_id`, token, or credentials; IDs can change after reconnection.

## Change discipline

- Keep changes small and reviewed through PRs. Do not treat successful tests as proof of a real staging deploy.
- Preserve source ownership, game rules and existing integration boundaries; infrastructure, DNS, Pages, protected Identity, and associated credentials belong to `evilsysadmin/shadowops-infra`.
