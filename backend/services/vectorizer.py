"""Vectorization pipeline - converts SAM masks to clean vector polygons."""

import logging
import math
from typing import Any

import numpy as np
from pyproj import Geod
from shapely.geometry import MultiPolygon, Polygon, mapping, shape
from shapely.ops import unary_union
from shapely.validation import make_valid

from backend.config import settings

logger = logging.getLogger(__name__)

# WGS84 ellipsoid for area calculation
geod = Geod(ellps="WGS84")


def compute_geodetic_area(polygon: Polygon) -> float:
    """Compute geodetic area in square meters for a WGS84 polygon."""
    try:
        area, _ = geod.geometry_area_perimeter(polygon)
        return abs(area)
    except Exception:
        return 0.0


def compute_geodetic_perimeter(polygon: Polygon) -> float:
    """Compute geodetic perimeter in meters."""
    try:
        _, perimeter = geod.geometry_area_perimeter(polygon)
        return abs(perimeter)
    except Exception:
        return 0.0


def sqm_to_sqft(sqm: float) -> float:
    """Convert square meters to square feet."""
    return sqm * 10.7639


def _chaikin_smooth(coords: list, iterations: int = 2) -> list:
    """Apply Chaikin corner-cutting algorithm to smooth polygon coordinates.

    Each iteration replaces each segment with two new points at 1/4 and 3/4
    along the segment, rounding sharp pixel-grid corners into smooth curves.
    """
    for _ in range(iterations):
        if len(coords) < 3:
            break
        new_coords = []
        for i in range(len(coords) - 1):
            p0 = coords[i]
            p1 = coords[i + 1]
            # Q = 3/4 * P0 + 1/4 * P1
            q = (0.75 * p0[0] + 0.25 * p1[0], 0.75 * p0[1] + 0.25 * p1[1])
            # R = 1/4 * P0 + 3/4 * P1
            r = (0.25 * p0[0] + 0.75 * p1[0], 0.25 * p0[1] + 0.75 * p1[1])
            new_coords.append(q)
            new_coords.append(r)
        # Close ring
        new_coords.append(new_coords[0])
        coords = new_coords
    return coords


def simplify_polygon(polygon: Polygon, tolerance: float = None) -> Polygon:
    """
    Simplify and smooth polygon geometry.

    Pipeline:
    1. Morphological buffer open (tiny buffer out then in) to remove pixel jaggies
    2. Chaikin corner-cutting to round angular pixel-grid corners
    3. Douglas-Peucker simplification to reduce point count

    tolerance is in degrees; ~0.00001 degrees ≈ 1.1m at equator
    """
    if tolerance is None:
        tolerance = settings.SIMPLIFY_TOLERANCE * 0.00001  # convert meters to ~degrees

    # Step 1: morphological open — smooth pixel staircase edges
    buf_dist = tolerance * 0.5
    smoothed = polygon.buffer(buf_dist).buffer(-buf_dist)

    if smoothed.is_empty:
        smoothed = polygon  # fallback if buffer collapses tiny polygon

    # Handle MultiPolygon from buffer — take the largest
    if isinstance(smoothed, MultiPolygon):
        smoothed = max(smoothed.geoms, key=lambda g: g.area)

    if not isinstance(smoothed, Polygon):
        smoothed = polygon

    # Step 2: Chaikin corner-cutting on the exterior ring
    exterior_coords = list(smoothed.exterior.coords)
    smooth_exterior = _chaikin_smooth(exterior_coords, iterations=2)

    # Apply to holes too
    smooth_holes = []
    for hole in smoothed.interiors:
        smooth_holes.append(_chaikin_smooth(list(hole.coords), iterations=2))

    smoothed = Polygon(smooth_exterior, smooth_holes)

    # Step 3: Douglas-Peucker simplification
    simplified = smoothed.simplify(tolerance, preserve_topology=True)

    if not simplified.is_valid:
        simplified = make_valid(simplified)

    # Final safety: ensure it's a Polygon
    if isinstance(simplified, MultiPolygon):
        simplified = max(simplified.geoms, key=lambda g: g.area)

    return simplified


