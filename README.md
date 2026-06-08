# growthprofiling

This tool processes a batch of growth profiling images, converting them to TIFF, relabeling them, and cropping the plate for publication. It supports various image formats including `.heic`, `.jpg`, `.png`, `.tiff`, and `.jpeg`.

A `rename_matrix.csv` is **required**: each raw image must have a corresponding `old_name` → `new_name` row in the CSV. Files in the raw directory that are not listed are skipped with a warning.

---

## Features

- **Batch conversion**: Converts various image formats to `.tiff`.
- **Renaming**: Renames images using a required `rename_matrix.csv`.
- **Automated cropping**: Crops the petri dish from the image for figure preparation.
- **Multithreaded processing**: Uses all available CPU cores by default for fast batch processing. You can override the number of threads with a command-line argument.
- **Fast circle detection**: Detects plate circles on JPEGs for speed, then applies coordinates to original TIFFs.
- **Publishable figure creation**: Generate grid figures from cropped images, with customizable axis labels and layout, ready for publication.

---

## Usage

1.  **Clone the [repository](https://github.com/GonzalezVictorM/growthprofiling.git)**:

    ```bash
    git clone https://github.com/GonzalezVictorM/growthprofiling.git
    cd growthprofiling
    ```
    
2.  **(Optional/recommended) Build a conda environment**:

    ```bash
    conda create --name growthprofiling python=3.13.5
    ```

    You can activate and deactivate the environment using the following code.

    ```bash
    conda activate growthprofiling
    conda deactivate
    ```

3.  **Install dependencies**:

    ```bash
    pip install -r requirements.txt
    ```

4.  **Place your images**:

    Put your raw images inside the `local_data/raw_pictures/` directory.

5. **Provide a Rename Matrix (required)**:

    Create or edit `local_data/rename_matrix_example.csv` and save it as `local_data/rename_matrix.csv`. The file must include a column `old_name` with file names without the extension (e.g. `IMG_4469.HEIC` → `IMG_4469`) and a column `new_name` (e.g. `strainA_substrateB_ndays`). Raw images whose stem is not listed in the CSV are skipped with a warning.

6.  **Run the picture processing tool**:

    You can run the batch processor using all available CPU cores (default), or specify the number of threads:

    ```bash
    python process_pictures.py --max-workers 8
    ```
    The script will process the images and save the output in the following directories:
    
    * `local_data/converted_pictures/`: Intermediate .tiff files (saved directly under the new name from the CSV).
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

## Prerequisites

### 1. Conda installation

Install **Anaconda** from your institution's **Software Center** or by downloading the installer from the [Anaconda downloadpage](https://www.anaconda.com/download).

## Configuration

You can adjust various settings by editing `config.py`. These settings include file paths, supported formats, and circle-detection parameters. For example, you can change the input and output directories or fine-tune the circle recognition parameters.

## Directory architechture

```
project_root/  
├── process_pictures.py         # Batch processing with multithreading
├── generate_figure.py          # Interactive figure creation
├── config.py                   # Configuration settings for the tool
├── requirements.txt            # List of Python dependencies
├── utils/                      # Helper scripts
│   ├── image_utils.py          # Functions for image processing
│   └── figure_utils.py         # Functions for figure creation
├── local_data/                 # All data and output files are stored here
│   ├── rename_matrix.csv       # CSV file for renaming images (required)
│   ├── rename_matrix_example.csv # Example CSV for reference
│   ├── raw_pictures/           # Place your input images here
│   ├── converted_pictures/     # Intermediate TIFF files (saved directly under the new name)
│   └── cropped_pictures/       # Final, cropped images are saved here
```

## Contact

For questions or contributions, please open an issue or pull request on GitHub.