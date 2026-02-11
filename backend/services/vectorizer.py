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


def simplify_polygon(polygon: Polygon, tolerance: float = None) -> Polygon:
    """
    Simplify polygon geometry.

    tolerance is in degrees; ~0.00001 degrees ≈ 1.1m at equator
    """
    if tolerance is None:
        tolerance = settings.SIMPLIFY_TOLERANCE * 0.00001  # convert meters to ~degrees

    simplified = polygon.simplify(tolerance, preserve_topology=True)

    if not simplified.is_valid:
        simplified = make_valid(simplified)

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
