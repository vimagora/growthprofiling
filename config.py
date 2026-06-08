import os
import csv

# ---- System settings ----
THREADS = os.cpu_count() or 1  # Use all available cores, default to 1 if not available

# ---- Supported Formats ----
SUPPORTED_FORMATS = ('.png', '.jpg', '.jpeg', '.tiff', '.heic')
DEFAULT_OUTPUT_EXT = 'tiff'

# ---- Circle detection settings ----
CIRCLE_DETECTION_CONFIG = {
    'dp': 1.5,              # How much to reduce the image resolution for detection (higher = faster, less precise)
    'param1': 100,          # Sensitivity for finding edges in the image (higher = fewer edges detected)
    'param2': 30,           # How strong a circle needs to be to count as a real circle (lower = more circles found, but more false ones)
    # The next three are expressed as a fraction of the image width so the
    # detector is resolution-independent. On a 4032 px wide image
    # (iPhone HEIC default) these correspond to minDist=484, minRadius=847,
    # maxRadius=1210 px, matching the previously hand-tuned absolute values.
    'minDist_frac':   0.12,
    'minRadius_frac': 0.21,
    'maxRadius_frac': 0.30,
    'radius_pad_pct': 0.0,  # Grow the detected radius by this fraction. Useful if HoughCircles latches onto the inner agar rim.
}

# ---- Paths ----
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'local_data')
RAW_DIR = os.path.join(DATA_DIR, 'raw_pictures')
CONVERTED_DIR = os.path.join(DATA_DIR, 'converted_pictures')
CROPPED_DIR = os.path.join(DATA_DIR, 'cropped_pictures')
MANIFESTS_DIR = os.path.join(DATA_DIR, 'manifests')


# ---- Logs ----
MANIFEST_COLUMNS = ['filename', 'stage', 'status', 'message', 'duration_ms']


def init_manifest(log_file):
    """
    Create (or truncate) a manifest file and write the header row.
    """
    os.makedirs(os.path.dirname(log_file), exist_ok=True)
    with open(log_file, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(MANIFEST_COLUMNS)


def log_action(log_file, filename, stage, status, message='', duration_ms=None):
    with open(log_file, 'a', newline='') as f:
        writer = csv.writer(f)
        writer.writerow([
            filename,
            stage,
            status,
            message,
            '' if duration_ms is None else f"{duration_ms:.1f}",
        ])
