"""
Regression tests for circle detection.

Two layers:

  * test_synthetic_circle: a synthetic black-circle-on-white image. Always
    runs. Catches gross breakage (import errors, wildly off detection).

  * test_fixture_images: loops over tests/fixtures/expected_circles.csv,
    which is populated by tools/calibrate.py against the user's own
    images. Skipped cleanly if the fixture CSV doesn't exist. Asserts
    detection matches the recorded (x, y, r) within tolerance.
"""
import csv
import os
import sys
import unittest

import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
sys.path.insert(0, ROOT)

import cv2  # noqa: E402
from config import RAW_DIR, CIRCLE_DETECTION_CONFIG  # noqa: E402
from utils.image_utils import detect_plate_circle_downscaled, load_image_bgr  # noqa: E402

FIXTURES_DIR = os.path.join(ROOT, 'tests', 'fixtures')
EXPECTED_CSV = os.path.join(FIXTURES_DIR, 'expected_circles.csv')

# Pixel tolerance for the regression test. Hough output can shift a few
# pixels between runs as the downscale path moves; 25 px is well within
# what matters for crop quality on ~5000 px wide originals.
CENTER_TOLERANCE_PX = 25
RADIUS_TOLERANCE_PX = 25


def _synthetic_plate_image(width=4000, height=3000, center=(2000, 1500), radius=1000):
    """White background with a single filled black circle."""
    img = np.full((height, width, 3), 255, dtype=np.uint8)
    cv2.circle(img, center, radius, (0, 0, 0), thickness=-1)
    return img


class CircleDetectionSmokeTest(unittest.TestCase):
    """Always-on test: synthetic image with a known circle."""

    def test_synthetic_circle(self):
        cx, cy, r = 2000, 1500, 1000
        img = _synthetic_plate_image(center=(cx, cy), radius=r)
        circle = detect_plate_circle_downscaled(img, CIRCLE_DETECTION_CONFIG, resize_factor=0.25)
        self.assertIsNotNone(circle, "No circle detected on synthetic image")
        x, y, det_r = circle
        self.assertAlmostEqual(x, cx, delta=CENTER_TOLERANCE_PX)
        self.assertAlmostEqual(y, cy, delta=CENTER_TOLERANCE_PX)
        self.assertAlmostEqual(det_r, r, delta=RADIUS_TOLERANCE_PX)


def _load_expected_rows():
    if not os.path.isfile(EXPECTED_CSV):
        return None
    with open(EXPECTED_CSV, newline='') as f:
        return list(csv.DictReader(f))


class CircleDetectionRegressionTest(unittest.TestCase):
    """
    Per-fixture regression test. Each row in expected_circles.csv becomes
    one assertion: detection on the raw image must produce (x, y, r)
    within tolerance of the recorded values.
    """

    @classmethod
    def setUpClass(cls):
        cls.rows = _load_expected_rows()
        if cls.rows is None:
            raise unittest.SkipTest(
                f"No expected_circles.csv at {EXPECTED_CSV}. "
                f"Run `python tools/calibrate.py` to populate it."
            )

    def test_each_fixture(self):
        failures = []
        for row in self.rows:
            fname = row['filename']
            expected = (int(row['x']), int(row['y']), int(row['r']))
            with self.subTest(filename=fname):
                path = os.path.join(RAW_DIR, fname)
                self.assertTrue(os.path.isfile(path),
                                f"Fixture image missing: {path}")
                image = load_image_bgr(path)
                self.assertIsNotNone(image, f"Could not load {path}")
                circle = detect_plate_circle_downscaled(
                    image, CIRCLE_DETECTION_CONFIG, resize_factor=0.25,
                )
                self.assertIsNotNone(circle, f"No circle detected in {fname}")
                x, y, r = circle
                ex, ey, er = expected
                self.assertAlmostEqual(x, ex, delta=CENTER_TOLERANCE_PX,
                                       msg=f"{fname}: x off (got {x}, expected {ex})")
                self.assertAlmostEqual(y, ey, delta=CENTER_TOLERANCE_PX,
                                       msg=f"{fname}: y off (got {y}, expected {ey})")
                self.assertAlmostEqual(r, er, delta=RADIUS_TOLERANCE_PX,
                                       msg=f"{fname}: r off (got {r}, expected {er})")

        if failures:
            self.fail("\n".join(failures))


if __name__ == "__main__":
    unittest.main()
