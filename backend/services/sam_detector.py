"""SAM boundary detection service using segment-geospatial."""

import logging
import os
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image

from backend.config import settings

logger = logging.getLogger(__name__)

# Enable MPS fallback so unsupported ops (e.g. float64) run on CPU transparently.
# Must be set before any torch import.
os.environ["PYTORCH_ENABLE_MPS_FALLBACK"] = "1"


def _patch_mps_float64():
    """Patch torch.as_tensor to downcast float64 to float32 on MPS.

    SAM's automatic_mask_generator passes numpy float64 arrays to
    torch.as_tensor(arr, device='mps'), which fails because MPS
    doesn't support float64. This patch transparently casts to float32.
    """
    import torch

    if not torch.backends.mps.is_available():
        return

    _original_as_tensor = torch.as_tensor

    def _as_tensor_mps_safe(data, *, dtype=None, device=None):
        if device is not None and str(device).startswith("mps") and dtype is None:
            if hasattr(data, "dtype") and str(data.dtype) == "float64":
                if isinstance(data, np.ndarray):
                    data = data.astype(np.float32)
                elif isinstance(data, torch.Tensor):
                    data = data.float()
        return _original_as_tensor(data, dtype=dtype, device=device)

    torch.as_tensor = _as_tensor_mps_safe
    logger.info("Patched torch.as_tensor for MPS float64 safety")


# Global model instance (lazy-loaded)
_sam_model = None
_sam_predictor = None


def _get_device() -> str:
    """Determine best available device, respecting config override."""
    configured = settings.SAM_DEVICE
    if configured and configured != "auto":
        return configured

    import torch

    if torch.backends.mps.is_available():
        return "mps"
    elif torch.cuda.is_available():
        return "cuda"
    return "cpu"


def get_sam_model():
    """Get or initialize SAM model (lazy singleton)."""
    global _sam_model
    if _sam_model is not None:
        return _sam_model

    logger.info("Loading SAM2 model (this may take a moment on first run)...")

    try:
        from samgeo import SamGeo

        device = _get_device()
        if device == "mps":
            _patch_mps_float64()
        logger.info(f"Using device: {device}")

        _sam_model = SamGeo(
            model_type=settings.SAM_MODEL_TYPE,
            automatic=True,
            device=device,
            sam_kwargs={
                "points_per_side": 32,  # default density, good balance
                "pred_iou_thresh": 0.80,  # slightly lower to catch more boundaries
                "stability_score_thresh": 0.85,  # slightly lower for satellite imagery
                "min_mask_region_area": 100,  # filter tiny noise masks
            },
        )
        logger.info("SAM2 model loaded successfully")
        return _sam_model
    except Exception as e:
        logger.error(f"Failed to load SAM model: {e}")
        raise


def get_sam_predictor():
    """Get or initialize SAM predictor for prompted segmentation."""
    global _sam_predictor
    if _sam_predictor is not None:
        return _sam_predictor

    try:
        from samgeo import SamGeo

        device = _get_device()
        _sam_predictor = SamGeo(
            model_type=settings.SAM_MODEL_TYPE,
            automatic=False,
            device=device,
        )
        logger.info("SAM2 predictor loaded successfully")
        return _sam_predictor
    except Exception as e:
        logger.error(f"Failed to load SAM predictor: {e}")
        raise


async def detect_boundaries_auto(
    image: np.ndarray,
    meta: dict,
) -> list[dict]:
    """
    Run automatic boundary detection on a satellite image.

    Args:
        image: RGB numpy array of the satellite image
        meta: Metadata dict with bbox and pixel info

    Returns:
        List of detected mask dicts with geometry info
    """
    import torch

    sam = get_sam_model()

    # Save image to temp file for samgeo
    with tempfile.NamedTemporaryFile(suffix=".tif", delete=False) as tmp_in:
        tmp_input = tmp_in.name
    with tempfile.NamedTemporaryFile(suffix=".tif", delete=False) as tmp_out:
        tmp_output = tmp_out.name

    try:
        _save_georeferenced_image(image, meta, tmp_input)

        # generate() accepts source directly; set_image() is only for prompted mode
        # foreground=False + unique=True gives each detected object a unique ID
        sam.generate(
            source=tmp_input,
            output=tmp_output,
            batch=False,
            foreground=False,
            unique=True,
        )

        # Convert masks to vector polygons
        masks = _extract_masks_from_output(tmp_output, meta)

        logger.info(f"Auto-detection found {len(masks)} segments")
        return masks

    finally:
        for f in [tmp_input, tmp_output]:
            try:
                os.unlink(f)
            except OSError:
                pass