def _shape_aspect(polygon: Polygon) -> float:
    """Compute bounding-box aspect ratio of a polygon."""
    b = polygon.bounds
    w = b[2] - b[0]
    h = b[3] - b[1]
    if w > 0 and h > 0:
        return max(w, h) / min(w, h)
    return 1.0


def classify_polygon(polygon: Polygon, area_sqm: float) -> str:
    """Shape-only fallback classifier (used when no satellite image available)."""
    aspect = _shape_aspect(polygon)
    if aspect > 6.0 and area_sqm > 50:
        return "road"
    if area_sqm < settings.MIN_POLYGON_AREA_SQM:
        return "infrastructure"
    return "plot"


def classify_by_color_and_shape(
    polygon: Polygon,
    area_sqm: float,
    image: np.ndarray,
    meta: dict,
) -> str:
    """Classify a detected polygon using satellite pixel colors + shape.

    Analyses the mean RGB values within the polygon's bounding box from the
    satellite image and combines with geometric properties to assign one of:
        plot, road, vegetation, open_land, water, building

    Args:
        polygon: Shapely Polygon in EPSG:4326.
        area_sqm: Geodetic area of the polygon.
        image: RGB numpy array of the stitched satellite image.
        meta: Tile metadata with bbox and pixel_size fields.

    Returns:
        Category string.
    """
    from backend.services.tile_fetcher import lonlat_to_pixel

    aspect = _shape_aspect(polygon)

    # --- extract pixel crop for this polygon ---
    bounds = (
        polygon.bounds
    )  # (minx, miny, maxx, maxy) = (minLon, minLat, maxLon, maxLat)
    min_px, min_py = lonlat_to_pixel(bounds[0], bounds[3], meta)  # top-left
    max_px, max_py = lonlat_to_pixel(bounds[2], bounds[1], meta)  # bottom-right

    h, w = image.shape[:2]
    min_px = max(0, min(min_px, w - 1))
    max_px = max(0, min(max_px, w - 1))
    min_py = max(0, min(min_py, h - 1))
    max_py = max(0, min(max_py, h - 1))

    if max_px <= min_px or max_py <= min_py:
        return classify_polygon(polygon, area_sqm)  # fallback

    crop = image[min_py:max_py, min_px:max_px]
    if crop.size == 0:
        return classify_polygon(polygon, area_sqm)

    # --- compute color statistics ---
    mean_r = float(crop[:, :, 0].mean())
    mean_g = float(crop[:, :, 1].mean())
    mean_b = float(crop[:, :, 2].mean())

    total = mean_r + mean_g + mean_b + 1e-6
    g_ratio = mean_g / total
    b_ratio = mean_b / total
    r_ratio = mean_r / total

    # Green index  (G - R) / (G + R)  — positive = green-dominant
    green_idx = (mean_g - mean_r) / (mean_g + mean_r + 1e-6)

    brightness = total / 3.0

    max_c = max(mean_r, mean_g, mean_b)
    min_c = min(mean_r, mean_g, mean_b)
    saturation = (max_c - min_c) / (max_c + 1e-6)  # 0..1

    # --- classification rules (order matters) ---

    # 1. Very elongated → road regardless of color
    if aspect > 6.0 and area_sqm > 50:
        return "road"

    # 2. Water — blue-dominant
    if b_ratio > 0.38 and mean_b > mean_g and mean_b > mean_r:
        return "water"

    # 3. Vegetation — green-dominant
    if green_idx > 0.04 and g_ratio > 0.36:
        return "vegetation"

    # 4. Road (non-elongated pavement / parking) — gray, low saturation
    if saturation < 0.15 and 80 < brightness < 180 and aspect > 3.0:
        return "road"

    # 5. Open / vacant land — warm earthy tones, low-moderate sat
    if r_ratio > 0.36 and g_ratio > 0.30 and saturation < 0.25 and brightness < 170:
        return "open_land"

    # 6. Small structures → building
    if area_sqm < 200 and saturation < 0.3:
        return "building"

    # 7. Bright concrete rooftops → building
    if brightness > 190 and saturation < 0.18 and area_sqm < 2000:
        return "building"

    # 8. Tiny features
    if area_sqm < settings.MIN_POLYGON_AREA_SQM:
        return "infrastructure"

    # Default: built-up industrial / commercial plot
    return "plot"


