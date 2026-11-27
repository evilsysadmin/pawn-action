#!/usr/bin/env python3
"""Import the complete tracked Godot tree from a local Chess Studio clone."""
import argparse
import hashlib
import io
from pathlib import Path, PurePosixPath
import subprocess
import tarfile
import tempfile

LEGACY = "games/pawn-slug-godot"


def git(repo, *args):
    return subprocess.check_output(["git", "-C", str(repo), *args])


def import_game(source, ref, destination):
    if destination.exists() or destination.is_symlink():
        raise ValueError(f"Destination already exists: {destination}")
    commit = git(source, "rev-parse", "--verify", f"{ref}^{{commit}}").decode().strip()
    tree = git(source, "rev-parse", f"{commit}:{LEGACY}").decode().strip()
    algorithm = git(source, "rev-parse", "--show-object-format").decode().strip()
    expected = {}
    for row in git(source, "ls-tree", "-rz", tree).split(b"\0"):
        if not row:
            continue
        meta, name = row.split(b"\t", 1)
        mode, kind, oid = meta.decode().split()
        path = PurePosixPath(name.decode())
        if kind != "blob" or mode not in ("100644", "100755") or path.is_absolute() or ".." in path.parts:
            raise ValueError(f"Unsupported tree entry: {path}")
        expected[str(path)] = (mode, oid)
    if "project.godot" not in expected:
        raise ValueError("Source is missing project.godot")
    archive = git(source, "archive", "--format=tar", tree)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=destination.parent) as temp:
        staged = Path(temp) / "game"
        staged.mkdir()
        seen = set()
        with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
            for member in tar:
                if member.isdir():
                    continue
                if not member.isfile() or member.name not in expected or member.name in seen:
                    raise ValueError(f"Unexpected archive member: {member.name}")
                data = tar.extractfile(member).read()
                mode, oid = expected[member.name]
                header = f"blob {len(data)}\0".encode()
                if hashlib.new(algorithm, header + data).hexdigest() != oid:
                    raise ValueError(f"Blob mismatch: {member.name}")
                target = staged / member.name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
                target.chmod(0o755 if mode == "100755" else 0o644)
                seen.add(member.name)
        if seen != expected.keys():
            raise ValueError("Archive does not contain every tracked file")
        if destination.exists() or destination.is_symlink():
            raise ValueError(f"Destination already exists: {destination}")
        staged.rename(destination)
    return commit, tree, len(expected)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="Local Chess Studio clone")
    parser.add_argument("ref", help="Explicit source commit or ref")
    args = parser.parse_args()
    destination = Path(__file__).resolve().parents[1] / LEGACY
    try:
        commit, tree, count = import_game(args.source, args.ref, destination)
    except (ValueError, OSError, subprocess.CalledProcessError) as exc:
        parser.exit(1, f"Import failed: {exc}\n")
    print(f"Imported {count} verified files from commit {commit}, tree {tree}")
    print("Review and commit the imported files in a separate PR; no deployment was performed.")


if __name__ == "__main__":
    main()
