import os
import numpy as np
from PIL import Image
import pillow_heif
import cv2
from config import DEFAULT_OUTPUT_EXT

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


def convert_to_tiff(input_path, output_dir, output_ext=DEFAULT_OUTPUT_EXT, output_stem=None):
    """
    Converts an image to TIFF format. Handles HEIC and general formats.

    If output_stem is provided, the converted file is written as
    '<output_stem>.<output_ext>'; otherwise the input file stem is used.
    """
    base_name = os.path.basename(input_path)
    file_name, ext = os.path.splitext(base_name)
    ext = ext.lower()
    ensure_output_dir(output_dir)
    out_stem = output_stem if output_stem is not None else file_name
    output_path = os.path.join(output_dir, f"{out_stem}.{output_ext}")

    if ext == f".{output_ext}":
        # Already in desired format, just copy
        if not os.path.exists(output_path):
            Image.open(input_path).save(output_path)
        return output_path

    try:
        if ext == '.heic':
            heif_file = pillow_heif.read_heif(input_path)
            img = Image.frombytes(heif_file.mode, heif_file.size, heif_file.data, "raw")
        else:
            img = Image.open(input_path)
        
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")

        img.save(output_path)
        return output_path
    except Exception as e:
        print(f"[ERROR] Could not convert {input_path}: {e}")
        return None

def detect_plate_circles(image, config):
    """
    Returns all plate-circle candidates from HoughCircles as a list of
    (x, y, r) tuples, ordered by accumulator strength (best first).
    Returns an empty list if no circles are found.
    """
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    gray = cv2.equalizeHist(gray)
    blurred = cv2.GaussianBlur(gray, (5, 5), 2)
    edges = cv2.Canny(blurred, 50, 150)
    circles = cv2.HoughCircles(
        edges, cv2.HOUGH_GRADIENT,
        dp=config['dp'],
        minDist=config['minDist'],
        param1=config['param1'],
        param2=config['param2'],
        minRadius=config['minRadius'],
        maxRadius=config['maxRadius']
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

    Among the candidates HoughCircles returns, the one whose centre is
    closest to the image centre wins -- the user's plates sit roughly in
    the middle of the frame, and the raw accumulator order can otherwise
    prefer a spurious larger circle (e.g. a lens-vignette ring or a table
    edge) over the actual plate.

    config['radius_pad_pct'] (default 0.0) grows the final radius by the
    given fraction, useful if HoughCircles consistently latches onto the
    inner agar rim instead of the outer plate edge.
    """
    h, w = image_bgr.shape[:2]
    new_w = max(1, int(w * resize_factor))
    new_h = max(1, int(h * resize_factor))
    small = cv2.resize(image_bgr, (new_w, new_h), interpolation=cv2.INTER_AREA)

    scaled_config = config.copy()
    for key in ['minDist', 'minRadius', 'maxRadius']:
        if key in scaled_config:
            scaled_config[key] = max(1, int(scaled_config[key] * resize_factor))

    candidates = detect_plate_circles(small, scaled_config)
    if not candidates:
        return None

    cx, cy = new_w / 2.0, new_h / 2.0
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