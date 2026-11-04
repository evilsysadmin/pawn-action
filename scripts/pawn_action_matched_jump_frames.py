#!/usr/bin/env python3
"""Unmodified Chromium PNGs: physical jump height vs grounded skin centroid.

This comparison never changes or synthesizes a screenshot. The legacy Web
export does not emit physical jump bridge events, so visible displacement and
landing are the only comparable proof, alongside actual Godot input.
"""
import argparse
import hashlib
import json
from pathlib import Path
from PIL import Image

ROI = (80, 325, 155, 600)
# An older Chromium/Godot shell can return a top-left 800x600 CDP frame
# for a 1280x720 page. The face ROI is fully preserved at 1:1 pixels.
FULL = (1280, 720)
LEGACY_CDPS = {(800, 600), (800, 450)}
MIN_FACE_PIXELS = 90
MIN_RISE_PX = 80


def face_y(filename, *, cdp=False, source="current"):
    if filename.is_symlink() or not filename.is_file():
        raise ValueError("Missing or unsafe Chromium screenshot")
    with Image.open(filename) as im:
        if im.format != "PNG":
            raise ValueError("Only original compositor PNG accepted")
        size = im.size
        if not cdp and size != FULL:
            raise ValueError("Idle and landed screenshots must be full viewport")
        if cdp and size != FULL and not (source == "legacy" and size in LEGACY_CDPS):
            raise ValueError("Unsupported compositor size, refuse rescale")
        # A short 800x450 first screencast frame crops Matthias' legs and
        # cannot prove return/height. Preserve it but never select as apex.
        if size[1] < ROI[3]:
            return None
        crop = im.convert("RGB").crop(ROI)
    pixels = crop.load()
    yy = []
    for y in range(crop.height):
        for x in range(crop.width):
            r, g, b = pixels[x, y]
            if r >= 110 and r > 1.3 * g and r > 1.5 * b and 42 < g < 165 and b < 130:
                yy.append(y + ROI[1])
    if len(yy) < MIN_FACE_PIXELS:
        return None
    yy.sort()
    return yy[len(yy) // 2]


def extract(folder, source):
    if source not in ("current", "legacy"):
        raise ValueError("Unexpected capture source")
    origin = folder / "matched-pistol-jump-source"
    meta = json.loads((origin / "source.json").read_text())
    if (meta.get("source") != "chromium-cdp-compositor"
            or meta.get("key") != source
            or meta.get("stage") != "industrial_front_v1"
            or meta.get("viewport") != {"width": 1280, "height": 720}
            or meta.get("startX") != 110
            or meta.get("jumpHoldMs") != 850
            or meta.get("postJumpMs") != 1250):
        raise ValueError("Mismatch of jump route, timing or source")
    frames = sorted(origin.glob("frame-*.png"))
    if not 10 <= len(frames) <= 120 or len(frames) != meta.get("frames"):
        raise ValueError("Insufficient compositor frames")
    idle = folder / "60-pistol-jump-idle.png"
    landed = folder / "62-pistol-jump-landed.png"
    grounded_y = face_y(idle)
    landed_y = face_y(landed)
    if grounded_y is None or landed_y is None or abs(grounded_y - landed_y) > 24:
        raise ValueError("No stable grounded start/landing")
    best = None
    skipped_partial = 0
    dimensions = set()
    for frame in frames:
        with Image.open(frame) as im:
            dimensions.add(im.size)
            if im.size[1] < ROI[3]:
                skipped_partial += 1
        center = face_y(frame, cdp=True, source=source)
        if center is not None:
            rise = grounded_y - center
            if best is None or rise > best[0]:
                best = (rise, frame, center)
    if len(frames) - skipped_partial < 8:
        raise ValueError("Not enough usable complete-ROI compositor frames")
    if best is None or best[0] < MIN_RISE_PX:
        raise ValueError("No authentic vertical ascent of 80px in compositor")
    apex = folder / "61-pistol-jump-apex.png"
    if apex.exists():
        raise ValueError("Cannot overwrite an existing jump candidate")
    apex.write_bytes(best[1].read_bytes())  # preserve original cropped/full PNG
    with Image.open(apex) as im:
        apex_size = list(im.size)
    names = ("60-pistol-jump-idle.png", "61-pistol-jump-apex.png",
             "62-pistol-jump-landed.png")
    report = {
        "schema": 1, "status": "physical_jump_pixels_verified",
        "source": source, "stage": "industrial_front_v1",
        "viewport": {"width": 1280, "height": 720},
        "startX": 110, "minRisePx": MIN_RISE_PX,
        "measuredRisePx": best[0],
        "groundedMedianFaceY": grounded_y, "apexMedianFaceY": best[2],
        "landedMedianFaceY": landed_y,
        "apexSourceFrame": best[1].name, "sourceFrameCount": len(frames),
        "apexSourceSize": apex_size,
        "sourceFrameSizes": [list(size) for size in sorted(dimensions)],
        "partialFramesIgnored": skipped_partial,
        "originalPixelsRetained": True,
        "images": {name: hashlib.sha256((folder / name).read_bytes()).hexdigest()
                   for name in names},
    }
    (folder / "matched-pistol-jump.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report))


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--dir", type=Path, required=True)
    p.add_argument("--source", choices=("current", "legacy"), required=True)
    args = p.parse_args()
    extract(args.dir, args.source)
