import os
import numpy as np
from PIL import Image
import pillow_heif
import cv2


def ensure_output_dir(path):
    os.makedirs(path, exist_ok=True)


def load_image_bgr(input_path):
    """
    Loads an image from any supported format into a BGR numpy array.
    Returns None on failure.
    """
    ext = os.path.splitext(input_path)[1].lower()
    try:
        if ext == '.heic':
            heif_file = pillow_heif.read_heif(input_path)
            img = Image.frombytes(heif_file.mode, heif_file.size, heif_file.data, "raw")
            if img.mode != "RGB":
                img = img.convert("RGB")
            return cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
        # cv2.imread handles JPG/PNG/TIFF natively
        return cv2.imread(input_path)
    except Exception as e:
        print(f"[ERROR] Could not load {input_path}: {e}")
        return None


def draw_detected_circle(image_bgr, circle, color=(0, 255, 0), thickness=None):
    """
    Returns a copy of image_bgr with the detected circle drawn on top.
    Stroke thickness defaults to ~0.5% of image diagonal for visibility on
    high-resolution inputs.
    """
    out = image_bgr.copy()
    if circle is None:
        return out
    x, y, r = circle
    if thickness is None:
        h, w = out.shape[:2]
        thickness = max(2, int(0.005 * (h ** 2 + w ** 2) ** 0.5))
    cv2.circle(out, (x, y), r, color, thickness)
    cv2.circle(out, (x, y), max(2, thickness), color, -1)  # centre dot
    return out


def _pixel_bounds(config, width):
    """
    Resolves the fraction-of-width config knobs to concrete pixel values
    for a given image width. Returns (min_dist, min_radius, max_radius).
    """
    min_radius = max(1, int(config['minRadius_frac'] * width))
    max_radius = max(min_radius + 1, int(config['maxRadius_frac'] * width))
    min_dist = max(1, int(config['minDist_frac'] * width))
    return min_dist, min_radius, max_radius


def detect_plate_circles(image, config):
    """
    Returns all plate-circle candidates from HoughCircles as a list of
    (x, y, r) tuples, ordered by accumulator strength (best first).
    Returns an empty list if no circles are found.

    minDist/minRadius/maxRadius are read from config as fractions of
    the input image's width, so the detector is resolution-independent.
    """
    h, w = image.shape[:2]
    min_dist, min_radius, max_radius = _pixel_bounds(config, w)

    # HoughCircles computes its own gradient via Canny using `param1` as the
    # upper threshold, so we just pass it the blurred grayscale. Running an
    # explicit equalizeHist + Canny ahead of it (the previous behaviour)
    # tended to produce noisier edges and was strictly slower.
    # The blur kernel and sigma are configurable: a wider blur smears out
    # thin bright artefacts (e.g. ring-light halos at the agar meniscus)
    # so Hough can lock onto the broader plastic-rim gradient instead.
    ksize = int(config.get('blur_ksize', 5))
    if ksize % 2 == 0:
        ksize += 1
    sigma = float(config.get('blur_sigma', 2))
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (ksize, ksize), sigma)
    circles = cv2.HoughCircles(
        blurred, cv2.HOUGH_GRADIENT,
        dp=config['dp'],
        minDist=min_dist,
        param1=config['param1'],
        param2=config['param2'],
        minRadius=min_radius,
        maxRadius=max_radius,
    )
    if circles is None:
        return []
    circles = np.uint16(np.around(circles))
    return [tuple(int(v) for v in c) for c in circles[0]]


def detect_plate_circle(image, config):
    """
    Detects a single circle. Kept for callers that only want the
    highest-accumulator candidate.
    """
    candidates = detect_plate_circles(image, config)
    return candidates[0] if candidates else None


def detect_plate_circle_downscaled(image_bgr, config, resize_factor=0.25):
    """
    Detects the plate circle on a downscaled copy of an already-decoded
    BGR numpy image. Returns (x, y, r) in the original image's coordinates,
    or None if no circle is found.

    Candidates are first filtered to those whose centre lies within
    config['center_tolerance_frac'] * image_width of the image centre,
    which eliminates obvious non-plate circles (lens vignettes, table
    edges) regardless of how strong their Hough accumulator was. Among
    survivors, the one with the highest Hough accumulator wins -- this
    keeps the actual plate even when it is off-centre, provided it
    falls inside the tolerance disc. If nothing survives the filter, the
    function falls back to the closest-to-centre candidate.

    config['radius_pad_pct'] (default 0.0) grows the final radius by the
    given fraction, useful if HoughCircles consistently latches onto the
    inner agar rim instead of the outer plate edge.
    """
    h, w = image_bgr.shape[:2]
    new_w = max(1, int(w * resize_factor))
    new_h = max(1, int(h * resize_factor))
    small = cv2.resize(image_bgr, (new_w, new_h), interpolation=cv2.INTER_AREA)

    # No manual rescale: minDist/min/maxRadius are fractions of width, so
    # they auto-adapt to whatever image size we pass in.
    candidates = detect_plate_circles(small, config)
    if not candidates:
        return None

    # Two-stage selection:
    #   1. Drop candidates whose centre is more than center_tolerance_frac
    #      * width from the image centre -- these are almost certainly not
    #      plates (table edges, lens vignette, etc.).
    #   2. Among survivors, take the highest-accumulator candidate (the one
    #      HoughCircles ranked first).
    # If nothing survives the filter, fall back to closest-to-centre as a
    # best-effort guess.
    cx, cy = new_w / 2.0, new_h / 2.0
    tol_frac = float(config.get('center_tolerance_frac', 0.25))
    tol_sq = (tol_frac * new_w) ** 2
    survivors = [c for c in candidates
                 if (c[0] - cx) ** 2 + (c[1] - cy) ** 2 <= tol_sq]
    if survivors:
        best = survivors[0]
    else:
        best = min(candidates, key=lambda c: (c[0] - cx) ** 2 + (c[1] - cy) ** 2)

    x, y, r = best
    scale = 1.0 / resize_factor
    pad = float(config.get('radius_pad_pct', 0.0))
    return (int(x * scale), int(y * scale), int(r * scale * (1.0 + pad)))

def crop_plate(image, circle):
    """
    Crops the image to the bounding box of the detected circle.
    """
    x, y, r = circle
    x1, y1 = max(0, x - r), max(0, y - r)
    x2, y2 = min(image.shape[1], x + r), min(image.shape[0], y + r)
    return image[y1:y2, x1:x2]

def mask_to_circle(image):
    """
    Masks the image to a circle (sets outside to black).
    """
    h, w = image.shape[:2]
    mask = np.zeros((h, w), dtype=np.uint8)
    cv2.circle(mask, (w // 2, h // 2), min(h, w) // 2, 255, -1)
    result = cv2.bitwise_and(image, image, mask=mask)
    return result