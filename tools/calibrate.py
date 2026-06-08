"""
Generate tests/fixtures/expected_circles.csv from the current
CIRCLE_DETECTION_CONFIG run against the images in local_data/raw_pictures/.

This is a one-shot calibration step. The values it writes become the
"expected" baseline for the regression test in
tests/test_circle_detection.py. Re-run this script any time you
intentionally retune CIRCLE_DETECTION_CONFIG.

For each image, the script also writes a thumbnail to
tests/fixtures/overlays/ with:
  * The picked circle drawn in GREEN
  * All other Hough candidates drawn in RED
  * The image centre marked, plus a magenta dashed disc showing the
    center_tolerance_frac filter
  * A short stats line in the corner.

This lets you tell at a glance whether Hough found the real plate but
picked the wrong candidate (a selection-logic problem) vs. Hough never
found the real plate to begin with (a detection-parameter problem).

Usage:
    python tools/calibrate.py
"""
import csv
import math
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
sys.path.insert(0, ROOT)

import cv2
from config import RAW_DIR, SUPPORTED_FORMATS, CIRCLE_DETECTION_CONFIG
from utils.image_utils import (
    _pixel_bounds, detect_plate_circles, load_image_bgr,
)

FIXTURES_DIR = os.path.join(ROOT, 'tests', 'fixtures')
EXPECTED_CSV = os.path.join(FIXTURES_DIR, 'expected_circles.csv')
OVERLAYS_DIR = os.path.join(FIXTURES_DIR, 'overlays')

OVERLAY_LONG_EDGE = 800
RESIZE_FACTOR = 0.25  # must match detect_plate_circle_downscaled's default


def _thumbnail(image_bgr, long_edge=OVERLAY_LONG_EDGE):
    h, w = image_bgr.shape[:2]
    scale = long_edge / max(h, w)
    if scale >= 1.0:
        return image_bgr, 1.0
    return cv2.resize(image_bgr, (int(w * scale), int(h * scale)),
                      interpolation=cv2.INTER_AREA), scale


def _select(candidates, image_width, image_height, config):
    """
    Returns (picked_candidate, came_from_survivors_bool) using the same
    rules as detect_plate_circle_downscaled. Returns (None, False) if
    candidates is empty.
    """
    if not candidates:
        return None, False
    cx, cy = image_width / 2.0, image_height / 2.0
    tol_frac = float(config.get('center_tolerance_frac', 0.25))
    tol_sq = (tol_frac * image_width) ** 2
    survivors = [c for c in candidates
                 if (c[0] - cx) ** 2 + (c[1] - cy) ** 2 <= tol_sq]
    if survivors:
        return survivors[0], True
    return min(candidates, key=lambda c: (c[0] - cx) ** 2 + (c[1] - cy) ** 2), False


