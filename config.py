import os
import csv

# ---- System settings ----
THREADS = os.cpu_count() or 1  # Use all available cores, default to 1 if not available

# ---- Supported Formats ----
SUPPORTED_FORMATS = ('.png', '.jpg', '.jpeg', '.tiff', '.heic')
DEFAULT_OUTPUT_EXT = 'tiff'

# ---- Circle detection settings ----
RESIZE_FACTOR = 0.25

CIRCLE_DETECTION_CONFIG = {
    'dp': 1.5,              # How much to reduce the image resolution for detection (higher = faster, less precise)
    'param1': 100,          # Sensitivity for finding edges in the image (higher = fewer edges detected)
    'param2': 40,           # How strong a circle needs to be to count as a real circle (lower = more circles found, but more false ones)
    # The next three are expressed as a fraction of the image width so the
    # detector is resolution-independent. On a 4032 px wide image
    # (iPhone HEIC default) these correspond to minDist=484, minRadius=847,
    # maxRadius=1210 px, matching the previously hand-tuned absolute values.
    'minDist_frac':   0.12,
    'minRadius_frac': 0.18,
    'maxRadius_frac': 0.38,
    'radius_pad_pct': 0.0,         # Grow the detected radius by this fraction. Useful if HoughCircles latches onto the inner agar rim.
    'center_tolerance_frac': 0.1, # Max allowed distance of plate centre from image centre, as a fraction of image width. Candidates outside this disc are dropped before accumulator-based selection (kills table edges, lens vignette rings). Raise it if your plates are very off-centre.
    # Pre-Hough Gaussian blur. Higher values smear out thin bright rings
    # (e.g. a ring-light halo at the agar meniscus) so Hough can lock onto
    # the wider plastic-rim gradient instead. Must be odd.
    'blur_ksize': 15,
    'blur_sigma': 5,
}

# ---- Paths ----
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'local_data')
RAW_DIR = os.path.join(DATA_DIR, 'raw_pictures')
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
