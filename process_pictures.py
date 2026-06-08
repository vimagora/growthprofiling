import os
import sys
import time
import threading
import cv2
import pandas as pd
import logging
from collections import Counter
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from config import (
    SUPPORTED_FORMATS, DEFAULT_OUTPUT_EXT, DATA_DIR, RAW_DIR, CONVERTED_DIR,
    CROPPED_DIR, MANIFESTS_DIR, CIRCLE_DETECTION_CONFIG, THREADS,
    init_manifest, log_action,
)
from utils.image_utils import (
    convert_to_tiff, ensure_output_dir,
    detect_plate_circle_fast, crop_plate, mask_to_circle
)

logging.basicConfig(
    level=logging.INFO,
    format='[%(levelname)s] %(message)s'
)

_MANIFEST_LOCK = threading.Lock()


def _log(manifest_path, filename, stage, status, message='', duration_ms=None):
    with _MANIFEST_LOCK:
        log_action(manifest_path, filename, stage, status, message, duration_ms)


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


def process_image(image_path, rename_map, manifest_path):
    """
    Processes a single image: converts (saving directly with the new name),
    detects the plate circle, crops, and masks.

    Returns a short outcome string: 'ok', 'skipped', or 'failed'.
    """
    original_name = os.path.basename(image_path)
    file_stem, _ = os.path.splitext(original_name)
    logging.info(f"Processing: {original_name}")

    new_name = rename_map.get(file_stem.lower())
    if not new_name:
        msg = f"No rename entry for '{file_stem}'"
        logging.warning(f"{msg}. Skipping.")
        _log(manifest_path, original_name, 'rename_lookup', 'skipped', msg)
        return 'skipped'

    new_filename = f"{new_name}.{DEFAULT_OUTPUT_EXT}"

    # Step 1: Convert to TIFF, saved directly under the new name.
    ensure_output_dir(CONVERTED_DIR)
    converted_path = os.path.join(CONVERTED_DIR, new_filename)

    if not os.path.exists(converted_path):
        t0 = time.perf_counter()
        result = convert_to_tiff(image_path, CONVERTED_DIR, output_stem=new_name)
        dt = (time.perf_counter() - t0) * 1000.0
        if not result:
            logging.error(f"Conversion failed for {original_name}.")
            _log(manifest_path, original_name, 'convert', 'failed', 'convert_to_tiff returned None', dt)
            return 'failed'
        _log(manifest_path, original_name, 'convert', 'ok', new_filename, dt)
    else:
        logging.debug(f"Already exists: {converted_path}")
        _log(manifest_path, original_name, 'convert', 'skipped', 'output already exists')

    # Step 2: Circle detection, crop, and mask.
    ensure_output_dir(CROPPED_DIR)
    cropped_path = os.path.join(CROPPED_DIR, new_filename)

    if os.path.exists(cropped_path):
        logging.debug(f"Already exists: {cropped_path}")
        _log(manifest_path, original_name, 'crop', 'skipped', 'output already exists')
        return 'ok'

    logging.info("Starting circle detection...")
    t0 = time.perf_counter()
    image = cv2.imread(converted_path)
    if image is None:
        dt = (time.perf_counter() - t0) * 1000.0
        msg = f"Could not load converted image: {converted_path}"
        logging.error(msg)
        _log(manifest_path, original_name, 'crop', 'failed', msg, dt)
        return 'failed'

    circle = detect_plate_circle_fast(converted_path, CIRCLE_DETECTION_CONFIG, jpeg_resize_factor=0.25)
    if circle is None:
        dt = (time.perf_counter() - t0) * 1000.0
        msg = f"No circular plate detected in {new_filename}"
        logging.warning(msg + ".")
        _log(manifest_path, original_name, 'crop', 'failed', msg, dt)
        return 'failed'

    cropped = crop_plate(image, circle)
    masked = mask_to_circle(cropped)
    cv2.imwrite(cropped_path, masked)
    dt = (time.perf_counter() - t0) * 1000.0
    logging.info(f"Cropped circular region saved: {new_filename}")
    _log(manifest_path, original_name, 'crop', 'ok', f"x={circle[0]} y={circle[1]} r={circle[2]}", dt)
    return 'ok'


def batch_process(rename_csv, max_workers=THREADS):
    logging.info("Starting batch processing...")

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
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(process_image, fp, rename_map, manifest_path): fp
            for fp in file_paths
        }
        for future, fp in futures.items():
            try:
                outcomes[future.result()] += 1
            except Exception as e:
                logging.error(f"Exception in file {fp}: {e}")
                _log(manifest_path, os.path.basename(fp), 'batch', 'failed', f"unhandled exception: {e}")
                outcomes['failed'] += 1

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
    args = parser.parse_args()

    batch_process(rename_csv=args.rename_csv, max_workers=args.max_workers)
