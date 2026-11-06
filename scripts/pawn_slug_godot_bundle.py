#!/usr/bin/env python3
"""Build metadata and publish a Godot Web export as one immutable R2 release."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import re
import sys
import tempfile
from typing import Any

import r2_asset_publish as transport

core = transport.core
ROOT = pathlib.Path(__file__).resolve().parents[1]
DEFAULT_BUILD_DIR = ROOT / "games/pawn-slug-godot/build/web"
DEFAULT_CONFIG = ROOT / "infra/cloudflare/r2-assets.json"
DEFAULT_PREFIX = "pawn-action"
LEGACY_PREFIX = "pawn-slug-godot"
POINTER_NAME = "current.json"
REQUIRED_FILES = {"index.html", "index.js", "index.wasm", "index.pck"}
RELEASE_RE = re.compile(r"^[0-9a-f]{16}$")
MIME_OVERRIDES = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".pck": "application/octet-stream",
    ".wasm": "application/wasm",
}


class BundleError(RuntimeError):
    pass


def _content_type(path: pathlib.Path) -> str:
    return MIME_OVERRIDES.get(path.suffix.lower(), core.content_type_for(path))


def _files(build_dir: pathlib.Path) -> list[pathlib.Path]:
    if not build_dir.is_dir():
        raise BundleError(f"No existe el export Godot Web: {build_dir}")
    files = sorted(path for path in build_dir.rglob("*") if path.is_file())
    if not files:
        raise BundleError(f"Export Godot Web vacío: {build_dir}")
    relative = {path.relative_to(build_dir).as_posix() for path in files}
    missing = sorted(REQUIRED_FILES - relative)
    if missing:
        raise BundleError(f"Export Godot incompleto; faltan: {', '.join(missing)}")
    if any(path.is_symlink() for path in files):
        raise BundleError("El export Godot no puede contener symlinks")
    return files


def _bundle_digest(build_dir: pathlib.Path, files: list[pathlib.Path]) -> str:
    digest = hashlib.sha256()
    for path in files:
        relative = path.relative_to(build_dir).as_posix()
        data_digest = core.sha256_file(path)
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(data_digest.encode("ascii"))
        digest.update(b"\0")
        digest.update(str(path.stat().st_size).encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def build_pointer(build_dir: pathlib.Path, base_url: str, prefix: str, source_sha: str = "") -> dict[str, Any]:
    files = _files(build_dir)
    digest = _bundle_digest(build_dir, files)
    release = digest[:16]
    release_prefix = f"{prefix.strip('/')}/releases/{release}"
    entries: dict[str, Any] = {}
    for path in files:
        relative = path.relative_to(build_dir).as_posix()
        key = f"{release_prefix}/{relative}"
        entries[relative] = {
            "bytes": path.stat().st_size,
            "contentType": _content_type(path),
            "key": key,
            "sha256": core.sha256_file(path),
            "url": f"{base_url.rstrip('/')}/{key}",
        }
    pointer = {
        "version": 1,
        "release": release,
        "sha256": digest,
        "sourceSha": source_sha if re.fullmatch(r"[0-9a-f]{7,64}", source_sha or "") else "",
        "index": entries["index.html"]["url"],
        "files": entries,
    }
    validate_pointer(pointer, base_url=base_url, prefix=prefix)
    return pointer


def validate_pointer(pointer: Any, *, base_url: str, prefix: str = DEFAULT_PREFIX) -> None:
    if not isinstance(pointer, dict) or pointer.get("version") != 1:
        raise BundleError("Pointer Godot inválido: version")
    release = pointer.get("release")
    digest = pointer.get("sha256")
    files = pointer.get("files")
    if not isinstance(release, str) or not RELEASE_RE.fullmatch(release):
        raise BundleError("Pointer Godot inválido: release")
    if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise BundleError("Pointer Godot inválido: sha256")
    if not isinstance(files, dict) or not REQUIRED_FILES.issubset(files):
        raise BundleError("Pointer Godot inválido: files")
    release_prefix = f"{prefix.strip('/')}/releases/{release}"
    expected_index = f"{base_url.rstrip('/')}/{release_prefix}/index.html"
    if pointer.get("index") != expected_index:
        raise BundleError("Pointer Godot inválido: index")
    for relative, entry in files.items():
        if not isinstance(relative, str) or relative.startswith("/") or ".." in pathlib.PurePosixPath(relative).parts:
            raise BundleError(f"Pointer Godot inválido: path {relative!r}")
        if not isinstance(entry, dict):
            raise BundleError(f"Pointer Godot inválido: entry {relative}")
        expected_key = f"{release_prefix}/{relative}"
        if entry.get("key") != expected_key or entry.get("url") != f"{base_url.rstrip('/')}/{expected_key}":
            raise BundleError(f"Pointer Godot inválido: URL/key {relative}")
        if not isinstance(entry.get("bytes"), int) or entry["bytes"] <= 0:
            raise BundleError(f"Pointer Godot inválido: bytes {relative}")
        if not re.fullmatch(r"[0-9a-f]{64}", str(entry.get("sha256", ""))):
            raise BundleError(f"Pointer Godot inválido: sha256 {relative}")


def _pointer_action(existing: dict[str, Any], desired: dict[str, Any]) -> str:
    if existing.get("sha256") != desired.get("sha256"):
        return "publish"
    if existing.get("sourceSha") != desired.get("sourceSha"):
        return "repoint"
    return "unchanged"


def _authorize_publish(prefix: str, *, dry_run: bool, confirmed: bool) -> None:
    # Chess Studio still owns pawn-slug-godot/current.json. Never allow this
    # repository to publish there, even with an explicit confirmation flag.
    if prefix != DEFAULT_PREFIX:
        raise BundleError(
            f"Pawn Action may only publish under {DEFAULT_PREFIX!r}; "
            f"refusing legacy/shared prefix {prefix!r}"
        )
    if not dry_run and not confirmed:
        raise BundleError("Live R2 publication requires --confirm-publish (manual cutover gate)")



def _reject_legacy_shared_live_destination(config: dict[str, Any]) -> None:
    """Never publish the standalone Web export into Chess Studio's public bucket.

    Staging Web artifacts are admitted and published by shadowops-infra to its
    separately verified private bucket. Even explicit copied-bucket credentials
    must not bypass this check during the handoff.
    """
    if (
        config.get("bucket") == "chess-studio-assets"
        or config.get("customDomain") == "assets.chess-studio.shadowops.dpdns.org"
    ):
        raise BundleError(
            "Pawn Action live publish to Chess Studio's shared/public R2 destination "
            "is forbidden; use shadowops-infra private staging release admission"
        )


def _require_publish_authority(config: dict[str, Any]) -> tuple[str, str]:
    """Require a deliberate Pawn Action destination and dedicated credentials.

    The cloned Chess Studio config may still name the shared R2 bucket. A
    generic CLOUDFLARE_API_TOKEN must never silently authorize a new writer.
    """
    bucket = config.get("bucket")
    domain = config.get("customDomain")
    approved_bucket = os.environ.get("PAWN_ACTION_R2_PUBLISH_BUCKET", "").strip()
    approved_domain = os.environ.get("PAWN_ACTION_R2_PUBLISH_DOMAIN", "").strip()
    if not approved_bucket or not approved_domain:
        raise BundleError(
            "Live Pawn Action publish requires PAWN_ACTION_R2_PUBLISH_BUCKET "
            "and PAWN_ACTION_R2_PUBLISH_DOMAIN explicitly approved for this repo"
        )
    if approved_bucket != bucket or approved_domain != domain:
        raise BundleError("Pawn Action R2 publish destination does not match approved bucket/domain")
    token = os.environ.get("PAWN_ACTION_CLOUDFLARE_API_TOKEN", "").strip()
    account_id = os.environ.get("PAWN_ACTION_CLOUDFLARE_ACCOUNT_ID", "").strip()
    if not token or not account_id:
        raise BundleError(
            "Live Pawn Action publish requires dedicated "
            "PAWN_ACTION_CLOUDFLARE_API_TOKEN / PAWN_ACTION_CLOUDFLARE_ACCOUNT_ID; "
            "legacy CLOUDFLARE_* credentials are not accepted"
        )
    return token, account_id


def _fetch_existing_pointer(token: str, account_id: str, bucket: str,
                            pointer_key: str, base_url: str, prefix: str
                            ) -> tuple[dict[str, Any] | None, str | None]:
    """Return validated pointer AND SHA-256 of exact original R2 JSON bytes.

    Release digest alone cannot detect an intervening repoint of sourceSha.
    This byte fingerprint binds any later mutation to the operator-reviewed
    current.json, and is checked a second time immediately before PUT.
    """
    try:
        raw = core.get_object(token, account_id, bucket, pointer_key)
    except core.PublishError as exc:
        # Only an explicit missing pointer permits a first publication.
        # Never overwrite a known pointer on timeouts, 403/500, or stale API errors.
        if str(exc) == f"Cloudflare GET HTTP 404 para {pointer_key}":
            return None, None
        raise BundleError(f"Cannot verify existing R2 pointer {pointer_key}: {exc}") from exc
    try:
        candidate = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeError) as exc:
        raise BundleError(f"Existing R2 pointer {pointer_key} is invalid JSON") from exc
    validate_pointer(candidate, base_url=base_url, prefix=prefix)
    return candidate, hashlib.sha256(raw).hexdigest()


def _require_current_pointer_match(expected_sha256: str, actual_sha256: str | None) -> None:
    """Explicit first-release or byte-for-byte current pointer precondition."""
    if expected_sha256 == "absent" and actual_sha256 is None:
        return
    if re.fullmatch(r"[0-9a-f]{64}", expected_sha256 or "") and expected_sha256 == actual_sha256:
        return
    raise BundleError(
        "R2 current pointer differs from explicitly expected fingerprint; "
        "abort publication and re-inspect the destination"
    )


def inspect_current(config_path: pathlib.Path) -> dict[str, Any]:
    """Read-only operator preview; never writes a release or moves a pointer."""
    config = core.load_config(config_path)
    token, account_id = _require_publish_authority(config)
    prefix = DEFAULT_PREFIX
    pointer, fingerprint = _fetch_existing_pointer(
        token, account_id, config["bucket"], f"{prefix}/{POINTER_NAME}",
        f"https://{config['customDomain']}", prefix,
    )
    result = {
        "prefix": prefix,
        "exists": pointer is not None,
        "currentPointerSha256": fingerprint if fingerprint is not None else "absent",
        "release": pointer["release"] if pointer is not None else None,
        "sourceSha": pointer["sourceSha"] if pointer is not None else None,
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return result


def publish(build_dir: pathlib.Path, config_path: pathlib.Path, prefix: str,
            dry_run: bool, confirmed: bool = False,
            expected_current_pointer_sha256: str = "") -> dict[str, Any]:
    _authorize_publish(prefix, dry_run=dry_run, confirmed=confirmed)
    if not dry_run and not (
        expected_current_pointer_sha256 == "absent"
        or re.fullmatch(r"[0-9a-f]{64}", expected_current_pointer_sha256 or "")
    ):
        raise BundleError(
            "Live publish requires --expected-current-pointer-sha256 "
            "<64hex|absent> from authenticated inspect-current"
        )
    config = core.load_config(config_path)
    # The copied config is a compatibility snapshot, not a publish destination.
    # Block the legacy shared/public bucket even when dedicated env values match.
    if not dry_run:
        _reject_legacy_shared_live_destination(config)
    # Refuse accidental live writes before reading/building an export or
    # making any Cloudflare request. Credential-less dry runs stay usable.
    credentials = None if dry_run else _require_publish_authority(config)
    base_url = f"https://{config['customDomain']}"
    pointer = build_pointer(build_dir, base_url, prefix, os.environ.get("GITHUB_SHA", "").lower())
    if dry_run:
        print(json.dumps(pointer, indent=2, sort_keys=True))
        return pointer

    token, account_id = credentials
    bucket = config["bucket"]
    pointer_key = f"{prefix.strip('/')}/{POINTER_NAME}"
    existing, before_fingerprint = _fetch_existing_pointer(
        token, account_id, bucket, pointer_key, base_url, prefix,
    )
    _require_current_pointer_match(expected_current_pointer_sha256, before_fingerprint)

    def check_unchanged_remote_pointer() -> None:
        # A remote writer or GC may have changed current.json while immutable
        # objects were uploading. Never overwrite a new pointer silently.
        _, fresh_fingerprint = _fetch_existing_pointer(
            token, account_id, bucket, pointer_key, base_url, prefix,
        )
        if fresh_fingerprint != before_fingerprint:
            raise BundleError(
                "R2 current pointer changed during release; refusing final PUT"
            )

    if existing is not None:
        action = _pointer_action(existing, pointer)
        if action == "unchanged":
            print(f"UNCHANGED Pawn Action Godot -> {pointer['index']}")
            return existing
        if action == "repoint":
            rendered = (json.dumps(pointer, indent=2, sort_keys=True) + "\n").encode("utf-8")
            check_unchanged_remote_pointer()
            core.upload_object(token, account_id, bucket, pointer_key, rendered, "application/json; charset=utf-8")
            print(f"REPOINTED Pawn Action Godot {pointer['release']} -> sourceSha={pointer['sourceSha']}")
            return pointer

    # Admission is atomic at release granularity: budget the sum of every
    # immutable object and the updated pointer before uploading any file.
    from r2_storage_governance import admission_check_batch

    rendered = (json.dumps(pointer, indent=2, sort_keys=True) + "\n").encode("utf-8")
    admission_check_batch(
        config, token=token, account_id=account_id,
        additions={
            **{entry["key"]: entry["bytes"] for entry in pointer["files"].values()},
            pointer_key: len(rendered),
        },
    )

    for relative, entry in pointer["files"].items():
        source = build_dir / pathlib.PurePosixPath(relative)
        core.upload_object(token, account_id, bucket, entry["key"], source.read_bytes(), entry["contentType"])
        print(f"UPLOADED {relative} -> {entry['url']}")

    check_unchanged_remote_pointer()
    core.upload_object(token, account_id, bucket, pointer_key, rendered, "application/json; charset=utf-8")
    print(f"PUBLISHED Pawn Action Godot {pointer['release']} -> {pointer['index']}")
    return pointer


def verify_pointer(path: pathlib.Path, config_path: pathlib.Path, prefix: str, expected_source_sha: str) -> str:
    config = core.load_config(config_path)
    base_url = f"https://{config['customDomain']}"
    try:
        pointer = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BundleError(f"No se pudo leer pointer Godot: {exc}") from exc
    validate_pointer(pointer, base_url=base_url, prefix=prefix)
    if expected_source_sha and pointer.get("sourceSha") != expected_source_sha.lower():
        raise BundleError(
            f"Pointer Godot apunta a sourceSha={pointer.get('sourceSha')!r}; esperado {expected_source_sha.lower()!r}"
        )
    return str(pointer["index"])


def self_test() -> None:
    with tempfile.TemporaryDirectory() as temp:
        root = pathlib.Path(temp)
        for name, payload in {
            "index.html": b"<html>godot</html>",
            "index.js": b"console.log('godot')",
            "index.wasm": b"wasm" * 32,
            "index.pck": b"pck" * 64,
        }.items():
            (root / name).write_bytes(payload)
        first = build_pointer(root, "https://assets.example.test", DEFAULT_PREFIX, "a" * 40)
        second = build_pointer(root, "https://assets.example.test", DEFAULT_PREFIX, "a" * 40)
        assert first == second
        assert first["index"].endswith(f"/releases/{first['release']}/index.html")
        assert first["files"]["index.wasm"]["contentType"] == "application/wasm"
        same_bundle_new_source = build_pointer(root, "https://assets.example.test", DEFAULT_PREFIX, "b" * 40)
        assert _pointer_action(first, second) == "unchanged"
        assert first["index"].startswith("https://assets.example.test/pawn-action/releases/")
        legacy_preview = build_pointer(root, "https://assets.example.test", LEGACY_PREFIX, "a" * 40)
        assert legacy_preview["index"].startswith("https://assets.example.test/pawn-slug-godot/releases/")
        for wrong_prefix in (LEGACY_PREFIX, "", "pawn-action/../pawn-slug-godot", "pawn-action/extra"):
            for dry_run in (True, False):
                try:
                    _authorize_publish(wrong_prefix, dry_run=dry_run, confirmed=True)
                except BundleError:
                    pass
                else:
                    raise AssertionError(f"Unsafe R2 publish prefix accepted: {wrong_prefix!r}")
        try:
            _authorize_publish(DEFAULT_PREFIX, dry_run=False, confirmed=False)
        except BundleError:
            pass
        else:
            raise AssertionError("Live publish without confirmation was accepted")
        _authorize_publish(DEFAULT_PREFIX, dry_run=True, confirmed=False)
        _authorize_publish(DEFAULT_PREFIX, dry_run=False, confirmed=True)
        from unittest.mock import patch
        # A --confirm-publish flag alone is deliberately insufficient.
        # The legacy generic secrets must not authorize the new repository.
        approved = {
            "PAWN_ACTION_R2_PUBLISH_BUCKET": "pawnaction-test",
            "PAWN_ACTION_R2_PUBLISH_DOMAIN": "pawn-action.example.test",
            "PAWN_ACTION_CLOUDFLARE_API_TOKEN": "isolated-test-token",
            "PAWN_ACTION_CLOUDFLARE_ACCOUNT_ID": "isolated-test-account",
        }
        target = {"bucket": "pawnaction-test", "customDomain": "pawn-action.example.test"}

        def expect_authority_rejection(env: dict[str, str], config: dict[str, str] = target) -> None:
            with patch.dict(os.environ, env, clear=True):
                try:
                    _require_publish_authority(config)
                except BundleError:
                    pass
                else:
                    raise AssertionError("Unauthorized Pawn Action R2 destination/credentials accepted")

        # Explicit approval variables cannot authorize writing to Chess Studio.
        for unsafe in (
            {"bucket": "chess-studio-assets", "customDomain": target["customDomain"]},
            {"bucket": target["bucket"], "customDomain": "assets.chess-studio.shadowops.dpdns.org"},
        ):
            with patch.dict(os.environ, {
                "PAWN_ACTION_R2_PUBLISH_BUCKET": unsafe["bucket"],
                "PAWN_ACTION_R2_PUBLISH_DOMAIN": unsafe["customDomain"],
                "PAWN_ACTION_CLOUDFLARE_API_TOKEN": "isolated-test-token",
                "PAWN_ACTION_CLOUDFLARE_ACCOUNT_ID": "isolated-test-account",
            }, clear=True):
                try:
                    _reject_legacy_shared_live_destination(unsafe)
                except BundleError:
                    pass
                else:
                    raise AssertionError("Shared/public R2 destination was accepted")
        _reject_legacy_shared_live_destination(target)
        expect_authority_rejection({})
        expect_authority_rejection({
            "CLOUDFLARE_API_TOKEN": "legacy-token",
            "CLOUDFLARE_ACCOUNT_ID": "legacy-account",
        })
        for variable in approved:
            incomplete = dict(approved)
            incomplete.pop(variable)
            expect_authority_rejection(incomplete)
        expect_authority_rejection(
            approved, {"bucket": "legacy-bucket", "customDomain": target["customDomain"]})
        expect_authority_rejection(
            approved, {"bucket": target["bucket"], "customDomain": "legacy.example.test"})
        with patch.dict(os.environ, approved, clear=True):
            assert _require_publish_authority(target) == (
                "isolated-test-token", "isolated-test-account")
        # Live publish must fail BEFORE attempting any Cloudflare I/O when
        # explicitly confirmed but with no dedicated repository authority.
        with patch.dict(os.environ, {}, clear=True), patch.object(
            core, "get_object", side_effect=AssertionError("unexpected remote GET")
        ), patch.object(
            core, "upload_object", side_effect=AssertionError("unexpected remote PUT")
        ):
            try:
                publish(root, DEFAULT_CONFIG, DEFAULT_PREFIX, dry_run=False, confirmed=True)
            except BundleError:
                pass
            else:
                raise AssertionError("Live publish accepted without dedicated authority")
        pointer_key = f"{DEFAULT_PREFIX}/{POINTER_NAME}"
        with patch.object(core, "get_object", side_effect=core.PublishError(
            f"Cloudflare GET HTTP 404 para {pointer_key}"
        )):
            assert _fetch_existing_pointer("test", "test", "test", pointer_key,
                                           "https://assets.example.test", DEFAULT_PREFIX) == (None, None)
        for failure in (f"Cloudflare GET HTTP 403 para {pointer_key}",
                        f"Cloudflare GET HTTP 500 para {pointer_key}"):
            with patch.object(core, "get_object", side_effect=core.PublishError(failure)):
                try:
                    _fetch_existing_pointer("test", "test", "test", pointer_key,
                                            "https://assets.example.test", DEFAULT_PREFIX)
                except BundleError:
                    pass
                else:
                    raise AssertionError(f"Unsafe pointer overwrite on {failure!r}")
        with patch.object(core, "get_object", return_value=b"{bad json"):
            try:
                _fetch_existing_pointer("test", "test", "test", pointer_key,
                                        "https://assets.example.test", DEFAULT_PREFIX)
            except BundleError:
                pass
            else:
                raise AssertionError("Corrupt existing R2 pointer was accepted")
        assert _pointer_action(first, same_bundle_new_source) == "repoint"
        # Exact remote bytes, not merely the release content SHA, are the
        # publication precondition; same immutable bundle may be repointed
        # to a different (reviewed) source commit.
        original = (json.dumps(first, sort_keys=True) + "\n").encode("utf-8")
        original_fingerprint = hashlib.sha256(original).hexdigest()
        with patch.object(core, "get_object", return_value=original):
            remote, fingerprint = _fetch_existing_pointer(
                "test", "test", "test", pointer_key,
                "https://assets.example.test", DEFAULT_PREFIX,
            )
            assert remote == first and fingerprint == original_fingerprint
        _require_current_pointer_match(original_fingerprint, fingerprint)
        _require_current_pointer_match("absent", None)
        for expected, observed in [
            ("absent", fingerprint),
            (original_fingerprint, None),
            ("f" * 64, fingerprint),
            ("", fingerprint),
            ("A" * 64, fingerprint),
        ]:
            try:
                _require_current_pointer_match(expected, observed)
            except BundleError:
                pass
            else:
                raise AssertionError("Unsafe R2 expected-pointer precondition passed")

        # Exercise actual live publishing code with stubbed remote access:
        # a mismatched current.json must fail BEFORE ANY upload.
        credentials = ("dedicated-test-token", "dedicated-test-account")
        desired_build = root
        # These mocked remote manifests were built under assets.example.test,
        # so the strict pointer URL validator must see that exact test origin.
        mock_remote_config = {"bucket": target["bucket"], "customDomain": "assets.example.test"}
        with patch.object(core, "load_config", return_value=mock_remote_config), patch(
            __name__ + "._require_publish_authority", return_value=credentials
        ), patch.dict(os.environ, {"GITHUB_SHA": "b" * 40}, clear=True):
            with patch.object(core, "get_object", return_value=original), patch.object(
                core, "upload_object", side_effect=AssertionError("unexpected PUT")
            ):
                try:
                    publish(desired_build, DEFAULT_CONFIG, DEFAULT_PREFIX, False, True, "absent")
                except BundleError:
                    pass
                else:
                    raise AssertionError("Publishing over unreviewed current pointer was allowed")
            # A remote source repoint between initial inspection and final
            # PUT must fail even when immutable release bytes are unchanged.
            changed_remote = (json.dumps(same_bundle_new_source, sort_keys=True) + "\n").encode("utf-8")
            with patch.object(core, "get_object", side_effect=[original, changed_remote]), patch.object(
                core, "upload_object", side_effect=AssertionError("unsafe pointer repoint PUT")
            ):
                try:
                    publish(desired_build, DEFAULT_CONFIG, DEFAULT_PREFIX, False, True, original_fingerprint)
                except BundleError as exc:
                    assert "changed during release" in str(exc)
                else:
                    raise AssertionError("Concurrent repoint was not detected")
            # No matching current pointer in the first-release scenario:
            # a new pointer appearing before the final PUT must fail closed.
            missing = core.PublishError(f"Cloudflare GET HTTP 404 para {pointer_key}")
            with patch.object(core, "get_object", side_effect=[missing, original]), patch(
                "r2_storage_governance.admission_check_batch"
            ), patch.object(core, "upload_object", return_value={}) as uploads:
                try:
                    publish(desired_build, DEFAULT_CONFIG, DEFAULT_PREFIX, False, True, "absent")
                except BundleError as exc:
                    assert "changed during release" in str(exc)
                else:
                    raise AssertionError("Concurrent first-release pointer was overwritten")
                assert not any(call.args[3] == pointer_key for call in uploads.call_args_list)

        (root / "index.pck").write_bytes(b"changed" * 64)
        changed = build_pointer(root, "https://assets.example.test", DEFAULT_PREFIX, "b" * 40)
        assert changed["release"] != first["release"]
        assert _pointer_action(first, changed) == "publish"
        (root / "index.js").unlink()
        try:
            build_pointer(root, "https://assets.example.test", DEFAULT_PREFIX)
        except BundleError:
            pass
        else:
            raise AssertionError("missing required file was accepted")
    print("OK Pawn Action Godot bundle self-test")


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser()
    sub = result.add_subparsers(dest="command", required=True)
    sub.add_parser("self-test")
    check = sub.add_parser("check")
    check.add_argument("--build-dir", type=pathlib.Path, default=DEFAULT_BUILD_DIR)
    check.add_argument("--config", type=pathlib.Path, default=DEFAULT_CONFIG)
    check.add_argument("--prefix", default=DEFAULT_PREFIX)
    publish_cmd = sub.add_parser("publish")
    publish_cmd.add_argument("--build-dir", type=pathlib.Path, default=DEFAULT_BUILD_DIR)
    publish_cmd.add_argument("--config", type=pathlib.Path, default=DEFAULT_CONFIG)
    publish_cmd.add_argument("--prefix", default=DEFAULT_PREFIX)
    publish_cmd.add_argument("--dry-run", action="store_true")
    publish_cmd.add_argument("--confirm-publish", action="store_true",
                             help="Explicitly authorize writing pawn-action/current.json (never the legacy pointer)")
    publish_cmd.add_argument("--expected-current-pointer-sha256", default="",
                             metavar="64HEX|absent",
                             help="Exact authenticated current.json fingerprint from inspect-current; mandatory for live writes")
    inspect = sub.add_parser("inspect-current",
                             help="Read-only inspect of the dedicated Pawn Action pointer and its exact SHA256")
    inspect.add_argument("--config", type=pathlib.Path, default=DEFAULT_CONFIG)
    verify = sub.add_parser("verify-pointer")
    verify.add_argument("path", type=pathlib.Path)
    verify.add_argument("--config", type=pathlib.Path, default=DEFAULT_CONFIG)
    verify.add_argument("--prefix", default=DEFAULT_PREFIX)
    verify.add_argument("--expected-source-sha", default="")
    return result


def main() -> int:
    args = parser().parse_args()
    try:
        if args.command == "self-test":
            self_test()
        elif args.command == "check":
            config = core.load_config(args.config)
            pointer = build_pointer(args.build_dir, f"https://{config['customDomain']}", args.prefix)
            print(json.dumps(pointer, indent=2, sort_keys=True))
        elif args.command == "publish":
            publish(args.build_dir, args.config, args.prefix, args.dry_run,
                    args.confirm_publish, args.expected_current_pointer_sha256)
        elif args.command == "inspect-current":
            inspect_current(args.config)
        elif args.command == "verify-pointer":
            print(verify_pointer(args.path, args.config, args.prefix, args.expected_source_sha))
        return 0
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