def _draw_overlay(image_bgr, candidates, picked, config):
    """
    Draws all candidates (red), the picked one (green), the image centre
    (yellow cross), and the centre-tolerance disc (magenta).
    """
    out = image_bgr.copy()
    h, w = out.shape[:2]
    cx, cy = w // 2, h // 2

    diag = math.hypot(h, w)
    thickness = max(2, int(0.004 * diag))

    # Centre-tolerance disc
    tol_frac = float(config.get('center_tolerance_frac', 0.25))
    cv2.circle(out, (cx, cy), int(tol_frac * w), (255, 0, 255), thickness)

    # Image centre cross
    cross = max(20, int(0.02 * diag))
    cv2.line(out, (cx - cross, cy), (cx + cross, cy), (0, 255, 255), thickness)
    cv2.line(out, (cx, cy - cross), (cx, cy + cross), (0, 255, 255), thickness)

    for c in candidates:
        color = (0, 255, 0) if c == picked else (0, 0, 255)
        x, y, r = c
        cv2.circle(out, (x, y), r, color, thickness)
        cv2.circle(out, (x, y), thickness, color, -1)

    return out


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

    pad = float(CIRCLE_DETECTION_CONFIG.get('radius_pad_pct', 0.0))
    scale_up = 1.0 / RESIZE_FACTOR

    rows = []
    failures = []
    for fname in files:
        path = os.path.join(RAW_DIR, fname)
        image = load_image_bgr(path)
        if image is None:
            print(f"[INFO] {fname}: LOAD FAILED")
            failures.append(fname)
            continue

        h, w = image.shape[:2]
        new_w = max(1, int(w * RESIZE_FACTOR))
        new_h = max(1, int(h * RESIZE_FACTOR))
        small = cv2.resize(image, (new_w, new_h), interpolation=cv2.INTER_AREA)

        _, min_r, max_r = _pixel_bounds(CIRCLE_DETECTION_CONFIG, w)
        small_candidates = detect_plate_circles(small, CIRCLE_DETECTION_CONFIG)
        picked_small, in_tolerance = _select(small_candidates, new_w, new_h, CIRCLE_DETECTION_CONFIG)

        cx_full, cy_full = w / 2.0, h / 2.0
        print(f"[INFO] {fname}: {w}x{h}, radius bounds=[{min_r},{max_r}]px, "
              f"{len(small_candidates)} candidate(s)")
        for i, c in enumerate(small_candidates):
            x_full = int(c[0] * scale_up)
            y_full = int(c[1] * scale_up)
            r_full = int(c[2] * scale_up)
            dist = math.hypot(x_full - cx_full, y_full - cy_full)
            marker = " <- picked" if c == picked_small else ""
            print(f"          [{i}] x={x_full} y={y_full} r={r_full} "
                  f"dist_from_centre={int(dist)}px{marker}")

        if picked_small is None:
            print(f"          -> NO CIRCLE DETECTED")
            failures.append(fname)
            overlay = _draw_overlay(image, [], None, CIRCLE_DETECTION_CONFIG)
            thumb, _ = _thumbnail(overlay)
            cv2.imwrite(os.path.join(OVERLAYS_DIR, f"{fname}.jpg"), thumb)
            continue

        # Map all candidates back to full-image coordinates for the overlay.
        full_candidates = [
            (int(c[0] * scale_up), int(c[1] * scale_up), int(c[2] * scale_up * (1.0 + pad)))
            for c in small_candidates
        ]
        picked_full = (
            int(picked_small[0] * scale_up),
            int(picked_small[1] * scale_up),
            int(picked_small[2] * scale_up * (1.0 + pad)),
        )

        rows.append({
            'filename': fname,
            'x': picked_full[0],
            'y': picked_full[1],
            'r': picked_full[2],
        })
        note = "in tolerance" if in_tolerance else "FALLBACK to closest-to-centre"
        print(f"          -> picked x={picked_full[0]} y={picked_full[1]} r={picked_full[2]} ({note})")

        overlay = _draw_overlay(image, full_candidates, picked_full, CIRCLE_DETECTION_CONFIG)
        thumb, _ = _thumbnail(overlay)
        cv2.imwrite(os.path.join(OVERLAYS_DIR, f"{fname}.jpg"), thumb)

    if not rows:
        print("[ERROR] No circles detected on any image; not writing expected_circles.csv.", file=sys.stderr)
        sys.exit(1)

    with open(EXPECTED_CSV, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=['filename', 'x', 'y', 'r'])
        writer.writeheader()
        writer.writerows(rows)

    print()
    print(f"[INFO] Wrote {len(rows)} rows to {EXPECTED_CSV}")
    print(f"[INFO] Overlays saved to {OVERLAYS_DIR}/ -- green = picked, red = other candidates, "
          f"magenta = centre tolerance, yellow = image centre.")
    if failures:
        print(f"[WARN] {len(failures)} image(s) had no detection: {', '.join(failures)}")
        sys.exit(2)


if __name__ == "__main__":
    main()
