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
        --output figure.pdf
    ```

    The rename matrix is the source of truth: if it includes `strain`, `substrate`, and `day` columns those are used directly; otherwise the script parses these from `new_name` by splitting on `_` (which requires exactly three tokens).

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