# ---- category → display colour mapping ----
CATEGORY_COLORS: dict[str, str] = {
    "plot": "#ef4444",  # Red — industrial/commercial plots
    "road": "#64748b",  # Slate — roads & pavement
    "vegetation": "#22c55e",  # Green — parks, trees, green belt
    "open_land": "#d97706",  # Amber — vacant / bare land
    "water": "#3b82f6",  # Blue — water bodies
    "building": "#a855f7",  # Purple — individual structures
    "infrastructure": "#f59e0b",  # Yellow — utility infra
    "other": "#6b7280",  # Gray — unclassified
}

# Human-readable labels for each category
CATEGORY_LABELS: dict[str, str] = {
    "plot": "Plot",
    "road": "Road",
    "vegetation": "Vegetation",
    "open_land": "Open Land",
    "water": "Water",
    "building": "Building",
    "infrastructure": "Infrastructure",
    "other": "Other",
}


def get_color_for_category(category: str) -> str:
    """Get default display color for a category."""
    return CATEGORY_COLORS.get(category, CATEGORY_COLORS["other"])


def process_masks_to_plots(
    masks: list[dict],
    min_area_sqm: float = None,
    image: np.ndarray | None = None,
    meta: dict | None = None,
) -> list[dict]:
    """
    Process raw SAM masks into classified, labeled plot features.

    Args:
        masks: List of dicts with 'geometry' (GeoJSON), 'mask_id', etc.
        min_area_sqm: Minimum area threshold
        image: Optional RGB satellite image for color-based classification.
        meta: Optional tile metadata (required if image is provided).

    Returns:
        List of processed plot dicts ready for DB insertion
    """
    if min_area_sqm is None:
        min_area_sqm = settings.MIN_POLYGON_AREA_SQM

    use_color = image is not None and meta is not None

    plots = []
    counters: dict[str, int] = {}

    # Sort masks by area (largest first)
    processed_masks = []
    for mask in masks:
        try:
            geom = shape(mask["geometry"])
            if not geom.is_valid:
                geom = make_valid(geom)

            # Handle MultiPolygon - take largest
            if isinstance(geom, MultiPolygon):
                geom = max(geom.geoms, key=lambda g: g.area)

            if not isinstance(geom, Polygon):
                continue

            area_sqm = compute_geodetic_area(geom)
            processed_masks.append((geom, area_sqm, mask))
        except Exception as e:
            logger.warning(f"Failed to process mask {mask.get('mask_id')}: {e}")
            continue

    processed_masks.sort(key=lambda x: x[1], reverse=True)

    for geom, area_sqm, mask in processed_masks:
        if area_sqm < min_area_sqm:
            continue

        # Simplify geometry
        simplified = simplify_polygon(geom)

        # Classify — prefer color+shape when satellite image available
        if use_color:
            category = classify_by_color_and_shape(simplified, area_sqm, image, meta)
        else:
            category = classify_polygon(simplified, area_sqm)

        counters[category] = counters.get(category, 0) + 1

        # Generate label
        cat_label = CATEGORY_LABELS.get(category, category.capitalize())
        label = f"{cat_label} {counters[category]}"

        # Compute perimeter
        perimeter = compute_geodetic_perimeter(simplified)

        plot = {
            "label": label,
            "category": category,
            "geometry": mapping(simplified),
            "area_sqm": round(area_sqm, 2),
            "area_sqft": round(sqm_to_sqft(area_sqm), 2),
            "perimeter_m": round(perimeter, 2),
            "color": get_color_for_category(category),
            "confidence": mask.get("confidence", None),
            "centroid": [simplified.centroid.x, simplified.centroid.y],
        }
        plots.append(plot)

    summary_parts = [f"{v} {k}" for k, v in sorted(counters.items())]
    logger.info(f"Processed {len(plots)} features: {', '.join(summary_parts)}")
    return plots


