import os
import sys
import argparse
import logging
from config import BASE_DIR, DATA_DIR, CROPPED_DIR
from utils.figure_utils import load_images, generate_figure

logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')


def _parse_csv_list(s):
    if s is None:
        return None
    return [tok.strip() for tok in s.split(',') if tok.strip()]


def _prompt_choice(label, options):
    print(f"\nAvailable {label}:")
    for i, opt in enumerate(options):
        print(f"{i + 1}: {opt}")
    raw = input(f"Select {label} by number (space separated): ").strip().split()
    return [options[int(idx) - 1] for idx in raw
            if idx.isdigit() and 1 <= int(idx) <= len(options)]


def _validate_subset(requested, allowed, label):
    bad = [x for x in requested if x not in allowed]
    if bad:
        logging.error(f"Unknown {label}: {', '.join(bad)}. Available: {', '.join(allowed)}")
        sys.exit(1)
    return requested


def main():
    parser = argparse.ArgumentParser(description="Generate a publication-ready growth-profile grid figure.")
    parser.add_argument('--rename-csv', default='rename_matrix.csv',
                        help='CSV file (in local_data/) used as source of truth for metadata.')
    parser.add_argument('--strains', help='Comma-separated strains to include (default: interactive prompt).')
    parser.add_argument('--substrates', help='Comma-separated substrates to include (default: interactive prompt).')
    parser.add_argument('--timepoint', help='Single timepoint to plot (default: interactive prompt).')
    parser.add_argument('--axis', choices=['vertical', 'horizontal'],
                        help='Whether strains are on the vertical or horizontal axis (default: interactive prompt).')
    parser.add_argument('--output', default=os.path.join(BASE_DIR, 'growth_profile_figure.pdf'),
                        help='Output PDF path.')
    args = parser.parse_args()

    rename_csv_path = os.path.join(DATA_DIR, args.rename_csv)
    if not os.path.isfile(rename_csv_path):
        logging.error(f"Rename CSV not found: {rename_csv_path}")
        sys.exit(1)

    images, strains, substrates, timepoints = load_images(CROPPED_DIR, rename_csv_path)
    if not images:
        logging.error("No cropped images found that match the rename matrix.")
        sys.exit(1)

    axis_choice = args.axis
    if axis_choice is None:
        print("Axis orientation (strains on vertical or horizontal)?")
        axis_choice = input("Type 'vertical' or 'horizontal': ").strip().lower()
        if axis_choice not in ('vertical', 'horizontal'):
            logging.error("Invalid axis choice.")
            sys.exit(1)

    selected_strains = _parse_csv_list(args.strains)
    if selected_strains is None:
        selected_strains = _prompt_choice('strains', strains)
    else:
        selected_strains = _validate_subset(selected_strains, strains, 'strains')

    selected_substrates = _parse_csv_list(args.substrates)
    if selected_substrates is None:
        selected_substrates = _prompt_choice('substrates', substrates)
    else:
        selected_substrates = _validate_subset(selected_substrates, substrates, 'substrates')

    selected_timepoint = args.timepoint
    if selected_timepoint is None:
        picks = _prompt_choice('timepoints (pick one)', timepoints)
        if not picks:
            logging.error("No timepoint selected.")
            sys.exit(1)
        selected_timepoint = picks[0]
    else:
        _validate_subset([selected_timepoint], timepoints, 'timepoints')

    if not (selected_strains and selected_substrates and selected_timepoint):
        logging.error("Strains, substrates, and a timepoint are all required.")
        sys.exit(1)

    generate_figure(selected_strains, selected_substrates, selected_timepoint,
                    images, args.output, axis_choice)
    logging.info(f"Figure saved as {args.output}")


if __name__ == "__main__":
    main()
