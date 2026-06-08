import os
import sys
import time
import cv2
import pandas as pd
import logging
from collections import Counter
from datetime import datetime
from concurrent.futures import ProcessPoolExecutor, as_completed
from config import (
    SUPPORTED_FORMATS, DEFAULT_OUTPUT_EXT, DATA_DIR, RAW_DIR, RESIZE_FACTOR,
    CROPPED_DIR, MANIFESTS_DIR, CIRCLE_DETECTION_CONFIG, THREADS,
    init_manifest, log_action,
)
from utils.image_utils import (
    ensure_output_dir, load_image_bgr,
    detect_plate_circle_downscaled, crop_plate, mask_to_circle,
    draw_detected_circle,
)

DEBUG_DIR = os.path.join(DATA_DIR, 'debug')
DEBUG_OVERLAY_LONG_EDGE = 800

logging.basicConfig(
    level=logging.INFO,
    format='[%(levelname)s] %(message)s'
)


def load_rename_map(rename_csv):
    """
    Loads the rename matrix CSV. The CSV is required.

    Hard-errors (sys.exit) if the file is missing or malformed.
    Returns a dict mapping lowercased old_name -> new_name.
    """
    rename_csv_path = os.path.join(DATA_DIR, rename_csv)
    if not os.path.isfile(rename_csv_path):
        logging.error(f"Rename CSV not found: {rename_csv_path}")
        sys.exit(1)

    try:
        df = pd.read_csv(rename_csv_path)
    except Exception as e:
        logging.error(f"Could not read rename CSV {rename_csv_path}: {e}")
        sys.exit(1)

    if not {'old_name', 'new_name'}.issubset(df.columns):
        logging.error(
            f"Rename CSV {rename_csv_path} is missing required columns "
            f"'old_name' and/or 'new_name'."
        )
        sys.exit(1)

    rename_map = {
        str(row['old_name']).lower(): str(row['new_name'])
        for _, row in df.iterrows()
    }
    logging.info(f"Loaded rename matrix with {len(rename_map)} entries.")
    return rename_map


def _write_debug_overlay(image_bgr, circle, debug_path):
    h, w = image_bgr.shape[:2]
    scale = DEBUG_OVERLAY_LONG_EDGE / max(h, w)
    overlay = draw_detected_circle(image_bgr, circle)
    if scale < 1.0:
        overlay = cv2.resize(overlay, (int(w * scale), int(h * scale)),
                             interpolation=cv2.INTER_AREA)
    cv2.imwrite(debug_path, overlay)


