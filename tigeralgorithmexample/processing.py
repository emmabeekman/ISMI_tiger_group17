from pathlib import Path
from typing import List

import numpy as np
from tqdm import tqdm

from .gcio import (
    TMP_DETECTION_OUTPUT_PATH,
    TMP_SEGMENTATION_OUTPUT_PATH,
    TMP_TILS_SCORE_PATH,
    copy_data_to_output_folders,
    get_image_path_from_input_folder,
    get_tissue_mask_path_from_input_folder,
    initialize_output_folders,
)
from .rw import (
    READING_LEVEL,
    WRITING_TILE_SIZE,
    DetectionWriter,
    SegmentationWriter,
    TilsScoreWriter,
    open_multiresolutionimage_image,
)


def process_image_tile_to_segmentation(
    image_tile: np.ndarray, tissue_mask_tile: np.ndarray
) -> np.ndarray:
    """Example function that shows processing a tile from a multiresolution image for segmentation purposes.
    
    NOTE 
        This code is only made for illustration and is not meant to be taken as valid processing step.

    Args:
        image_tile (np.ndarray): [description]
        tissue_mask_tile (np.ndarray): [description]

    Returns:
        np.ndarray: [description]
    """

    prediction = np.copy(image_tile[:, :, 0])
    prediction[image_tile[:, :, 0] > 90] = 0
    prediction[image_tile[:, :, 0] <= 90] = 2
    return prediction * tissue_mask_tile


def process_image_tile_to_detections(
    image_tile: np.ndarray,
    segmentation_mask: np.ndarray,
) -> List[tuple]:
    """Example function that shows processing a tile from a multiresolution image for detection purposes.
    
    NOTE 
        This code is only made for illustration and is not meant to be taken as valid processing step.

    Args:
        image_tile (np.ndarray): [description]
        tissue_mask_tile (np.ndarray): [description]

    Returns:
        List[tuple]: list of tuples (x,y) coordinates of detections
    """
    if not np.any(segmentation_mask == 2):
        return []

    prediction = np.copy(image_tile[:, :, 2])
    prediction[(image_tile[:, :, 2] <= 40) & (segmentation_mask == 2)] = 1
    xs, ys = np.where(prediction.transpose() == 1)
    return list(zip(xs, ys, [1] * len(xs)))


def process_segmentation_detection_to_tils_score(
    segmentation_path: Path, detections: List[tuple]
) -> int:
    """Example function that shows processing a segmentation mask and corresponding detection for the computation of a tls score.
    
    NOTE 
        This code is only made for illustration and is not meant to be taken as valid processing step.

    Args:
        segmentation_mask (np.ndarray): [description]
        detections (List[tuple]): [description]

    Returns:
        int: til score (between 0, 100)
    """
    image = open_multiresolutionimage_image(path=segmentation_path)
    width, height = image.getDimensions()
    slide_at_level_4 = image.getUCharPatch(0, 0, int(width / 16), int(height / 16), 4)
    area = len(np.where(slide_at_level_4 == 2)[0])
    value = int(min(100, area / (len(detections) / (8 * 8 * 8))))
    return value


def process():
    """Proceses a test slide"""

    level = READING_LEVEL
    tile_size = WRITING_TILE_SIZE

    initialize_output_folders()

    # get input paths
    image_path = get_image_path_from_input_folder()
    tissue_mask_path = get_tissue_mask_path_from_input_folder()

    print(image_path)
    print(image_path.exists())
    # open images
    image = open_multiresolutionimage_image(path=image_path)
    tissue_mask = open_multiresolutionimage_image(path=tissue_mask_path)

    # get image info
    dimensions = image.getDimensions()
    spacing = image.getSpacing()

    # create writers
    segmentation_writer = SegmentationWriter(
        TMP_SEGMENTATION_OUTPUT_PATH,
        tile_size=tile_size,
        dimensions=dimensions,
        spacing=spacing,
    )
    detection_writer = DetectionWriter(TMP_DETECTION_OUTPUT_PATH)
    tils_score_writer = TilsScoreWriter(TMP_TILS_SCORE_PATH)

    print("Processing image...")
    # loop over image
    for y in tqdm(range(0, dimensions[1], tile_size)):
        for x in range(0, dimensions[0], tile_size):
            tissue_mask_tile = tissue_mask.getUCharPatch(
                startX=x, startY=y, width=tile_size, height=tile_size, level=level
            ).squeeze()
            if np.any(tissue_mask_tile):
                image_tile = image.getUCharPatch(
                    startX=x, startY=y, width=tile_size, height=tile_size, level=level
                )

                # segmentation
                segmentation_mask = process_image_tile_to_segmentation(
                    image_tile=image_tile, tissue_mask_tile=tissue_mask_tile
                )
                segmentation_writer.write_segmentation(tile=segmentation_mask, x=x, y=y)

                # detection
                detections = process_image_tile_to_detections(
                    image_tile=image_tile, segmentation_mask=segmentation_mask
                )
                detection_writer.write_detections(
                    detections=detections, x_offset=x, y_offset=y
                )

    print("Saving...")
    # save segmentation and detection
    segmentation_writer.save()
    detection_writer.save()

    print("Compute tils score...")
    # compute tils score
    tils_score = process_segmentation_detection_to_tils_score(
        TMP_SEGMENTATION_OUTPUT_PATH, detection_writer.detections
    )
    tils_score_writer.set_tils_score(tils_score=tils_score)

    print("Saving...")
    # save tils score
    tils_score_writer.save()

    print("Copy data...")
    # save data to output folder
    copy_data_to_output_folders()

    print("Done!")