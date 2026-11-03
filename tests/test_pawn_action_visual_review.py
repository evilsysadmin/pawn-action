"""Offline, actual-PNG contract tests for Pawn Action visual review packets."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import pawn_action_visual_review as review

SHA = "a" * 40


def capture_fixture(folder):
    folder.mkdir(parents=True)
    names = {name for items in review.PANELS.values() for _, name in items}
    for name in names:
        if name.startswith("mobile-landscape-"):
            dims = (915, 412)
        elif name == "mobile-portrait-rotate.png":
            dims = (390, 844)
        elif name.endswith("-closeup.png"):
            dims = (500, 300)
        else:
            dims = (1280, 720)
        Image.new("RGB", dims, "#345678").save(folder / name)
    mandatory = sorted(name for name in names if not name.startswith("mobile-")
                       and not name.startswith("stage-"))
    labels = [Path(name).stem for name in mandatory]
    labels += ["extra-" + str(i) for i in range(65)]
    desktop = {
        "schema": 7, "detailedStage": "industrial_front_v1",
        "jumpProof": {"minHeightPx": 80, "airborneBefore": 0,
                      "airborneAfter": 1, "landedBefore": 0, "landedAfter": 1},
        "captures": [{"label": name, "path": "/runner/visual-evidence/" + name + ".png"}
                     for name in labels],
        "stageOverviews": [
            {"path": "/runner/visual-evidence/stage-industrial_front_v1.png"},
            {"path": "/runner/visual-evidence/stage-industrial_front_v1-traversal.png"},
        ],
    }
    mobile = {
        "schema": 1, "pageErrors": [],
        "phases": [{"phase": "cold"}, {"phase": "touch-fire", "shots": 3},
                   {"phase": "touch-grenade", "throws": 1}, {"phase": "reload"},
                   {"phase": "touch-fire-after-reload", "shots": 2},
                   {"phase": "portrait", "orientationBlocked": True,
                    "noticeVisible": True, "canvasTouchDisabled": True}],
    }
    (folder / "runtime-visual-health.json").write_text(json.dumps(desktop))
    (folder / "mobile-web-smoke.json").write_text(json.dumps(mobile))


class RealReviewTests(unittest.TestCase):
    def test_real_source_hashes_and_sha_bound_pending_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "captures"
            out = Path(tmp) / "review"
            capture_fixture(folder)
            result = review.build(folder, out, SHA, "41647681783")
            self.assertEqual(result["source_sha"], SHA)
            self.assertEqual(result["github_run_id"], "41647681783")
            self.assertEqual(result["status"], "review_pending")
            self.assertEqual(result["baseline"],
                             {"status": "not_supplied", "approved": False})
            for group in review.PANELS:
                file = out / ("review-" + group + ".jpg")
                self.assertTrue(file.is_file())
                with Image.open(file) as image:
                    self.assertGreaterEqual(image.width, 800)
            sample = "00-idle.png"
            self.assertEqual(
                result["evidence"][sample]["sha256"],
                hashlib.sha256((folder / sample).read_bytes()).hexdigest())
            self.assertIn("Keep the migration PR Draft",
                          (out / "README.md").read_text())
            self.assertEqual(json.loads((out / "review-manifest.json").read_text()),
                             result)
            with self.assertRaises(review.ReviewError):
                review.build(folder, out, SHA, "41647681783")

    def test_wrong_head_and_run_ids_rejected_before_any_outputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder, out = Path(tmp) / "capture", Path(tmp) / "review"
            capture_fixture(folder)
            for sha, run in [(SHA[:7], "42"), (SHA.upper(), "42"), (SHA, "0"),
                             (SHA, ""), (SHA, "1;rm -rf /")]:
                with self.subTest(sha=sha, run=run):
                    with self.assertRaises(review.ReviewError):
                        review.build(folder, out, sha, run)
                    self.assertFalse(out.exists())

    def test_missing_altered_or_wrong_viewport_png_blocks_review(self):
        for problem in ("missing", "corrupt", "dimensions"):
            with tempfile.TemporaryDirectory() as tmp:
                folder, out = Path(tmp) / "capture", Path(tmp) / "review"
                capture_fixture(folder)
                file = folder / "53-smg-run-fire-08.png"
                if problem == "missing":
                    file.unlink()
                elif problem == "corrupt":
                    file.write_bytes(b"not a png")
                else:
                    Image.new("RGB", (800, 600)).save(file)
                with self.subTest(problem=problem):
                    with self.assertRaises(review.ReviewError):
                        review.build(folder, out, SHA, "1")
                    self.assertFalse(out.exists())

    def test_missing_keyboard_frames_or_touch_proof_blocks_review(self):
        for fault in ("missing_run", "missing_traversal", "no_jump",
                      "no_landing", "short_jump", "no_touch",
                      "no_grenade", "mobile_errors"):
            with tempfile.TemporaryDirectory() as tmp:
                folder, out = Path(tmp) / "capture", Path(tmp) / "review"
                capture_fixture(folder)
                if fault in ("missing_run", "missing_traversal", "no_jump",
                             "no_landing", "short_jump"):
                    path = folder / "runtime-visual-health.json"
                    value = json.loads(path.read_text())
                    if fault == "missing_run":
                        value["captures"] = [x for x in value["captures"]
                                             if x["label"] != "10-run-07-closeup"]
                    elif fault == "missing_traversal":
                        value["stageOverviews"] = value["stageOverviews"][:1]
                    elif fault == "no_jump":
                        value["jumpProof"]["airborneAfter"] = 0
                    elif fault == "no_landing":
                        value["jumpProof"]["landedAfter"] = 0
                    elif fault == "short_jump":
                        value["jumpProof"]["minHeightPx"] = 20
                else:
                    path = folder / "mobile-web-smoke.json"
                    value = json.loads(path.read_text())
                    if fault == "no_touch":
                        value["phases"][1]["shots"] = 0
                    elif fault == "no_grenade":
                        value["phases"][2]["throws"] = 0
                    else:
                        value["pageErrors"] = ["fake JS crash"]
                path.write_text(json.dumps(value))
                with self.subTest(fault=fault), self.assertRaises(review.ReviewError):
                    review.build(folder, out, SHA, "42")
                self.assertFalse(out.exists())


if __name__ == "__main__":
    unittest.main()
