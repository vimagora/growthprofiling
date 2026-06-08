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

    The CSV may also include optional 'display_strain', 'display_substrate',
    and 'display_day' columns: when present and non-empty, those values are
    used as the figure labels instead of the raw keys. This lets you keep
    machine-friendly identifiers in the data while showing publication-
    quality labels in the output.

    Returns:
        (images, strains, substrates, timepoints, labels)

    where labels is a dict::

        {
            'strain':    {raw_key: display_label, ...},
            'substrate': {raw_key: display_label, ...},
            'day':       {raw_key: display_label, ...},
        }

    Keys with no display override are absent from the inner dicts; the
    caller should fall back to the raw key in that case.
    """
    df = pd.read_csv(rename_csv_path)
    if 'new_name' not in df.columns:
        raise ValueError(f"{rename_csv_path} is missing required column 'new_name'.")

    has_explicit = {'strain', 'substrate', 'day'}.issubset(df.columns)

    images = {}
    strains, substrates, timepoints = set(), set(), set()
    labels = {'strain': {}, 'substrate': {}, 'day': {}}
    display_cols = {
        'strain': 'display_strain',
        'substrate': 'display_substrate',
        'day': 'display_day',
    }

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

        # Collect display labels if the optional columns are present.
        key_for_cat = {'strain': strain, 'substrate': substrate, 'day': timepoint}
        for cat, col in display_cols.items():
            if col in df.columns:
                val = row[col]
                if not pd.isna(val) and str(val).strip():
                    labels[cat][key_for_cat[cat]] = str(val).strip()

    return images, sorted(strains), sorted(substrates), sorted(timepoints), labels


def generate_figure(
    selected_strains,
    selected_substrates,
    selected_timepoint,
    images,
    output_pdf,
    axis_choice,
    cell_size=4.0,
    label_fontsize=12,
    dpi=300,
    labels=None,
):
    """
    Generates a grid figure with strains on one axis and substrates on the other.

    Parameters
    ----------
    cell_size : float
        Side length, in inches, of each cell in the grid.
    label_fontsize : int
        Font size for row labels and column titles.
    dpi : int
        Resolution of the rendered PDF.
    labels : dict | None
        Optional display-label overrides as produced by load_images().
    """
    labels = labels or {'strain': {}, 'substrate': {}, 'day': {}}

    def label_for(cat, key):
        return labels.get(cat, {}).get(key, key)

    n_rows = len(selected_strains) if axis_choice == 'vertical' else len(selected_substrates)
    n_cols = len(selected_substrates) if axis_choice == 'vertical' else len(selected_strains)
    fig, axes = plt.subplots(nrows=n_rows, ncols=n_cols,
                             figsize=(cell_size * n_cols, cell_size * n_rows))

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
                with Image.open(img_path) as img:
                    ax.imshow(img)
            else:
                ax.text(0.5, 0.5, 'No image', ha='center', va='center')
            ax.set_xticks([])
            ax.set_yticks([])
            ax.set_aspect('equal')

            # ylabel = identity of the row (varies down the column).
            # title  = identity of the column (varies across the row).
            if j == 0:
                row_cat = 'strain' if axis_choice == 'vertical' else 'substrate'
                row_key = strain if axis_choice == 'vertical' else substrate
                ax.set_ylabel(label_for(row_cat, row_key), fontsize=label_fontsize)
            if i == 0:
                col_cat = 'substrate' if axis_choice == 'vertical' else 'strain'
                col_key = substrate if axis_choice == 'vertical' else strain
                ax.set_title(label_for(col_cat, col_key), fontsize=label_fontsize)

    plt.subplots_adjust(wspace=0, hspace=0)
    with PdfPages(output_pdf) as pdf:
        pdf.savefig(fig, bbox_inches='tight', pad_inches=0.1, dpi=dpi)
    plt.close(fig)