def clip_to_boundary(plots: list[dict], boundary_geojson: dict) -> list[dict]:
    """
    Clip detected plots to the area boundary.

    Keeps only plots that intersect the boundary polygon. Plots partially
    outside are clipped to the boundary.

    Args:
        plots: List of processed plot dicts with 'geometry' keys.
        boundary_geojson: GeoJSON geometry dict of the area boundary.

    Returns:
        Filtered & clipped list of plot dicts.
    """
    try:
        boundary = shape(boundary_geojson)
        if not boundary.is_valid:
            boundary = make_valid(boundary)
    except Exception as e:
        logger.warning(f"Invalid boundary geometry, skipping clip: {e}")
        return plots

    clipped = []
    for plot in plots:
        try:
            geom = shape(plot["geometry"])
            if not geom.is_valid:
                geom = make_valid(geom)

            if not geom.intersects(boundary):
                continue

            # Clip to boundary
            intersection = geom.intersection(boundary)

            if intersection.is_empty:
                continue

            # Handle MultiPolygon — take largest piece
            if isinstance(intersection, MultiPolygon):
                intersection = max(intersection.geoms, key=lambda g: g.area)

            if not isinstance(intersection, Polygon):
                continue

            # Recompute area for the clipped geometry
            area_sqm = compute_geodetic_area(intersection)
            if area_sqm < settings.MIN_POLYGON_AREA_SQM:
                continue

            clipped_plot = plot.copy()
            clipped_plot["geometry"] = mapping(intersection)
            clipped_plot["area_sqm"] = round(area_sqm, 2)
            clipped_plot["area_sqft"] = round(sqm_to_sqft(area_sqm), 2)
            clipped_plot["perimeter_m"] = round(
                compute_geodetic_perimeter(intersection), 2
            )
            clipped_plot["centroid"] = [
                intersection.centroid.x,
                intersection.centroid.y,
            ]
            clipped.append(clipped_plot)
        except Exception as e:
            logger.warning(f"Failed to clip plot: {e}")
            continue

    logger.info(f"Clipped {len(plots)} plots to boundary → {len(clipped)} retained")
    return clipped


def merge_overlapping_polygons(
    polygons: list[dict], overlap_threshold: float = 0.5
) -> list[dict]:
    """Merge polygons that overlap significantly."""
    if not polygons:
        return polygons

    shapes_list = [(shape(p["geometry"]), p) for p in polygons]
    merged = []
    used = set()

    for i, (geom_i, plot_i) in enumerate(shapes_list):
        if i in used:
            continue

        current = geom_i
        for j, (geom_j, plot_j) in enumerate(shapes_list):
            if j <= i or j in used:
                continue

            try:
                intersection = current.intersection(geom_j)
                overlap_ratio = intersection.area / min(current.area, geom_j.area)

                if overlap_ratio > overlap_threshold:
                    current = unary_union([current, geom_j])
                    used.add(j)
            except Exception:
                continue

        used.add(i)
        plot = plot_i.copy()
        plot["geometry"] = mapping(current)
        area_sqm = compute_geodetic_area(current)
        plot["area_sqm"] = round(area_sqm, 2)
        plot["area_sqft"] = round(sqm_to_sqft(area_sqm), 2)
        merged.append(plot)

    return merged
