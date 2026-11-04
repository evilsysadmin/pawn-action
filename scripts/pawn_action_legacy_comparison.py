#!/usr/bin/env python3
"""Side-by-side contact sheet only from verified legacy + current real captures.

This is NOT a visual approval and never modifies the original screenshot PNGs.
"""
import argparse
import hashlib
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageOps


class CandidateError(ValueError):
    pass


def comparison(legacy: Path, current: Path, current_sha: str) -> None:
    evidence = json.loads((legacy / "baseline-candidate.json").read_text(encoding="utf-8"))
    if evidence.get("status") not in (
            "candidate_not_approved", "candidate_partial_not_approved"):
        raise CandidateError("Legacy source is not a verified baseline candidate")
    smg_ok = evidence.get("smg", {}).get("status") == "captured_verified"
    if smg_ok:
        if evidence["smg"].get("method") != "pistol_ready_then_authored_pickup_at_x1240":
            raise CandidateError("Legacy SMG was not captured through real pickup")
        visual_health = json.loads((current / "runtime-visual-health.json").read_text())
        matched = visual_health.get("matchedSmgProof", {})
        if (matched.get("method") != evidence["smg"]["method"]
                or matched.get("captureSpawnX") != 1170
                or matched.get("authoredPickupX") != 1240
                or matched.get("viewport") != {"width": 1280, "height": 720}
                or any(matched.get(k) is not True for k in
                       ("ready", "weaponPickup", "weaponChanged", "firedAfterPickup"))):
            raise CandidateError("Pawn Action SMG did not prove same real pickup path")
        review = json.loads((current / "review/review-manifest.json").read_text())
        if review.get("source_sha") != current_sha:
            raise CandidateError("Pawn Action matched capture is not from exact HEAD")
        current_png = current / "57-smg-pickup-matched.png"
        if (not current_png.is_file()
                or review.get("evidence", {}).get("57-smg-pickup-matched.png", {}).get("sha256")
                != hashlib.sha256(current_png.read_bytes()).hexdigest()):
            raise CandidateError("Unpinned or damaged Pawn Action matched SMG PNG")
    if (evidence["status"] == "candidate_not_approved") != smg_ok:
        raise CandidateError("Inconsistent legacy SMG evidence/status")
    if len(evidence.get("sourceSha", "")) != 40 or len(current_sha) != 40:
        raise CandidateError("Missing source SHA identity")
    legacy_jump = evidence.get("matchedPistolJumpProof")
    current_jump = json.loads((current / "matched-pistol-jump.json").read_text())
    for source, proof, folder in (
            ("legacy", legacy_jump, legacy), ("current", current_jump, current)):
        if (not isinstance(proof, dict)
                or proof.get("status") != "physical_jump_pixels_verified"
                or proof.get("source") != source
                or proof.get("stage") != "industrial_front_v1"
                or proof.get("viewport") != {"width": 1280, "height": 720}
                or proof.get("startX") != 110
                or proof.get("measuredRisePx", 0) < 80):
            raise CandidateError("Matched real 80px jump absent: " + source)
        for name in ("60-pistol-jump-idle.png", "61-pistol-jump-apex.png",
                     "62-pistol-jump-landed.png"):
            f = folder / name
            if (not f.is_file() or proof.get("images", {}).get(name)
                    != hashlib.sha256(f.read_bytes()).hexdigest()):
                raise CandidateError("Matched jump evidence hash mismatch")
    current_review = json.loads((current / "review/review-manifest.json").read_text())
    if current_review.get("source_sha") != current_sha:
        raise CandidateError("Matched current jump not from exact HEAD")
    for name, digest in current_jump["images"].items():
        if current_review.get("evidence", {}).get(name, {}).get("sha256") != digest:
            raise CandidateError("Matched current jump PNG missing from SHA-bound review")
    pairs = [
        ("Idle", "00-idle.png", "00-idle.png"),
        ("Run (independent timing)", "10-run.png", "10-run-07.png"),
        ("Run + fire", "20-run-fire.png", "20-run-fire-07.png"),
        ("Mobile landscape", "mobile-landscape-ready.png", "mobile-landscape-ready.png"),
        ("Pistol jump real apex", "61-pistol-jump-apex.png", "61-pistol-jump-apex.png"),
        ("Pistol landed", "62-pistol-jump-landed.png", "62-pistol-jump-landed.png"),
    ]
    if smg_ok:
        pairs.insert(3, ("SMG real pickup (same route)", "51-smg-selected.png",
                         "57-smg-pickup-matched.png"))
    tile_w, tile_h, top = 530, 310, 90
    sheet = Image.new("RGB", (tile_w * 2, len(pairs) * tile_h + top), "#141a23")
    draw = ImageDraw.Draw(sheet)
    draw.text((16, 12), "LEGACY CHESS STUDIO  |  CANDIDATE - NOT APPROVED", fill="white")
    draw.text((16, 32), "source: " + evidence["sourceSha"][:12] +
              "   vs   Pawn Action: " + current_sha[:12], fill="#c1cfdb")
    draw.text((16, 51), "Independent frames, not frame-locked | " +
              ("SMG VERIFIED" if smg_ok else "SMG NOT PROVEN"),
              fill="#f6c36b")
    for idx, (label, before, after) in enumerate(pairs):
        row_y = top + idx * tile_h
        for column, folder, name in (
            (0, legacy, before), (1, current, after)
        ):
            f = folder / name
            if f.is_symlink() or not f.is_file():
                raise CandidateError("Missing or unsafe actual screenshot: " + name)
            data = f.read_bytes()
            if column == 0:
                pinned = evidence["captures"].get(name)
                if not pinned or hashlib.sha256(data).hexdigest() != pinned.get("sha256"):
                    raise CandidateError("Legacy screenshot hash mismatch: " + name)
            with Image.open(f) as im:
                if im.format != "PNG":
                    raise CandidateError("Expected real Chromium PNG: " + name)
                picture = ImageOps.contain(im.convert("RGB"), (tile_w - 16, tile_h - 43))
                x = column * tile_w + (tile_w - picture.width) // 2
                sheet.paste(picture, (x, row_y + 30))
            draw.text((column * tile_w + 12, row_y + 8),
                      ("CHESS STUDIO" if column == 0 else "PAWN ACTION") +
                      "  |  " + label, fill="white")
    target = legacy / "side-by-side-candidate.jpg"
    sheet.save(target, "JPEG", quality=90)
    print("Candidate comparison created (NOT approved):", target)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--legacy-dir", required=True, type=Path)
    parser.add_argument("--current-dir", required=True, type=Path)
    parser.add_argument("--current-sha", required=True)
    args = parser.parse_args()
    comparison(args.legacy_dir, args.current_dir, args.current_sha)


if __name__ == "__main__":
    main()
