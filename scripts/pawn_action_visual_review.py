#!/usr/bin/env python3
"""SHA-bound visual review contact sheets from real Chromium PNG captures.

Review aids only; no automatic visual approval without legacy baseline.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
from PIL import Image, ImageDraw, ImageOps

SHA = re.compile(r"[a-f0-9]{40}\Z")
PANELS = {
    "desktop": [
        ("Pistol idle", "00-idle.png"),
        ("Pistol run 00", "10-run-00.png"),
        ("Pistol run 07", "10-run-07.png"),
        ("Pistol run + fire", "20-run-fire-07.png"),
        ("Crouch", "40-crouch-02.png"),
        ("SMG selected", "51-smg-selected-after-100ms.png"),
        ("SMG run", "52-smg-run-08.png"),
        ("SMG run + fire", "53-smg-run-fire-08.png"),
        ("SMG real pickup, x=1240", "57-smg-pickup-matched.png"),
        ("Pistol grounded takeoff", "60-pistol-jump-idle.png"),
        ("Pistol real jump", "61-pistol-jump-apex.png"),
        ("Pistol landed", "62-pistol-jump-landed.png"),
        ("SMG jump", "55-smg-jump-fall-07.png"),
        ("SMG landed", "56-smg-landed.png"),
        ("Industrial initial", "stage-industrial_front_v1.png"),
        ("Industrial traversal", "stage-industrial_front_v1-traversal.png"),
    ],
    "closeups": [
        ("Pistol idle", "00-idle-closeup.png"),
        ("Pistol run 00", "10-run-00-closeup.png"),
        ("Pistol run 07", "10-run-07-closeup.png"),
        ("Pistol run + fire", "20-run-fire-07-closeup.png"),
        ("SMG selected", "50-smg-selected-immediate-closeup.png"),
        ("SMG ready", "51-smg-selected-after-100ms-closeup.png"),
        ("SMG run + fire", "53-smg-run-fire-08-closeup.png"),
        ("SMG real pickup", "57-smg-pickup-matched-closeup.png"),
        ("SMG landed", "56-smg-landed-closeup.png"),
    ],
    "motion": [
        ("Pistol run 00", "10-run-00-closeup.png"),
        ("Pistol run 03", "10-run-03-closeup.png"),
        ("Pistol run 07", "10-run-07-closeup.png"),
        ("Pistol run 11", "10-run-11-closeup.png"),
        ("SMG run 00", "52-smg-run-00-closeup.png"),
        ("SMG run 04", "52-smg-run-04-closeup.png"),
        ("SMG run 08", "52-smg-run-08-closeup.png"),
        ("SMG run 12", "52-smg-run-12-closeup.png"),
        ("SMG jump 00", "55-smg-jump-fall-00-closeup.png"),
        ("SMG jump 03", "55-smg-jump-fall-03-closeup.png"),
        ("SMG jump 07", "55-smg-jump-fall-07-closeup.png"),
        ("SMG jump 11", "55-smg-jump-fall-11-closeup.png"),
        ("SMG jump 15", "55-smg-jump-fall-15-closeup.png"),
    ],
    "motion-compare": [
        ("Run 00", "10-run-00.png"),
        ("Run 03", "10-run-03.png"),
        ("Run 07", "10-run-07.png"),
        ("Run 11", "10-run-11.png"),
        ("Fire held 00", "20-run-fire-00.png"),
        ("Fire held 03", "20-run-fire-03.png"),
        ("Fire held 07", "20-run-fire-07.png"),
        ("Fire held 11", "20-run-fire-11.png"),
    ],
    "mobile": [
        ("Touch ready", "mobile-landscape-ready.png"),
        ("Touch fire", "mobile-landscape-fire.png"),
        ("Touch grenade", "mobile-landscape-grenade.png"),
        ("Touch after reload", "mobile-landscape-reload.png"),
        ("Rotate guidance", "mobile-portrait-rotate.png"),
    ],
}


class ReviewError(ValueError):
    pass


def validate_metadata(directory):
    try:
        desktop = json.loads((directory / "runtime-visual-health.json").read_text())
        mobile = json.loads((directory / "mobile-web-smoke.json").read_text())
    except (ValueError, OSError, UnicodeError) as exc:
        raise ReviewError("Missing or invalid Chromium capture metadata") from exc
    if (desktop.get("schema") != 7
            or desktop.get("detailedStage") != "industrial_front_v1"
            or not isinstance(desktop.get("captures"), list)
            or len(desktop["captures"]) < 60
            or not isinstance(desktop.get("stageOverviews"), list)
            or len(desktop["stageOverviews"]) < 2):
        raise ReviewError("Desktop Chromium evidence incomplete")
    jump = desktop.get("jumpProof")
    if (not isinstance(jump, dict)
            or type(jump.get("minHeightPx")) is not int
            or jump["minHeightPx"] < 80
            or any(type(jump.get(k)) is not int or jump[k] < 0 for k in (
                "airborneBefore", "airborneAfter", "landedBefore", "landedAfter"))
            or jump["airborneAfter"] <= jump["airborneBefore"]
            or jump["landedAfter"] <= jump["landedBefore"]):
        raise ReviewError("Missing verified airborne jump / landing proof")
    smg = desktop.get("matchedSmgProof")
    if (not isinstance(smg, dict)
            or smg.get("method") != "pistol_ready_then_authored_pickup_at_x1240"
            or smg.get("stage") != "industrial_front_v1"
            or smg.get("captureSpawnX") != 1170
            or smg.get("authoredPickupX") != 1240
            or smg.get("viewport") != {"width": 1280, "height": 720}
            or smg.get("screenshot") != "57-smg-pickup-matched.png"
            or any(smg.get(k) is not True for k in (
                "ready", "weaponPickup", "weaponChanged", "firedAfterPickup"))
            or not isinstance(smg.get("events"), list)
            or not {"ready", "weapon-pickup", "weapon-changed",
                    "player-fired"}.issubset(smg["events"])):
        raise ReviewError("Matched real SMG pickup/firing proof missing")
    matched = desktop.get("matchedPistolJumpProof")
    if (not isinstance(matched, dict)
            or matched.get("status") != "physical_jump_pixels_verified"
            or matched.get("source") != "current"
            or matched.get("measuredRisePx", 0) < 80
            or matched.get("startX") != 110
            or matched.get("physicsEvents") != "player-airborne_and_player-landed"):
        raise ReviewError("Matched pistol jump missing real physical/visual proof")
    names = []
    for row in desktop["captures"]:
        if (not isinstance(row, dict) or not isinstance(row.get("label"), str)
                or not isinstance(row.get("path"), str)
                or Path(row["path"]).name != row["label"] + ".png"):
            raise ReviewError("Invalid capture identity")
        names.append(row["label"] + ".png")
    if len(set(names)) != len(names):
        raise ReviewError("Duplicate capture identity")
    required = {name for group in ("desktop", "closeups", "motion")
                for _, name in PANELS[group] if not name.startswith("stage-")}
    if not required.issubset(names):
        raise ReviewError("Missing documented runtime capture")
    overviews = {Path(row.get("path", "")).name
                 for row in desktop["stageOverviews"] if isinstance(row, dict)}
    if not {"stage-industrial_front_v1.png",
            "stage-industrial_front_v1-traversal.png"}.issubset(overviews):
        raise ReviewError("Industrial stage evidence unavailable")
    if (mobile.get("schema") != 1 or mobile.get("pageErrors") != []
            or not isinstance(mobile.get("phases"), list)):
        raise ReviewError("Mobile evidence incomplete")
    phases = {p.get("phase"): p for p in mobile["phases"] if isinstance(p, dict)}
    if (not {"cold", "touch-fire", "touch-grenade", "reload", "touch-fire-after-reload",
             "portrait"}.issubset(phases)
            or any(type(phases[k].get("shots")) is not int or phases[k]["shots"] < 1
                   for k in ("touch-fire", "touch-fire-after-reload"))
            or type(phases["touch-grenade"].get("throws")) is not int
            or phases["touch-grenade"]["throws"] < 1
            or phases["portrait"].get("orientationBlocked") is not True
            or phases["portrait"].get("noticeVisible") is not True
            or phases["portrait"].get("canvasTouchDisabled") is not True):
        raise ReviewError("Touch or rotate proof missing")


def load_png(directory, name):
    file = directory / name
    if file.is_symlink() or not file.is_file() or file.stat().st_size > 8 * 1024**2:
        raise ReviewError("Missing or excessive runtime PNG: " + name)
    try:
        with Image.open(file) as source:
            if source.format != "PNG":
                raise ReviewError("Not a PNG: " + name)
            size = source.size
            if name.startswith("mobile-landscape-"):
                valid = size == (915, 412)
            elif name == "mobile-portrait-rotate.png":
                valid = size == (390, 844)
            elif name.endswith("-closeup.png"):
                valid = 160 <= size[0] <= 560 and 140 <= size[1] <= 420
            else:
                valid = size == (1280, 720)
            if not valid:
                raise ReviewError("Invalid screenshot viewport: " + name)
            image = source.convert("RGB")
    except (OSError, ValueError, Image.DecompressionBombError) as exc:
        raise ReviewError("Damaged screenshot: " + name) from exc
    return image, {"width": size[0], "height": size[1],
                   "sha256": hashlib.sha256(file.read_bytes()).hexdigest()}


def sheet(title, items, images, sha, columns, tile):
    gap, top, label_height = 16, 70, 38
    rows = (len(items) + columns - 1) // columns
    surface = Image.new("RGB", (gap + columns * (tile[0] + gap),
       top + rows * (tile[1] + label_height + gap) + gap), "#121921")
    pen = ImageDraw.Draw(surface)
    pen.text((gap, 15), "Pawn Action / " + title + " / SHA " + sha[:12], fill="white")
    pen.text((gap, 40), "REVIEW PENDING / NO APPROVED CHESS STUDIO BASELINE",
             fill="#f0cb96")
    for i, (caption, name) in enumerate(items):
        col, row = i % columns, i // columns
        x = gap + col * (tile[0] + gap)
        y = top + row * (tile[1] + label_height + gap)
        small = ImageOps.contain(images[name], tile)
        surface.paste(small, (x + (tile[0] - small.width)//2,
                              y + (tile[1] - small.height)//2))
        pen.text((x, y + tile[1] + 7), caption, fill="#f3f1e8")
    return surface


def build(directory, output, sha, run_id):
    if not SHA.fullmatch(sha):
        raise ReviewError("Source SHA must be exact 40 lowercase hex")
    if not re.fullmatch(r"[1-9][0-9]{0,18}", run_id):
        raise ReviewError("Actions run ID must be numeric and positive")
    if output.exists() or not directory.is_dir():
        raise ReviewError("Evidence source missing or review output already exists")
    validate_metadata(directory)
    selected = sorted({name for items in PANELS.values() for _, name in items})
    images, evidence = {}, {}
    for name in selected:
        images[name], evidence[name] = load_png(directory, name)
    # Validate all original PNGs before creating any output.
    output.mkdir(parents=True)
    for group, (cols, tile) in {
        "desktop": (3, (410, 231)), "closeups": (4, (280, 225)),
        "motion": (4, (280, 225)), "motion-compare": (4, (410, 231)),
        "mobile": (2, (460, 400)),
    }.items():
        sheet(group, PANELS[group], images, sha, cols, tile).save(
            output / ("review-" + group + ".jpg"), quality=88)
    report = {
        "schema": 1, "source_sha": sha, "github_run_id": run_id,
        "status": "review_pending",
        "baseline": {"status": "not_supplied", "approved": False},
        "runtime": "real_chromium_godot_web",
        "groups": {g: [n for _, n in items] for g, items in PANELS.items()},
        "evidence": evidence,
    }
    (output / "review-manifest.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n")
    (output / "README.md").write_text(
        "# Pawn Action visual review\n\n"
        + "Source SHA: " + sha + "\nActions run: " + run_id + "\n\n"
        + "Five contact sheets from real Chromium/Godot captures. "
        + "Original screenshot SHA256 values are in review-manifest.json. "
        + "Visual review is PENDING. No comparable approved Chess Studio "
        + "baseline is bundled. Green CI does not approve visual parity. "
        + "Keep the migration PR Draft until the screenshots, scale, "
        + "weapons, animation and mobile touch have been reviewed.\n")
    return report


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--capture-dir", required=True, type=Path)
    p.add_argument("--out", required=True, type=Path)
    p.add_argument("--source-sha", required=True)
    p.add_argument("--run-id", required=True)
    args = p.parse_args()
    try:
        result = build(args.capture_dir, args.out, args.source_sha, args.run_id)
    except (ReviewError, OSError) as exc:
        print("PAWN_ACTION_VISUAL_REVIEW_BLOCKED: " + str(exc), file=sys.stderr)
        return 1
    print("PAWN_ACTION_VISUAL_REVIEW_PACKED " + json.dumps({
        "head_sha": result["source_sha"], "run_id": result["github_run_id"],
        "review_status": result["status"], "baseline": result["baseline"]["status"],
        "screenshots": len(result["evidence"]),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