def process_image(image_path, rename_map, debug=False):
    """
    Processes a single image: decodes the raw image into memory, detects
    the plate circle, crops, masks, and writes the final cropped TIFF.
    No intermediate file is written to disk.

    Pure worker function: performs no logging or shared-state writes so it
    can run in a process pool. Returns (outcome, events) where outcome is
    one of {'ok', 'skipped', 'failed'} and events is a list of tuples
    (filename, stage, status, message, duration_ms) suitable for log_action.

    If debug is True, a thumbnail with the detected circle drawn on top is
    written to local_data/debug/<new_name>.jpg.
    """
    original_name = os.path.basename(image_path)
    file_stem, _ = os.path.splitext(original_name)
    events = []

    new_name = rename_map.get(file_stem.lower())
    if not new_name:
        events.append((original_name, 'rename_lookup', 'skipped',
                       f"No rename entry for '{file_stem}'", None))
        return 'skipped', events

    new_filename = f"{new_name}.{DEFAULT_OUTPUT_EXT}"

    ensure_output_dir(CROPPED_DIR)
    cropped_path = os.path.join(CROPPED_DIR, new_filename)

    if os.path.exists(cropped_path):
        events.append((original_name, 'crop', 'skipped',
                       'output already exists', None))
        return 'ok', events

    # Step 1: Decode the raw image into a BGR numpy array.
    t0 = time.perf_counter()
    image = load_image_bgr(image_path)
    dt = (time.perf_counter() - t0) * 1000.0
    if image is None:
        events.append((original_name, 'decode', 'failed',
                       f"could not load {image_path}", dt))
        return 'failed', events
    events.append((original_name, 'decode', 'ok',
                   f"{image.shape[1]}x{image.shape[0]}", dt))

    # Step 2: Detect plate circle, crop, mask, write.
    t0 = time.perf_counter()
    circle = detect_plate_circle_downscaled(image, CIRCLE_DETECTION_CONFIG, resize_factor=RESIZE_FACTOR)
    if circle is None:
        dt = (time.perf_counter() - t0) * 1000.0
        if debug:
            ensure_output_dir(DEBUG_DIR)
            _write_debug_overlay(image, None, os.path.join(DEBUG_DIR, f"{new_name}.jpg"))
        events.append((original_name, 'crop', 'failed',
                       f"no circular plate detected in {new_filename}", dt))
        return 'failed', events

    if debug:
        ensure_output_dir(DEBUG_DIR)
        _write_debug_overlay(image, circle, os.path.join(DEBUG_DIR, f"{new_name}.jpg"))

    cropped = crop_plate(image, circle)
    masked = mask_to_circle(cropped)
    cv2.imwrite(cropped_path, masked)
    dt = (time.perf_counter() - t0) * 1000.0
    events.append((original_name, 'crop', 'ok',
                   f"x={circle[0]} y={circle[1]} r={circle[2]}", dt))
    return 'ok', events


def batch_process(rename_csv, max_workers=THREADS, debug=False):
    logging.info("Starting batch processing...")
    if debug:
        logging.info(f"Debug overlays will be written to {DEBUG_DIR}/")

    if not os.path.exists(RAW_DIR):
        logging.error(f"Input folder '{RAW_DIR}' does not exist.")
        sys.exit(1)

    rename_map = load_rename_map(rename_csv)

    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    manifest_path = os.path.join(MANIFESTS_DIR, f"run_{run_id}.csv")
    init_manifest(manifest_path)
    logging.info(f"Manifest: {manifest_path}")

    file_paths = [
        os.path.join(RAW_DIR, fname)
        for fname in os.listdir(RAW_DIR)
        if os.path.isfile(os.path.join(RAW_DIR, fname)) and fname.lower().endswith(SUPPORTED_FORMATS)
    ]
    logging.info(f"Found {len(file_paths)} supported image files.")

    outcomes = Counter()
    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(process_image, fp, rename_map, debug): fp for fp in file_paths}
        for future in as_completed(futures):
            fp = futures[future]
            original_name = os.path.basename(fp)
            try:
                outcome, events = future.result()
            except Exception as e:
                logging.error(f"Exception in file {fp}: {e}")
                log_action(manifest_path, original_name, 'batch', 'failed',
                           f"unhandled exception: {e}")
                outcomes['failed'] += 1
                continue

            for ev in events:
                log_action(manifest_path, *ev)

            if outcome == 'ok':
                logging.info(f"Done: {original_name}")
            elif outcome == 'skipped':
                logging.warning(f"Skipped: {original_name}")
            else:
                logging.error(f"Failed: {original_name}")
            outcomes[outcome] += 1

    logging.info(
        f"Batch complete. ok={outcomes['ok']} skipped={outcomes['skipped']} "
        f"failed={outcomes['failed']} (manifest: {manifest_path})"
    )


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Batch process growth profiling images.")
    parser.add_argument("--rename-csv", type=str, default="rename_matrix.csv",
                        help="CSV file (in local_data/) for renaming images. Required.")
    parser.add_argument("--max-workers", type=int, default=THREADS,
                        help="Number of parallel workers (default: all cores)")
    parser.add_argument("--debug", action="store_true",
                        help="Write a thumbnail with the detected circle drawn on top to local_data/debug/.")
    args = parser.parse_args()

    batch_process(rename_csv=args.rename_csv, max_workers=args.max_workers, debug=args.debug)
