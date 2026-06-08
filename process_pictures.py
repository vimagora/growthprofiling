import os
import sys
import cv2
import pandas as pd
import logging
from concurrent.futures import ThreadPoolExecutor
from config import (
    SUPPORTED_FORMATS, DEFAULT_OUTPUT_EXT, DATA_DIR, RAW_DIR, CONVERTED_DIR,
    CROPPED_DIR, CIRCLE_DETECTION_CONFIG, THREADS
)
from utils.image_utils import (
    convert_to_tiff, ensure_output_dir,
    detect_plate_circle_fast, crop_plate, mask_to_circle
)

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


def process_image(image_path, rename_map):
    """
    Processes a single image: converts (saving directly with the new name),
    detects the plate circle, crops, and masks.

    Files whose stem is not present in rename_map are skipped with a warning.
    """
    original_name = os.path.basename(image_path)
    file_stem, _ = os.path.splitext(original_name)
    logging.info(f"Processing: {original_name}")

    new_name = rename_map.get(file_stem.lower())
    if not new_name:
        logging.warning(f"No rename entry for '{file_stem}'. Skipping.")
        return

    new_filename = f"{new_name}.{DEFAULT_OUTPUT_EXT}"

    # Step 1: Convert to TIFF, saved directly under the new name.
    ensure_output_dir(CONVERTED_DIR)
    converted_path = os.path.join(CONVERTED_DIR, new_filename)

    if not os.path.exists(converted_path):
        result = convert_to_tiff(image_path, CONVERTED_DIR, output_stem=new_name)
        if not result:
            logging.error(f"Conversion failed for {original_name}. Skipping.")
            return
    else:
        logging.debug(f"Already exists: {converted_path}")

    # Step 2: Circle detection, crop, and mask.
    ensure_output_dir(CROPPED_DIR)
    cropped_path = os.path.join(CROPPED_DIR, new_filename)

    if os.path.exists(cropped_path):
        logging.debug(f"Already exists: {cropped_path}")
        return

    logging.info("Starting circle detection...")
    image = cv2.imread(converted_path)
    if image is None:
        logging.error(f"Could not load converted image for cropping: {converted_path}")
        return

    circle = detect_plate_circle_fast(converted_path, CIRCLE_DETECTION_CONFIG, jpeg_resize_factor=0.25)
    if circle is None:
        logging.warning(f"No circular plate detected in {new_filename}.")
        return

    cropped = crop_plate(image, circle)
    masked = mask_to_circle(cropped)
    cv2.imwrite(cropped_path, masked)
    logging.info(f"Cropped circular region saved: {new_filename}")


def batch_process(rename_csv, max_workers=THREADS):
    logging.info("Starting batch processing...")

    if not os.path.exists(RAW_DIR):
        logging.error(f"Input folder '{RAW_DIR}' does not exist.")
        sys.exit(1)

    rename_map = load_rename_map(rename_csv)

    file_paths = [
        os.path.join(RAW_DIR, fname)
        for fname in os.listdir(RAW_DIR)
        if os.path.isfile(os.path.join(RAW_DIR, fname)) and fname.lower().endswith(SUPPORTED_FORMATS)
    ]
    logging.info(f"Found {len(file_paths)} supported image files.")

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(process_image, fp, rename_map) for fp in file_paths]
        for i, future in enumerate(futures):
            try:
                future.result()
            except Exception as e:
                logging.error(f"Exception in file {file_paths[i]}: {e}")

    logging.info("Batch processing complete.")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Batch process growth profiling images.")
    parser.add_argument("--rename-csv", type=str, default="rename_matrix.csv",
                        help="CSV file (in local_data/) for renaming images. Required.")
    parser.add_argument("--max-workers", type=int, default=THREADS,
                        help="Number of parallel workers (default: all cores)")
    args = parser.parse_args()

    batch_process(rename_csv=args.rename_csv, max_workers=args.max_workers)
