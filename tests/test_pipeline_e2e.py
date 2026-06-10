"""
End-to-end smoke test of the full pipeline on synthetic data.

Runs raw image -> decode -> detect -> crop -> mask -> cropped TIFF and
then cropped TIFFs -> generate_figure -> PDF, all inside a temp
directory so nothing in local_data/ is touched. Catches integration
breakage that the per-component unit tests cannot.

This is a smoke test: it asserts the pipeline produces output files of
sensible size, not that the detection on real photos is correct (that
is the regression test's job).
"""
import os
import sys
import tempfile
import unittest

import numpy as np

# Force a non-interactive backend before matplotlib (or pyplot via figure_utils)
# is imported. Lets the test run on headless machines / CI.
import matplotlib
matplotlib.use('Agg')

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
sys.path.insert(0, ROOT)

import cv2  # noqa: E402
from config import CIRCLE_DETECTION_CONFIG, RESIZE_FACTOR  # noqa: E402
from utils.image_utils import (  # noqa: E402
    load_image_bgr, detect_plate_circle_downscaled, crop_plate, mask_to_circle,
)
from utils.figure_utils import load_images, generate_figure  # noqa: E402


def _make_synthetic_plate_image(path, width=4000, height=3000, plate_radius=1000):
    """White background with a black filled circle in the centre."""
    img = np.full((height, width, 3), 255, dtype=np.uint8)
    cv2.circle(img, (width // 2, height // 2), plate_radius, (50, 50, 50), -1)
    cv2.imwrite(path, img)


def _make_rename_csv(path):
    with open(path, 'w') as f:
        f.write("old_name,strain,substrate,day,new_name\n")
        f.write("IMG_001,strainA,subX,3d,strainA_subX_3d\n")
        f.write("IMG_002,strainA,subY,3d,strainA_subY_3d\n")


class EndToEndPipelineTest(unittest.TestCase):
    """Process two synthetic plates, build a 1x2 figure, assert artefacts exist."""

    def test_full_pipeline_on_synthetic_data(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            raw_dir = os.path.join(tmpdir, 'raw_pictures')
            cropped_dir = os.path.join(tmpdir, 'cropped_pictures')
            os.makedirs(raw_dir)
            os.makedirs(cropped_dir)

            csv_path = os.path.join(tmpdir, 'rename_matrix.csv')
            _make_rename_csv(csv_path)

            mapping = {
                'IMG_001': 'strainA_subX_3d',
                'IMG_002': 'strainA_subY_3d',
            }
            for old_name in mapping:
                _make_synthetic_plate_image(os.path.join(raw_dir, f"{old_name}.tiff"))

            # Pipeline stage by stage (skipping the ProcessPool orchestrator).
            for old_name, new_name in mapping.items():
                raw_path = os.path.join(raw_dir, f"{old_name}.tiff")
                cropped_path = os.path.join(cropped_dir, f"{new_name}.tiff")

                image = load_image_bgr(raw_path)
                self.assertIsNotNone(image, f"load_image_bgr failed on {raw_path}")

                circle = detect_plate_circle_downscaled(
                    image, CIRCLE_DETECTION_CONFIG, RESIZE_FACTOR
                )
                self.assertIsNotNone(circle, f"No circle detected in {raw_path}")

                cropped = crop_plate(image, circle)
                masked = mask_to_circle(cropped)
                cv2.imwrite(cropped_path, masked)
                self.assertTrue(os.path.exists(cropped_path),
                                f"Cropped output missing: {cropped_path}")
                self.assertGreater(os.path.getsize(cropped_path), 1000,
                                   f"Cropped TIFF suspiciously small: {cropped_path}")

            # Figure stage.
            images, strains, substrates, timepoints, labels = load_images(
                cropped_dir, csv_path,
            )
            self.assertEqual(strains, ['strainA'])
            self.assertEqual(substrates, ['subX', 'subY'])
            self.assertEqual(timepoints, ['3d'])
            self.assertEqual(len(images), 2)
            self.assertIn('strain', labels)

            pdf_path = os.path.join(tmpdir, 'figure.pdf')
            generate_figure(
                selected_strains=['strainA'],
                selected_substrates=['subX', 'subY'],
                selected_timepoint='3d',
                images=images,
                output_pdf=pdf_path,
                axis_choice='vertical',
                labels=labels,
            )
            self.assertTrue(os.path.exists(pdf_path),
                            f"Figure PDF missing: {pdf_path}")
            self.assertGreater(os.path.getsize(pdf_path), 1000,
                               "Figure PDF suspiciously small")


if __name__ == '__main__':
    unittest.main()
