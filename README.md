# growthprofiling

This tool processes a batch of growth profiling images, converting them to TIFF, relabeling them, and cropping the plate for publication. It supports various image formats including `.heic`, `.jpg`, `.png`, `.tiff`, and `.jpeg`.

A `rename_matrix.csv` is **required**: each raw image must have a corresponding `old_name` → `new_name` row in the CSV. Files in the raw directory that are not listed are skipped with a warning.

---

## Features

- **Batch conversion**: Converts various image formats to `.tiff`.
- **Renaming**: Renames images using a required `rename_matrix.csv`.
- **Automated cropping**: Crops the petri dish from the image for figure preparation.
- **Multiprocessed processing**: Uses all available CPU cores by default for fast batch processing. You can override the number of workers with a command-line argument.
- **Resolution-independent circle detection**: Detects the plate circle on a downscaled copy of each image. Detector bounds are expressed as a fraction of image width, so the same config works across cameras.
- **Per-run manifest**: Each batch writes a CSV with stage, status, message, and duration for every image.
- **Regression tests**: A calibration script + unit tests catch parameter drift in the circle detector.
- **Publishable figure creation**: Generate grid figures from cropped images, with customizable axis labels and layout, ready for publication.

---

## Usage

1.  **Clone the [repository](https://github.com/GonzalezVictorM/growthprofiling.git)**:

    ```bash
    git clone https://github.com/GonzalezVictorM/growthprofiling.git
    cd growthprofiling
    ```
    
2.  **Create and activate a Python virtual environment**:

    ```bash
    python -m venv .venv
    source .venv/bin/activate         # Linux / macOS / WSL
    # .venv\Scripts\activate          # Windows PowerShell / cmd
    # source .venv/Scripts/activate   # Windows Git Bash
    ```

    When you're done, deactivate it with `deactivate`.

3.  **Install dependencies**:

    ```bash
    pip install -r requirements.txt
    ```

4.  **Place your images**:

    Put your raw images inside the `local_data/raw_pictures/` directory.

5. **Provide a Rename Matrix (required)**:

    Create or edit `local_data/rename_matrix_example.csv` and save it as `local_data/rename_matrix.csv`. The file must include a column `old_name` with file names without the extension (e.g. `IMG_4469.HEIC` → `IMG_4469`) and a column `new_name` (e.g. `strainA_substrateB_ndays`). Raw images whose stem is not listed in the CSV are skipped with a warning.

6.  **Run the picture processing tool**:

    With your venv active, run the full pipeline over every image listed in `rename_matrix.csv`:

    ```bash
    python process_pictures.py
    ```

    Optional flags:

    * `--max-workers N` — number of parallel worker processes (default: all CPU cores).
    * `--rename-csv FILE` — name of the rename CSV inside `local_data/` (default: `rename_matrix.csv`).
    * `--debug` — also write 800 px thumbnails to `local_data/debug/` with the detected plate circle drawn on top. Useful for verifying detection after tuning `CIRCLE_DETECTION_CONFIG`.

    The script will process the images and save the output in the following directories:
    
    * `local_data/cropped_pictures/`: The final, cropped images ready for publication.
    * `local_data/manifests/`: One CSV per run (`run_YYYYMMDD_HHMMSS.csv`) recording each file's stage, status, message, and duration in ms.

    The script will skip parts of the process for which the output is ready, making it possible to run the command without re-doing all the work. The end-of-run log line summarises counts as `ok`/`skipped`/`failed`.

7.  **Run the figure making tool**:

    Fully interactive (you'll be prompted for axis, strains, substrates, and timepoint):

    ```bash
    python generate_figure.py
    ```

    Or fully scriptable (any combination of CLI args; missing ones fall back to prompts):

    ```bash
    python generate_figure.py \
        --axis vertical \
        --strains CBS464,CBS487 \
        --substrates cellulose,starch \
        --timepoint 3d \
        --output figure.pdf \
        --cell-size 4 \
        --label-fontsize 12 \
        --dpi 300 \
        --force
    ```

    | Flag | Default | Purpose |
    |---|---|---|
    | `--axis` | (prompt) | `vertical` puts strains on rows; `horizontal` flips. |
    | `--strains` / `--substrates` | (prompt) | Comma-separated subsets to include. Validated against the CSV. |
    | `--timepoint` | (prompt) | Single timepoint to plot. |
    | `--output` | `growth_profile_figure.pdf` | Output PDF path. |
    | `--cell-size` | `4.0` | Side length (inches) of each grid cell. |
    | `--label-fontsize` | `12` | Font size for row labels and column titles. |
    | `--dpi` | `300` | Resolution of the rendered PDF. |
    | `--force` | off | Overwrite the output PDF if it already exists. |

    The rename matrix is the source of truth: if it includes `strain`, `substrate`, and `day` columns those are used directly; otherwise the script parses these from `new_name` by splitting on `_` (which requires exactly three tokens).

    **Optional display labels.** Add `display_strain`, `display_substrate`, and/or `display_day` columns to `rename_matrix.csv` to override how each value is rendered in the figure. Useful for publication-quality formatting (e.g. `CBS464` → `B. acidogenes`) without renaming the underlying data. Empty cells in those columns fall back to the raw key.

***

## Configuration

You can adjust various settings by editing `config.py`. These settings include file paths, supported formats, and circle-detection parameters. For example, you can change the input and output directories or fine-tune the circle recognition parameters.

## Tests

The repo ships with regression tests for circle detection.

1.  **Seed the expected values.** With your raw images in `local_data/raw_pictures/`, run the calibration script once:

    ```bash
    python tools/calibrate.py
    ```

    This writes `tests/fixtures/expected_circles.csv` from whatever `CIRCLE_DETECTION_CONFIG` currently produces on your images, and saves a thumbnail with the detected circle drawn on top to `tests/fixtures/overlays/` for each image. **Open the overlays before trusting the baseline** — if a detection looks wrong, retune `CIRCLE_DETECTION_CONFIG` and re-run the calibration.

2.  **Run the tests:**

    ```bash
    python -m unittest discover tests
    ```

    A synthetic-image smoke test always runs. The per-fixture regression test runs once `expected_circles.csv` exists and skips cleanly otherwise. Tolerance is ±25 px on each of `x`, `y`, and `r`.

3.  **After intentional retuning:** re-run `python tools/calibrate.py` to refresh the expected values.

Fixture images, the expected CSV, and the overlays are all gitignored (they are tied to one user's photos and should stay local).

## Troubleshooting

### "No circular plate detected" on some images
The detector's radius bounds or the Hough strictness don't match your images. Run `python tools/calibrate.py` and look at the overlays in `tests/fixtures/overlays/`:

- **Green circle = picked**. **Red circles = other candidates Hough found**. **Magenta = `center_tolerance_frac` filter**. **Yellow cross = image centre**.
- If you see **no red circles at all**, Hough isn't finding the plate. Lower `param2` (try 25 or 20) in `config.py` to be more permissive, or check that `minRadius_frac`/`maxRadius_frac` actually bracket your plate radii (the calibrate script prints the resolved pixel bounds per image).
- If you see **red circles in the wrong places**, the detector is finding the plate but the selector picks something else. Adjust `center_tolerance_frac` so the magenta disc contains the real plate.

### Detection finds a circle smaller than the plate (clips the rim)
Classic with ring-light setups: a thin bright halo at the agar meniscus competes with the outer plastic rim. Increase `blur_ksize` (e.g. from 15 to 21) and `blur_sigma` (e.g. from 5 to 7) in `config.py` to smear the halo. If that's not enough, a small `radius_pad_pct` (0.02–0.03) gives every detection a small outward bias.

### Detection finds a circle much larger than the plate
A spurious circle (lens vignette, table edge, light cone on the bench) is winning. Two knobs:

- **Tighten `maxRadius_frac`** if the spurious is too big to be a plate.
- **Tighten `center_tolerance_frac`** if the spurious is off to one side. Lower values like 0.10 require the plate to sit nearly in the centre of the frame.

### Tests skip the regression test
That's expected if `tests/fixtures/expected_circles.csv` doesn't exist yet. Run `python tools/calibrate.py` first to populate it, then re-run the tests. The synthetic smoke test always runs regardless.

### `pillow_heif` install fails on Windows
HEIC decoding requires native libraries. On Windows the easiest path is:

```bash
pip install pillow_heif --only-binary=:all:
```

so pip downloads a prebuilt wheel rather than trying to compile. If that fails, install Anaconda's `libheif` first (`conda install -c conda-forge libheif`) and then re-install `pillow_heif` from pip.

### Figure has no images and shows "No image" placeholders everywhere
`generate_figure.py` looks up cropped TIFFs by `new_name` in the rename matrix. Three likely causes:

- You haven't run `process_pictures.py` yet — no cropped TIFFs exist.
- The strain/substrate/timepoint values you passed on the command line don't match what's in `rename_matrix.csv` exactly (case-sensitive). Run `python generate_figure.py` without flags to see the available values listed.
- The matching cropped TIFFs were filtered out by your `--strains`/`--substrates`/`--timepoint` selection. Try a wider selection.

### `Output ... already exists. Use --force to overwrite.`
The figure generator now refuses to silently clobber a PDF. Either pass `--force` or change `--output` to a different filename.

## Directory architechture

```
project_root/
├── process_pictures.py           # Batch processing pipeline
├── generate_figure.py            # Grid-figure creation (CLI or interactive)
├── config.py                     # Configuration (paths, detector knobs, manifest helpers)
├── requirements.txt              # Python dependencies
├── utils/
│   ├── image_utils.py            # Image decoding, circle detection, cropping
│   └── figure_utils.py           # Figure-grid layout and image lookup
├── tools/
│   └── calibrate.py              # Seeds tests/fixtures/expected_circles.csv and writes overlays
├── tests/
│   ├── test_circle_detection.py  # Synthetic smoke test + per-fixture regression test
│   └── fixtures/                 # (gitignored) expected_circles.csv and overlay thumbnails
├── local_data/                   # All data and output files (gitignored)
│   ├── rename_matrix.csv         # CSV for renaming images (required)
│   ├── rename_matrix_example.csv # Example CSV for reference
│   ├── raw_pictures/             # Place your input images here
│   ├── cropped_pictures/         # Final, cropped images
│   ├── manifests/                # Per-run CSV manifests
│   └── debug/                    # (only when --debug) circle-overlay thumbnails
```

## Contact

For questions or contributions, please open an issue or pull request on GitHub.