# Legacy migration

The current Godot project is still maintained in Chess Studio at
`games/pawn-slug-godot`. Import its tracked files, including binary artwork,
as one reviewed snapshot rather than reconstructing the game from partial
file copies.

From a clean Pawn Action clone, with a local Chess Studio clone available:

```sh
git -C ../chess-studio fetch origin main
git -C ../chess-studio rev-parse origin/main
# Replace SOURCE_SHA with the reviewed full commit SHA from the previous command.
python3 scripts/import_legacy_game.py ../chess-studio SOURCE_SHA
git status --short
```

The importer preserves the project path, verifies each Git blob and executable
mode, refuses existing destinations and prints the source commit/tree IDs.
It does not commit, push, change the legacy repository or publish any assets.
Record the printed IDs in the import PR. Git LFS pointers, if present, remain
tracked pointers and must be resolved before runtime acceptance.

Follow-up gates (not fulfilled by importing):
- Inventory dependencies outside the Godot tree, including asset build and
  validation scripts, R2 manifests and export/smoke tooling.
- Run the Godot headless tests and Web export/smoke with the required assets.
- Visually review Matthias's weapon animations, controls and stage traversal.
- Retain legacy publishing and launcher until the replacement is accepted.
  Infrastructure and identity remain owned by ShadowOps Infra.

Do not delete the existing playable source or repoint production in the import PR.
