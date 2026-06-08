import os
import sys
import cv2
import pandas as pd
import logging
from concurrent.futures import ThreadPoolExecutor
from config import (
    SUPPORTED_FORMATS, DEFAULT_OUTPUT_EXT, DATA_DIR, RAW_DIR, CONVERTED_DIR,
    RENAMED_DIR, CROPPED_DIR, CIRCLE_DETECTION_CONFIG, THREADS
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
    Processes a single image: converts, renames, crops, and masks.

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

    # Step 1: Convert to TIFF (under original name, for backwards compatibility with PR #1).
    output_file = file_stem + '.' + DEFAULT_OUTPUT_EXT
    output_path = os.path.join(CONVERTED_DIR, output_file)
    ensure_output_dir(CONVERTED_DIR)

    if not os.path.exists(output_path):
        converted_path = convert_to_tiff(image_path, CONVERTED_DIR)
        if not converted_path:
            logging.error(f"Conversion failed for {original_name}. Skipping.")
            return
    else:
        converted_path = output_path
        logging.debug(f"Already exists: {output_path}")

    # Step 2: Rename
    new_path = os.path.join(RENAMED_DIR, new_filename)
    ensure_output_dir(RENAMED_DIR)

    if not os.path.exists(new_path):
        try:
            os.rename(converted_path, new_path)
            logging.info(f"Renamed to: {new_filename}")
        except Exception as e:
            logging.error(f"Could not rename file: {e}")
            return
    else:
        logging.debug(f"Already exists: {new_path}")

    # Step 3: Circle Detection, Crop and Mask
    cropped_path = os.path.join(CROPPED_DIR, new_filename)
    ensure_output_dir(CROPPED_DIR)

    if not os.path.exists(cropped_path):
        logging.info("Starting circle detection...")
        image = cv2.imread(new_path)
        if image is None:
            logging.error("Could not load image for cropping.")
            return

        # Use fast JPEG-based circle detection for speed
        circle = detect_plate_circle_fast(new_path, CIRCLE_DETECTION_CONFIG, jpeg_resize_factor=0.25)
        if circle is None:
            logging.warning("No circular plate detected.")
            return

        cropped = crop_plate(image, circle)
        masked = mask_to_circle(cropped)
        cv2.imwrite(cropped_path, masked)
        logging.info(f"Cropped circular region saved: {os.path.basename(cropped_path)}")
    else:
        logging.debug(f"Already exists: {cropped_path}")


def batch_process(rename_csv, max_workers=THREADS):
    logging.info("Starting batch processing...")

    if not os.path.exists(RAW_DIR):
        logging.error(f"Input folder '{RAW_DIR}' does not exist.")
        sys.exit(1)

    rename_map = load_rename_map(rename_csv)

    # Gather all valid image files
    file_paths = [
        os.path.join(RAW_DIR, fname)
        for fname in os.listdir(RAW_DIR)
        if os.path.isfile(os.path.join(RAW_DIR, fname)) and fname.lower().endswith(SUPPORTED_FORMATS)
    ]
    logging.info(f"Found {len(file_paths)} supported image files.")

    # Process images in parallel
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
