# Changelog

All notable changes to this project are documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added
- **Per-run CSV manifest** under `local_data/manifests/run_<timestamp>.csv` recording filename, stage, status, message, and duration in ms for every image processed.
- **Circle-detection regression tests** plus a calibration script (`tools/calibrate.py`) that seeds `tests/fixtures/expected_circles.csv` and writes per-image overlay thumbnails (green = picked, red = other Hough candidates, magenta = centre-tolerance disc, yellow = image centre) for visual verification.
- **End-to-end pipeline smoke test** (`tests/test_pipeline_e2e.py`) that runs synthetic images through the full pipeline (raw → cropped → figure PDF) inside a temp directory.
- **`--debug` flag on `process_pictures.py`** writes thumbnails with the detected plate circle drawn on top to `local_data/debug/`. Useful for spotting bad detections during a real run.
- **CLI arguments for `generate_figure.py`** (`--strains`, `--substrates`, `--timepoint`, `--axis`, `--output`, `--cell-size`, `--label-fontsize`, `--dpi`, `--force`, `--rename-csv`). Any omitted flag falls back to an interactive prompt for that one value.
- **Optional display label columns** (`display_strain`, `display_substrate`, `display_day`) in `rename_matrix.csv` override how each value is rendered in the figure without renaming the underlying data.
- **Resolution-independent circle detection**: `minDist_frac`, `minRadius_frac`, `maxRadius_frac`, `center_tolerance_frac` are now expressed as fractions of image width.
- **Configurable Hough preprocessing**: `blur_ksize` and `blur_sigma` config knobs let you widen the pre-Hough Gaussian blur to suppress ring-light halos at the agar meniscus.
- **`RESIZE_FACTOR`** for the detection-time downscale, configurable in `config.py`.
- **Troubleshooting section** in the README covering "no circle detected", wrong-circle picks, HEIC install issues on Windows, and figure-generation pitfalls.

### Changed
- **Pipeline is now fully in-memory**: raw → cropped, with no intermediate `converted_pictures/` stage. Each image is decoded once into a numpy array; detection, cropping, and masking all run on the in-memory array; only the final cropped TIFF is written to disk. Eliminates ~70 MB of I/O per image.
- **`ProcessPoolExecutor`** replaces `ThreadPoolExecutor`. The dominant cost (HEIC decode, TIFF save) is GIL-bound, so threads couldn't truly parallelise; processes can.
- **Hough preprocessing** no longer pre-computes Canny edges or runs `equalizeHist`. HoughCircles computes its own gradient internally; the function now passes it the blurred grayscale directly. Faster and tends to produce cleaner detections.
- **Circle selection** is now a two-stage process: candidates outside `center_tolerance_frac × image_width` of the image centre are dropped first, then the highest-accumulator survivor wins. Falls back to closest-to-centre if no candidate survives the filter.
- **Figure layout**: `tight_layout()` is gone (it was fighting `subplots_adjust(wspace=0, hspace=0)`). Outer margins are now handled by `bbox_inches='tight'` on save.
- **Figure cells** have `aspect='equal'` set unconditionally, so empty "No image" placeholders no longer stretch differently from cells with images.
- **`Image.open` in figure code** is now wrapped in a `with` block to release file handles eagerly.
- **README** rewritten: venv instead of conda, updated feature list, accurate directory tree, troubleshooting section.

### Fixed
- **Figure axis labels were inverted**. In vertical mode, every top-row title was set to the first strain and every left-column ylabel to the first substrate, regardless of position. Now the title correctly shows the column's identity and the ylabel correctly shows the row's identity.
- **`generate_figure.py` overwrites silently**: now errors out if `--output` already exists; pass `--force` to overwrite.
- **Ring-light halo misdetection**: the original blur kernel `(5, 5)` / sigma=2 was too tight to suppress thin bright reflections at the agar meniscus, causing detection to lock onto the halo instead of the outer plastic rim. Default widened to `(15, 15)` / sigma=5; both are now config knobs.
- **`os.rename` cross-filesystem failure** (legacy): the rename stage moved files across `local_data/` subdirectories with `os.rename`, which fails when those subdirs are on different mounts. The stage is now gone entirely.

### Removed
- **OCR-based renaming** (Tesseract / `pytesseract`). `rename_matrix.csv` is now required; raw images without a matching `old_name` row are skipped with a warning.
- **Windows-specific Tesseract path** in `config.py`.
- **`renamed_pictures/` directory** and the cross-directory `os.rename` it required. Converted TIFFs are now written under the `new_name` from the CSV directly.
- **`converted_pictures/` directory**. The pipeline no longer writes an intermediate TIFF; the in-memory numpy array goes straight from decode to crop.
- **`convert_to_tiff` helper**: unused after the in-memory refactor.

## [Pre-rewrite baseline]

The project shipped as a Tesseract-OCR-backed batch converter with threading-based parallelism, fixed-pixel circle detection bounds, a three-stage on-disk pipeline (raw → converted → renamed → cropped), and a fully-interactive figure generator with no CLI surface. See git history before commit `ef126cb` for the original codebase.
