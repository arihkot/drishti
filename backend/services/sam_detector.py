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

    logger.info("Loading SAM model (this may take a moment on first run)...")

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
                "points_per_side": 48,  # 2304 sample points — good balance of speed and coverage
                "pred_iou_thresh": 0.82,  # lowered from 0.88 — accept more masks to avoid missing plots
                "stability_score_thresh": 0.90,  # lowered from 0.94 — keep more borderline masks
                "min_mask_region_area": 200,  # minimum mask region in pixels
                "crop_n_layers": 0,  # disabled — saves ~2x compute
            },
        )
        logger.info("SAM model loaded successfully")
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
        logger.info("SAM predictor loaded successfully")
        return _sam_predictor
    except Exception as e:
        logger.error(f"Failed to load SAM predictor: {e}")
        raise


def reload_models():
    """Force reload of both SAM model and predictor.

    Call this when SAM parameters change to ensure the new
    parameters take effect without restarting the server.
    """
    global _sam_model, _sam_predictor
    _sam_model = None
    _sam_predictor = None
    logger.info("SAM model cache cleared — models will reload on next use")


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


async def detect_boundaries_csidc_guided(
    image: np.ndarray,
    meta: dict,
    auto_masks: list[dict],
    csidc_plots: list[dict],
    coverage_threshold: float = 0.3,
) -> list[dict]:
    """Run targeted SAM prompts for CSIDC plots missed by auto-detection.

    For each CSIDC reference plot, checks how much of it is covered by
    existing auto-detected masks. If coverage is below the threshold,
    uses the CSIDC plot's centroid + edge points + bbox as SAM prompts
    to detect it.

    Uses multiple point prompts per plot (centroid + edge midpoints) for
    better detection of plots that SAM's auto mode missed.

    After prompting, filters out any resulting masks that are mostly
    contained within existing auto-detected polygons (avoids creating
    duplicate smaller plots inside already-detected larger ones).

    Args:
        image: RGB numpy array of the satellite image.
        meta: Tile metadata with bbox and pixel_size fields.
        auto_masks: Masks already found by auto-detection (raw mask dicts).
        csidc_plots: CSIDC reference plot dicts with 'geometry' keys.
        coverage_threshold: Min coverage ratio to consider a plot "found".

    Returns:
        Additional mask dicts for missed plots (to be merged with auto_masks).
    """
    from shapely.geometry import shape, mapping
    from shapely.validation import make_valid
    from backend.services.tile_fetcher import lonlat_to_pixel

    if not csidc_plots:
        return []

    # Build union of all auto-detected geometries for fast coverage check
    auto_geoms = []
    for m in auto_masks:
        try:
            g = shape(m["geometry"])
            if not g.is_valid:
                g = make_valid(g)
            auto_geoms.append(g)
        except Exception:
            continue

    if auto_geoms:
        from shapely.ops import unary_union

        auto_union = unary_union(auto_geoms)
    else:
        from shapely.geometry import Polygon as ShapelyPolygon

        auto_union = ShapelyPolygon()  # empty

    # Identify missed CSIDC plots
    missed_centroids = []
    missed_boxes = []
    missed_edge_points: list[list[list[float]]] = []  # per-plot list of edge points
    missed_count = 0
    skipped_count = 0

    img_bbox = meta["bbox"]  # [minLon, minLat, maxLon, maxLat]

    for csidc_plot in csidc_plots:
        try:
            geom = csidc_plot.get("geometry")
            if not geom or not geom.get("coordinates"):
                continue

            ref_poly = shape(geom)
            if not ref_poly.is_valid:
                ref_poly = make_valid(ref_poly)

            if ref_poly.is_empty or ref_poly.area < 1e-10:
                continue

            # Skip CSIDC plots outside the satellite image extent
            bounds = ref_poly.bounds  # (minx, miny, maxx, maxy)
            if (
                bounds[2] < img_bbox[0]
                or bounds[0] > img_bbox[2]
                or bounds[3] < img_bbox[1]
                or bounds[1] > img_bbox[3]
            ):
                continue

            # Compute coverage: how much of this CSIDC plot is already detected?
            try:
                intersection = ref_poly.intersection(auto_union)
                coverage = intersection.area / ref_poly.area if ref_poly.area > 0 else 0
            except Exception:
                coverage = 0.0

            if coverage >= coverage_threshold:
                skipped_count += 1
                continue

            # This plot was missed — extract centroid and bbox as prompts
            centroid = ref_poly.centroid
            cx, cy = centroid.x, centroid.y

            # Ensure centroid is within image bounds
            if img_bbox[0] <= cx <= img_bbox[2] and img_bbox[1] <= cy <= img_bbox[3]:
                missed_centroids.append([cx, cy])

            # Generate edge midpoints along the CSIDC boundary for additional prompts
            # This helps SAM detect plots whose centroid may be ambiguous
            edge_pts = []
            try:
                exterior_coords = list(ref_poly.exterior.coords)
                n_edges = len(exterior_coords) - 1  # last coord = first
                for i in range(min(n_edges, 4)):  # up to 4 edge midpoints
                    idx = i * n_edges // min(n_edges, 4)
                    p0 = exterior_coords[idx]
                    p1 = exterior_coords[(idx + 1) % n_edges]
                    mid_x = (p0[0] + p1[0]) / 2
                    mid_y = (p0[1] + p1[1]) / 2
                    if (
                        img_bbox[0] <= mid_x <= img_bbox[2]
                        and img_bbox[1] <= mid_y <= img_bbox[3]
                    ):
                        edge_pts.append([mid_x, mid_y])
            except Exception:
                pass
            missed_edge_points.append(edge_pts)

            # Clip the CSIDC bbox to image extent for box prompt
            box_minlon = max(bounds[0], img_bbox[0])
            box_minlat = max(bounds[1], img_bbox[1])
            box_maxlon = min(bounds[2], img_bbox[2])
            box_maxlat = min(bounds[3], img_bbox[3])

            if box_maxlon > box_minlon and box_maxlat > box_minlat:
                missed_boxes.append([box_minlon, box_minlat, box_maxlon, box_maxlat])

            missed_count += 1
        except Exception as e:
            logger.warning(f"Error processing CSIDC plot for prompts: {e}")
            continue

    logger.info(
        f"CSIDC-guided: {len(csidc_plots)} ref plots, "
        f"{skipped_count} already covered, {missed_count} missed → "
        f"{len(missed_centroids)} point prompts + {len(missed_boxes)} box prompts"
    )

    if not missed_centroids and not missed_boxes:
        return []

    # Run SAM prompted detection for missed plots
    all_extra_masks: list[dict] = []

    predictor = get_sam_predictor()

    with tempfile.NamedTemporaryFile(suffix=".tif", delete=False) as tmp_in:
        tmp_input = tmp_in.name

    try:
        _save_georeferenced_image(image, meta, tmp_input)
        predictor.set_image(tmp_input)

        # Strategy: use box prompts with centroid + edge points as foreground hints
        # Process each missed plot individually for best results
        for i in range(len(missed_boxes)):
            with tempfile.NamedTemporaryFile(suffix=".tif", delete=False) as tmp_out:
                tmp_output = tmp_out.name

            try:
                box = missed_boxes[i]
                # Convert box to pixel coords
                px1, py1 = lonlat_to_pixel(box[0], box[3], meta)  # top-left
                px2, py2 = lonlat_to_pixel(box[2], box[1], meta)  # bottom-right
                pixel_box = [[px1, py1, px2, py2]]

                # Collect all point prompts for this plot: centroid + edge midpoints
                pixel_points = []
                point_labels = []

                # Add centroid if available
                if i < len(missed_centroids):
                    cx, cy = missed_centroids[i]
                    ppx, ppy = lonlat_to_pixel(cx, cy, meta)
                    pixel_points.append([ppx, ppy])
                    point_labels.append(1)

                # Add edge midpoints as additional foreground prompts
                if i < len(missed_edge_points):
                    for edge_pt in missed_edge_points[i]:
                        epx, epy = lonlat_to_pixel(edge_pt[0], edge_pt[1], meta)
                        pixel_points.append([epx, epy])
                        point_labels.append(1)

                predictor.predict(
                    point_coords=pixel_points if pixel_points else None,
                    point_labels=point_labels if point_labels else None,
                    boxes=pixel_box,
                    output=tmp_output,
                )

                masks = _extract_masks_from_output(tmp_output, meta)
                all_extra_masks.extend(masks)
            finally:
                try:
                    os.unlink(tmp_output)
                except OSError:
                    pass

        # Handle centroids without matching boxes (if more centroids than boxes)
        for k in range(len(missed_boxes), len(missed_centroids)):
            with tempfile.NamedTemporaryFile(suffix=".tif", delete=False) as tmp_out:
                tmp_output = tmp_out.name

            try:
                cx, cy = missed_centroids[k]
                ppx, ppy = lonlat_to_pixel(cx, cy, meta)

                # Collect edge points too
                pixel_points = [[ppx, ppy]]
                point_labels = [1]

                if k < len(missed_edge_points):
                    for edge_pt in missed_edge_points[k]:
                        epx, epy = lonlat_to_pixel(edge_pt[0], edge_pt[1], meta)
                        pixel_points.append([epx, epy])
                        point_labels.append(1)

                predictor.predict(
                    point_coords=pixel_points,
                    point_labels=point_labels,
                    boxes=None,
                    output=tmp_output,
                )

                masks = _extract_masks_from_output(tmp_output, meta)
                all_extra_masks.extend(masks)
            finally:
                try:
                    os.unlink(tmp_output)
                except OSError:
                    pass

    finally:
        try:
            os.unlink(tmp_input)
        except OSError:
            pass

    # --- Post-filter: reject masks that are mostly inside auto-detected areas ---
    # This prevents the guided pass from creating smaller duplicate plots
    # inside already-detected larger polygons (e.g. SAM detecting a building
    # slab inside a plot that was already captured as one large polygon).
    CONTAINMENT_THRESHOLD = 0.6  # if >=60% of guided mask is inside auto union, drop it

    filtered_masks = []
    dropped = 0
    for mask in all_extra_masks:
        try:
            g = shape(mask["geometry"])
            if not g.is_valid:
                g = make_valid(g)
            if g.is_empty or g.area < 1e-10:
                dropped += 1
                continue

            overlap = g.intersection(auto_union)
            overlap_ratio = overlap.area / g.area if g.area > 0 else 0

            if overlap_ratio >= CONTAINMENT_THRESHOLD:
                dropped += 1
                continue

            filtered_masks.append(mask)
        except Exception:
            # Keep mask if geometry check fails
            filtered_masks.append(mask)

    logger.info(
        f"CSIDC-guided pass: {len(all_extra_masks)} raw → "
        f"{len(filtered_masks)} kept, {dropped} dropped (inside existing)"
    )
    return filtered_masks


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

            # Batch morphological smoothing: process the full labeled mask once
            # instead of running binary_closing/opening per unique value.
            from scipy.ndimage import binary_closing, binary_opening

            # Create a single binary foreground mask and smooth it once
            # Reduced iterations to avoid erasing real plot boundaries:
            # closing iter=2 fills small gaps, opening iter=1 removes tiny protrusions
            fg_mask = (mask_data > 0).astype(np.uint8)
            fg_smooth = binary_closing(fg_mask, iterations=2).astype(np.uint8)
            fg_smooth = binary_opening(fg_smooth, iterations=1).astype(np.uint8)

            # Apply smoothed foreground: zero out pixels removed by opening,
            # keep original labels where foreground survived
            smoothed_labels = mask_data * fg_smooth

            for val in unique_values:
                binary_mask = (smoothed_labels == val).astype(np.uint8)

                # Skip if morphological ops removed this mask entirely
                if not binary_mask.any():
                    continue

                # Extract polygon from mask
                for geom, value in shapes(binary_mask, transform=transform):
                    if value == 1:
                        polygon = shape(geom)

                        # Filter small polygons (lowered from 5e-8 to catch more features)
                        if (
                            polygon.area < 2e-8
                        ):  # ~2m² in degrees — let vectorizer handle size filtering
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
