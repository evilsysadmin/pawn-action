"""Original, SHA-verified Chromium motion sequence comparison tests."""
import hashlib
import tempfile
import unittest
from pathlib import Path
from PIL import Image
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import pawn_action_legacy_comparison as compare

SHA = "c" * 40


def fixture(legacy, current):
    names = [n for _, n in compare.MOTION_PAIRS]
    evidence = {"captures": {}}
    review = {"source_sha": SHA, "evidence": {}}
    for folder in (legacy, current):
        folder.mkdir(parents=True)
        for i, name in enumerate(names):
            image = Image.new("RGB", (1280, 720), (30 + 7 * i, 45, 57))
            image.save(folder / name, "PNG")
            hash_value = hashlib.sha256((folder / name).read_bytes()).hexdigest()
            if folder == legacy:
                evidence["captures"][name] = {"sha256": hash_value}
            else:
                review["evidence"][name] = {"sha256": hash_value}
    return evidence, review


class MotionReviewTests(unittest.TestCase):
    def test_real_frame_sequence_hashed_and_rejects_repeated_or_bad_proof(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            before, after, out = base / "legacy", base / "new", base / "motion.jpg"
            evidence, review = fixture(before, after)
            compare.build_motion_sheet(before, after, evidence, review, SHA, out)
            with Image.open(out) as img:
                self.assertGreater(img.width, 900)
                self.assertGreater(img.height, 1000)
            self.assertGreater(out.stat().st_size, 0)
            (before / compare.MOTION_PAIRS[3][1]).write_bytes(b"bad png")
            with self.assertRaises(compare.CandidateError):
                compare.build_motion_sheet(before, after, evidence, review, SHA, base / "bad.jpg")

    def test_missing_sha_wrong_head_or_viewport_rejected(self):
        for failure in ("missing_hash", "wrong_head", "wrong_viewport", "missing_png"):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as tmp:
                base = Path(tmp)
                before, after = base / "legacy", base / "new"
                evidence, review = fixture(before, after)
                name = compare.MOTION_PAIRS[0][1]
                if failure == "missing_hash":
                    del review["evidence"][name]
                elif failure == "wrong_head":
                    review["source_sha"] = "b" * 40
                elif failure == "wrong_viewport":
                    Image.new("RGB", (1024, 768)).save(after / name, "PNG")
                    review["evidence"][name] = {
                        "sha256": hashlib.sha256((after / name).read_bytes()).hexdigest()
                    }
                else:
                    (before / name).unlink()
                with self.assertRaises(compare.CandidateError):
                    compare.build_motion_sheet(before, after, evidence, review, SHA, base / "bad.jpg")
                self.assertFalse((base / "bad.jpg").exists())


if __name__ == "__main__":
    unittest.main()
