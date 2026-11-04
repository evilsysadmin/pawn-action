"""Offline regression tests for original-pixel matched-jump detection."""
import json
import tempfile
import unittest
from pathlib import Path
import sys
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import pawn_action_matched_jump_frames as jump


def picture(path, size=(1280, 720), actor_y=540, torso=True):
    im = Image.new("RGB", size, "#15202d")
    if torso:
        pen = ImageDraw.Draw(im)
        pen.rectangle((92, actor_y, 127, actor_y + 25), fill=(190, 105, 44))
    im.save(path, "PNG")


def fixture(folder, *, source="legacy", rise=135, landing=True):
    frames = folder / "matched-pistol-jump-source"
    frames.mkdir(parents=True)
    (frames / "source.json").write_text(json.dumps({
        "source": "chromium-cdp-compositor",
        "key": source, "frames": 11,
        "viewport": {"width": 1280, "height": 720},
        "stage": "industrial_front_v1", "startX": 110,
        "jumpHoldMs": 850, "postJumpMs": 1250,
    }))
    picture(folder / "60-pistol-jump-idle.png")
    picture(folder / "62-pistol-jump-landed.png", actor_y=540 if landing else 420)
    for n in range(11):
        size = (800, 450) if source == "legacy" and n == 0 else (
            (800, 600) if source == "legacy" else (1280, 720))
        y = 540 - rise if 3 <= n <= 5 else 540
        picture(frames / f"frame-{n:03d}.png", size=size, actor_y=y)


class JumpFrameTests(unittest.TestCase):
    def test_legacy_cropped_frame_keeps_original_bytes_and_measures_height(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixture(root)
            jump.extract(root, "legacy")
            output = json.loads((root / "matched-pistol-jump.json").read_text())
            self.assertGreaterEqual(output["measuredRisePx"], 80)
            self.assertEqual(output["apexSourceSize"], [800, 600])
            self.assertEqual(output["partialFramesIgnored"], 1)
            self.assertEqual(output["sourceFrameSizes"], [[800, 450], [800, 600]])
            self.assertEqual((root / "61-pistol-jump-apex.png").read_bytes(),
                             (root / "matched-pistol-jump-source" /
                              output["apexSourceFrame"]).read_bytes())

    def test_current_full_frame_and_missing_jump_or_landing_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixture(root, source="current")
            jump.extract(root, "current")
            value = json.loads((root / "matched-pistol-jump.json").read_text())
            self.assertEqual(value["apexSourceSize"], [1280, 720])
        for rise, landed in ((20, True), (135, False)):
            with self.subTest(rise=rise, landed=landed), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                fixture(root, rise=rise, landing=landed)
                with self.assertRaises(ValueError):
                    jump.extract(root, "legacy")
                self.assertFalse((root / "61-pistol-jump-apex.png").exists())


if __name__ == "__main__":
    unittest.main()
