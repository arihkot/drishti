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


def classify_polygon(polygon: Polygon, area_sqm: float) -> str:
    """Classify a polygon as parcel, road, or infrastructure based on geometry."""
    bounds = polygon.bounds
    width_deg = bounds[2] - bounds[0]
    height_deg = bounds[3] - bounds[1]

    # Aspect ratio
    if width_deg > 0 and height_deg > 0:
        aspect = max(width_deg, height_deg) / min(width_deg, height_deg)
    else:
        aspect = 1.0

    # Very elongated shapes are likely roads
    if aspect > 8.0 and area_sqm > 50:
        return "road"

    # Very small features are infrastructure
    if area_sqm < settings.MIN_POLYGON_AREA_SQM:
        return "infrastructure"

    # Default is parcel
    return "parcel"


def get_color_for_category(category: str) -> str:
    """Get default color for a category."""
    colors = {
        "parcel": "#FF0000",  # Red
        "road": "#00CED1",  # Dark Cyan
        "infrastructure": "#FFD700",  # Gold
        "other": "#9370DB",  # Medium Purple
    }
    return colors.get(category, "#FF0000")


def process_masks_to_plots(
    masks: list[dict],
    min_area_sqm: float = None,
) -> list[dict]:
    """
    Process raw SAM masks into classified, labeled plot features.

    Args:
        masks: List of dicts with 'geometry' (GeoJSON), 'mask_id', etc.
        min_area_sqm: Minimum area threshold

    Returns:
        List of processed plot dicts ready for DB insertion
    """
    if min_area_sqm is None:
        min_area_sqm = settings.MIN_POLYGON_AREA_SQM

    plots = []
    counters = {"parcel": 0, "road": 0, "infrastructure": 0, "other": 0}

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

        # Classify
        category = classify_polygon(simplified, area_sqm)
        counters[category] += 1

        # Generate label
        label = f"{category.capitalize()} {counters[category]}"
        if category == "road":
            label = f"Road {counters[category]}"

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

    logger.info(
        f"Processed {len(plots)} plots: "
        f"{counters['parcel']} parcels, {counters['road']} roads, "
        f"{counters['infrastructure']} infrastructure"
    )
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
