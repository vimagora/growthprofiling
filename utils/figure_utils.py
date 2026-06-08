import os
import logging
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.backends.backend_pdf import PdfPages
from PIL import Image


def load_images(cropped_dir, rename_csv_path):
    """
    Loads cropped images indexed by (strain, substrate, timepoint).

    The rename CSV is the source of truth. If it has explicit
    'strain', 'substrate', 'day' columns, those are used directly.
    Otherwise the function falls back to splitting 'new_name' on '_';
    rows whose new_name does not split into exactly three tokens are
    skipped with a warning.

    Returns: (images dict, sorted strains, sorted substrates, sorted timepoints).
    """
    df = pd.read_csv(rename_csv_path)
    if 'new_name' not in df.columns:
        raise ValueError(f"{rename_csv_path} is missing required column 'new_name'.")

    has_explicit = {'strain', 'substrate', 'day'}.issubset(df.columns)

    images = {}
    strains, substrates, timepoints = set(), set(), set()

    for _, row in df.iterrows():
        new_name = str(row['new_name'])
        if has_explicit:
            strain = str(row['strain'])
            substrate = str(row['substrate'])
            timepoint = str(row['day'])
        else:
            tokens = new_name.split('_')
            if len(tokens) != 3:
                logging.warning(
                    f"Skipping '{new_name}': expected 3 underscore-separated tokens "
                    f"(strain_substrate_timepoint), got {len(tokens)}."
                )
                continue
            strain, substrate, timepoint = tokens

        path = os.path.join(cropped_dir, f"{new_name}.tiff")
        if not os.path.exists(path):
            continue

        images[(strain, substrate, timepoint)] = path
        strains.add(strain)
        substrates.add(substrate)
        timepoints.add(timepoint)

    return images, sorted(strains), sorted(substrates), sorted(timepoints)


def generate_figure(selected_strains, selected_substrates, selected_timepoint, images, output_pdf, axis_choice):
    """
    Generates a grid figure with strains on one axis and substrates on the other.
    """
    n_rows = len(selected_strains) if axis_choice == 'vertical' else len(selected_substrates)
    n_cols = len(selected_substrates) if axis_choice == 'vertical' else len(selected_strains)
    fig, axes = plt.subplots(nrows=n_rows, ncols=n_cols, figsize=(4*n_cols, 4*n_rows))

    if n_rows == 1 and n_cols == 1:
        axes = np.array([[axes]])
    elif n_rows == 1:
        axes = np.array([axes])
    elif n_cols == 1:
        axes = np.array([[ax] for ax in axes])

    for i, strain in enumerate(selected_strains if axis_choice == 'vertical' else selected_substrates):
        for j, substrate in enumerate(selected_substrates if axis_choice == 'vertical' else selected_strains):
            ax = axes[i, j]
            if axis_choice == 'vertical':
                key = (strain, substrate, selected_timepoint)
            else:
                key = (substrate, strain, selected_timepoint)
            img_path = images.get(key)
            if img_path and os.path.exists(img_path):
                img = Image.open(img_path)
                ax.imshow(img)
            else:
                ax.text(0.5, 0.5, 'No image', ha='center', va='center')
            ax.set_xticks([])
            ax.set_yticks([])

            if j == 0:
                ax.set_ylabel(substrate if axis_choice == 'vertical' else strain, fontsize=12)
            if i == 0:
                ax.set_title(strain if axis_choice == 'vertical' else substrate, fontsize=12)

    plt.tight_layout()
    plt.subplots_adjust(wspace=0, hspace=0)
    with PdfPages(output_pdf) as pdf:
        pdf.savefig(fig)
    plt.close(fig)