async def detect_boundaries_prompted(
    image: np.ndarray,
    meta: dict,
    point_coords: list[list[float]] | None = None,
    point_labels: list[int] | None = None,
    box_coords: list[list[float]] | None = None,
) -> list[dict]:
    """
    Run prompted boundary detection.

    Args:
        image: RGB numpy array
        meta: Metadata dict
        point_coords: List of [lon, lat] points
        point_labels: List of labels (1=foreground, 0=background)
        box_coords: List of [minLon, minLat, maxLon, maxLat] boxes
    """
    from backend.services.tile_fetcher import lonlat_to_pixel

    predictor = get_sam_predictor()

    with tempfile.NamedTemporaryFile(suffix=".tif", delete=False) as tmp_in:
        tmp_input = tmp_in.name
    with tempfile.NamedTemporaryFile(suffix=".tif", delete=False) as tmp_out:
        tmp_output = tmp_out.name

    try:
        _save_georeferenced_image(image, meta, tmp_input)
        predictor.set_image(tmp_input)

        # Convert geo coordinates to pixel coordinates
        pixel_points = None
        pixel_boxes = None

        if point_coords:
            pixel_points = []
            for lon, lat in point_coords:
                px, py = lonlat_to_pixel(lon, lat, meta)
                pixel_points.append([px, py])

        if box_coords:
            pixel_boxes = []
            for box in box_coords:
                px1, py1 = lonlat_to_pixel(box[0], box[3], meta)  # top-left
                px2, py2 = lonlat_to_pixel(box[2], box[1], meta)  # bottom-right
                pixel_boxes.append([px1, py1, px2, py2])

        predictor.predict(
            point_coords=pixel_points if pixel_points else None,
            point_labels=point_labels,
            boxes=pixel_boxes if pixel_boxes else None,
            output=tmp_output,
        )

        masks = _extract_masks_from_output(tmp_output, meta)
        logger.info(f"Prompted detection found {len(masks)} segments")
        return masks

    finally:
        for f in [tmp_input, tmp_output]:
            try:
                os.unlink(f)
            except OSError:
                pass


def _save_georeferenced_image(image: np.ndarray, meta: dict, output_path: str):
    """Save numpy image as a georeferenced GeoTIFF."""
    import rasterio
    from rasterio.transform import from_bounds

    bbox = meta["bbox"]
    height, width = image.shape[:2]

    transform = from_bounds(bbox[0], bbox[1], bbox[2], bbox[3], width, height)

    # Write as GeoTIFF with 3 bands (RGB)
    with rasterio.open(
        output_path,
        "w",
        driver="GTiff",
        height=height,
        width=width,
        count=3,
        dtype="uint8",
        crs="EPSG:4326",
        transform=transform,
    ) as dst:
        for i in range(3):
            dst.write(image[:, :, i], i + 1)


def _extract_masks_from_output(mask_path: str, meta: dict) -> list[dict]:
    """Extract individual mask polygons from the SAM output raster."""
    import rasterio
    from rasterio.features import shapes
    from shapely.geometry import mapping, shape

    masks = []

    try:
        with rasterio.open(mask_path) as src:
            mask_data = src.read(1)
            transform = src.transform

            unique_values = np.unique(mask_data)
            unique_values = unique_values[unique_values > 0]  # skip background

            for val in unique_values:
                binary_mask = (mask_data == val).astype(np.uint8)

                # Extract polygon from mask
                for geom, value in shapes(binary_mask, transform=transform):
                    if value == 1:
                        polygon = shape(geom)

                        # Filter small polygons
                        if polygon.area < 1e-8:  # very small in degrees
                            continue

                        masks.append(
                            {
                                "geometry": mapping(polygon),
                                "mask_id": int(val),
                                "area_deg": polygon.area,
                                "centroid": [polygon.centroid.x, polygon.centroid.y],
                            }
                        )

    except Exception as e:
        logger.error(f"Error extracting masks: {e}")
        # Fallback: try reading as image and extracting contours
        masks = _extract_masks_fallback(mask_path, meta)

    return masks


def _extract_masks_fallback(mask_path: str, meta: dict) -> list[dict]:
    """Fallback mask extraction using OpenCV contours."""
    import cv2
    from shapely.geometry import Polygon, mapping

    from backend.services.tile_fetcher import pixel_to_lonlat

    masks = []
    try:
        img = cv2.imread(mask_path, cv2.IMREAD_UNCHANGED)
        if img is None:
            return masks

        if len(img.shape) == 3:
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        else:
            gray = img

        unique_values = np.unique(gray)
        unique_values = unique_values[unique_values > 0]

        for val in unique_values:
            binary = (gray == val).astype(np.uint8) * 255
            contours, _ = cv2.findContours(
                binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
            )

            for contour in contours:
                if cv2.contourArea(contour) < 100:  # skip tiny contours
                    continue

                # Simplify contour
                epsilon = 0.01 * cv2.arcLength(contour, True)
                approx = cv2.approxPolyDP(contour, epsilon, True)

                if len(approx) < 3:
                    continue

                # Convert pixel coords to lon/lat
                coords = []
                for point in approx:
                    px, py = point[0]
                    lon, lat = pixel_to_lonlat(int(px), int(py), meta)
                    coords.append([lon, lat])
                coords.append(coords[0])  # close polygon

                polygon = Polygon(coords)
                if polygon.is_valid and polygon.area > 1e-10:
                    masks.append(
                        {
                            "geometry": mapping(polygon),
                            "mask_id": int(val),
                            "area_deg": polygon.area,
                            "centroid": [polygon.centroid.x, polygon.centroid.y],
                        }
                    )

    except Exception as e:
        logger.error(f"Fallback extraction failed: {e}")

    return masks
