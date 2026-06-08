"""
Generate tests/fixtures/expected_circles.csv from the current
CIRCLE_DETECTION_CONFIG run against the images in local_data/raw_pictures/.

This is a one-shot calibration step. The values it writes become the
"expected" baseline for the regression test in
tests/test_circle_detection.py. Re-run this script any time you
intentionally retune CIRCLE_DETECTION_CONFIG.

For each image, the script also writes a thumbnail with the detected
circle drawn on top to tests/fixtures/overlays/, so you can visually
verify each detection before trusting the baseline.

Usage:
    python tools/calibrate.py
"""
import csv
import os
import sys

# Make `from config import ...` work when run from the repo root or elsewhere.
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
sys.path.insert(0, ROOT)

import cv2
from config import RAW_DIR, SUPPORTED_FORMATS, CIRCLE_DETECTION_CONFIG
from utils.image_utils import (
    detect_plate_circle_downscaled, draw_detected_circle, load_image_bgr,
)

FIXTURES_DIR = os.path.join(ROOT, 'tests', 'fixtures')
EXPECTED_CSV = os.path.join(FIXTURES_DIR, 'expected_circles.csv')
OVERLAYS_DIR = os.path.join(FIXTURES_DIR, 'overlays')

OVERLAY_LONG_EDGE = 800  # px; keep overlays small enough to eyeball quickly


def _thumbnail(image_bgr, long_edge=OVERLAY_LONG_EDGE):
    h, w = image_bgr.shape[:2]
    scale = long_edge / max(h, w)
    if scale >= 1.0:
        return image_bgr
    return cv2.resize(image_bgr, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)


def main():
    os.makedirs(FIXTURES_DIR, exist_ok=True)
    os.makedirs(OVERLAYS_DIR, exist_ok=True)

    if not os.path.isdir(RAW_DIR):
        print(f"[ERROR] Raw directory not found: {RAW_DIR}", file=sys.stderr)
        sys.exit(1)

    files = sorted(
        fname for fname in os.listdir(RAW_DIR)
        if os.path.isfile(os.path.join(RAW_DIR, fname)) and fname.lower().endswith(SUPPORTED_FORMATS)
    )
    if not files:
        print(f"[ERROR] No supported images found in {RAW_DIR}.", file=sys.stderr)
        sys.exit(1)

    rows = []
    failures = []
    for fname in files:
        path = os.path.join(RAW_DIR, fname)
        print(f"[INFO] {fname}: ", end='', flush=True)
        image = load_image_bgr(path)
        if image is None:
            print("LOAD FAILED")
            failures.append(fname)
            continue
        circle = detect_plate_circle_downscaled(image, CIRCLE_DETECTION_CONFIG, resize_factor=0.25)
        if circle is None:
            print("NO CIRCLE DETECTED")
            failures.append(fname)
            # Still save a thumbnail of the raw image so it's easy to see why
            cv2.imwrite(os.path.join(OVERLAYS_DIR, f"{fname}.jpg"), _thumbnail(image))
            continue
        x, y, r = circle
        rows.append({'filename': fname, 'x': x, 'y': y, 'r': r})
        print(f"x={x} y={y} r={r}")

        overlay = draw_detected_circle(image, circle)
        cv2.imwrite(os.path.join(OVERLAYS_DIR, f"{fname}.jpg"), _thumbnail(overlay))

    if not rows:
        print("[ERROR] No circles detected on any image; not writing expected_circles.csv.", file=sys.stderr)
        sys.exit(1)

    with open(EXPECTED_CSV, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=['filename', 'x', 'y', 'r'])
        writer.writeheader()
        writer.writerows(rows)

    print()
    print(f"[INFO] Wrote {len(rows)} rows to {EXPECTED_CSV}")
    print(f"[INFO] Overlays saved to {OVERLAYS_DIR}/ -- open them to verify each detection.")
    if failures:
        print(f"[WARN] {len(failures)} image(s) had no detection: {', '.join(failures)}")
        sys.exit(2)


if __name__ == "__main__":
    main()
