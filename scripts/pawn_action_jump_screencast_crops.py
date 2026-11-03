#!/usr/bin/env python3
"""Fail-closed 2D closeups from actual Chromium CDP compositor PNG frames.

Used only by the visual capture harness, never by the game or sprite compiler.
"""
from pathlib import Path
import sys
from PIL import Image


def create_closeups(directory: Path) -> None:
    for frame in (0, 3, 7, 11, 15):
        source = directory / f"55-smg-jump-fall-{frame:02d}.png"
        target = directory / f"55-smg-jump-fall-{frame:02d}-closeup.png"
        if source.is_symlink() or not source.is_file() or target.exists():
            raise ValueError(f"Unsafe or absent screencast frame: {source.name}")
        with Image.open(source) as image:
            if image.format != "PNG" or image.size != (1280, 720):
                raise ValueError(f"Wrong Chromium compositor frame: {source.name}")
            # Match the capture harness's historic crop geometry.
            x = 320 if frame >= 8 else 0
            image.convert("RGB").crop((x, 274, x + 560, 692)).save(target, format="PNG")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: pawn_action_jump_screencast_crops.py <capture-dir>")
    create_closeups(Path(sys.argv[1]))
