"""Geometry comparison engine for deviation detection."""

import json
import logging
from typing import Any

from pyproj import Geod
from shapely.geometry import MultiPolygon, Polygon, mapping, shape
from shapely.ops import unary_union
from shapely.validation import make_valid

from backend.config import settings

logger = logging.getLogger(__name__)

geod = Geod(ellps="WGS84")


def compute_area_sqm(geometry) -> float:
    """Compute geodetic area in square meters."""
    try:
        area, _ = geod.geometry_area_perimeter(geometry)
        return abs(area)
    except Exception:
        return 0.0


def hausdorff_distance_approx(geom1, geom2) -> float:
    """Approximate Hausdorff distance between two geometries in degrees."""
    try:
        return geom1.hausdorff_distance(geom2)
    except Exception:
        return float("inf")


def classify_deviation(
    detected: Polygon,
    basemap: Polygon,
    tolerance_m: float = None,
) -> dict[str, Any]:
    """
    Compare a detected polygon against a basemap polygon and classify deviation.

    Returns a dict with deviation type, severity, and details.
    """
    if tolerance_m is None:
        tolerance_m = settings.ENCROACHMENT_TOLERANCE_M

    # Convert tolerance from meters to approximate degrees
    tolerance_deg = tolerance_m * 0.00001

    result = {
        "deviation_type": "COMPLIANT",
        "severity": "low",
        "deviation_area_sqm": 0.0,
        "match_percentage": 100.0,
        "deviation_geometry": None,
        "description": "",
        "details": {},
    }

    try:
        if not detected.is_valid:
            detected = make_valid(detected)
        if not basemap.is_valid:
            basemap = make_valid(basemap)

        # Ensure we have Polygon types
        if isinstance(detected, MultiPolygon):
            detected = max(detected.geoms, key=lambda g: g.area)
        if isinstance(basemap, MultiPolygon):
            basemap = max(basemap.geoms, key=lambda g: g.area)

        detected_area = compute_area_sqm(detected)
        basemap_area = compute_area_sqm(basemap)

        # Compute intersection
        intersection = detected.intersection(basemap)
        intersection_area = compute_area_sqm(intersection)

        # Compute difference (detected outside basemap = potential encroachment)
        encroachment = detected.difference(basemap)
        encroachment_area = compute_area_sqm(encroachment)

        # Compute unused (basemap area not covered by detected = vacant)
        vacant = basemap.difference(detected)
        vacant_area = compute_area_sqm(vacant)

        # Match percentage
        if basemap_area > 0:
            match_pct = (intersection_area / basemap_area) * 100
        else:
            match_pct = 0.0

        # Hausdorff distance for boundary alignment
        hausdorff = hausdorff_distance_approx(detected.boundary, basemap.boundary)

        result["details"] = {
            "detected_area_sqm": round(detected_area, 2),
            "basemap_area_sqm": round(basemap_area, 2),
            "intersection_area_sqm": round(intersection_area, 2),
            "encroachment_area_sqm": round(encroachment_area, 2),
            "vacant_area_sqm": round(vacant_area, 2),
            "hausdorff_distance_deg": round(hausdorff, 8),
            "match_percentage": round(match_pct, 2),
        }
        result["match_percentage"] = round(match_pct, 2)

        # Classification logic
        encroachment_ratio = encroachment_area / max(basemap_area, 1)
        vacant_ratio = vacant_area / max(basemap_area, 1)

        if encroachment_ratio > 0.15:
            result["deviation_type"] = "ENCROACHMENT"
            result["deviation_area_sqm"] = round(encroachment_area, 2)
            result["severity"] = "critical" if encroachment_ratio > 0.3 else "high"
            result["description"] = (
                f"Significant encroachment detected: {round(encroachment_area, 1)} sq.m "
                f"({round(encroachment_ratio * 100, 1)}%) extends beyond allotted boundary."
            )
            if not encroachment.is_empty:
                result["deviation_geometry"] = mapping(encroachment)

        elif encroachment_ratio > 0.05:
            result["deviation_type"] = "BOUNDARY_MISMATCH"
            result["deviation_area_sqm"] = round(encroachment_area, 2)
            result["severity"] = "medium"
            result["description"] = (
                f"Boundary mismatch: {round(encroachment_area, 1)} sq.m "
                f"({round(encroachment_ratio * 100, 1)}%) deviates from allotted boundary."
            )
            if not encroachment.is_empty:
                result["deviation_geometry"] = mapping(encroachment)

        elif vacant_ratio > 0.7:
            result["deviation_type"] = "VACANT"
            result["deviation_area_sqm"] = round(vacant_area, 2)
            result["severity"] = "medium"
            result["description"] = (
                f"Plot appears largely vacant: {round(vacant_area, 1)} sq.m "
                f"({round(vacant_ratio * 100, 1)}%) of allotted area is unused."
            )
            if not vacant.is_empty:
                result["deviation_geometry"] = mapping(vacant)

        elif match_pct < 50:
            result["deviation_type"] = "UNAUTHORIZED_DEVELOPMENT"
            result["deviation_area_sqm"] = round(encroachment_area, 2)
            result["severity"] = "high"
            result["description"] = (
                f"Low overlap with basemap ({round(match_pct, 1)}%). "
                f"Possible unauthorized development."
            )
            sym_diff = detected.symmetric_difference(basemap)
            if not sym_diff.is_empty:
                result["deviation_geometry"] = mapping(sym_diff)

        else:
            result["deviation_type"] = "COMPLIANT"
            result["severity"] = "low"
            result["description"] = (
                f"Plot is compliant. {round(match_pct, 1)}% overlap with allotted boundary."
            )

    except Exception as e:
        logger.error(f"Comparison error: {e}")
        result["deviation_type"] = "ERROR"
        result["severity"] = "low"
        result["description"] = f"Comparison failed: {str(e)}"

    return result


def compare_project_with_basemap(
    detected_plots: list[dict],
    basemap_features: list[dict],
    tolerance_m: float = None,
) -> dict[str, Any]:
    """
    Compare all detected plots against basemap features.

    Uses spatial matching to pair detected polygons with basemap polygons.
    """
    if tolerance_m is None:
        tolerance_m = settings.ENCROACHMENT_TOLERANCE_M

    results = {
        "summary": {
            "total": len(detected_plots),
            "total_detected": len(detected_plots),
            "total_basemap": len(basemap_features),
            "compliant": 0,
            "encroachment": 0,
            "boundary_mismatch": 0,
            "vacant": 0,
            "unauthorized": 0,
            "unmatched_detected": 0,
            "unmatched_basemap": 0,
        },
        "deviations": [],
        "unmatched_detected": [],
        "unmatched_basemap": [],
    }

    # Convert to shapely geometries
    detected_geoms = []
    for plot in detected_plots:
        try:
            geom = shape(plot["geometry"])
            if not geom.is_valid:
                geom = make_valid(geom)
            detected_geoms.append((geom, plot))
        except Exception as e:
            logger.warning(f"Invalid detected geometry: {e}")

    basemap_geoms = []
    for feature in basemap_features:
        try:
            geom_data = feature.get("geometry", feature)
            geom = shape(geom_data)
            if not geom.is_valid:
                geom = make_valid(geom)
            basemap_geoms.append((geom, feature))
        except Exception as e:
            logger.warning(f"Invalid basemap geometry: {e}")

    # Spatial matching: find best overlap for each detected polygon
    matched_basemap = set()

    for det_geom, det_plot in detected_geoms:
        best_match = None
        best_overlap = 0.0

        for i, (bm_geom, bm_feature) in enumerate(basemap_geoms):
            if i in matched_basemap:
                continue

            try:
                if not det_geom.intersects(bm_geom):
                    continue

                intersection = det_geom.intersection(bm_geom)
                overlap = compute_area_sqm(intersection)

                if overlap > best_overlap:
                    best_overlap = overlap
                    best_match = (i, bm_geom, bm_feature)
            except Exception:
                continue

        if best_match:
            idx, bm_geom, bm_feature = best_match
            matched_basemap.add(idx)

            deviation = classify_deviation(det_geom, bm_geom, tolerance_m)
            deviation["plot_label"] = det_plot.get("label", "Unknown")
            deviation["plot_id"] = det_plot.get("id")
            deviation["basemap_name"] = bm_feature.get("properties", {}).get(
                "ia_name", bm_feature.get("name", "Unknown")
            )

            results["deviations"].append(deviation)

            # Update summary
            dev_type = deviation["deviation_type"]
            if dev_type == "COMPLIANT":
                results["summary"]["compliant"] += 1
            elif dev_type == "ENCROACHMENT":
                results["summary"]["encroachment"] += 1
            elif dev_type == "BOUNDARY_MISMATCH":
                results["summary"]["boundary_mismatch"] += 1
            elif dev_type == "VACANT":
                results["summary"]["vacant"] += 1
            elif dev_type == "UNAUTHORIZED_DEVELOPMENT":
                results["summary"]["unauthorized"] += 1
        else:
            results["unmatched_detected"].append(
                {
                    "label": det_plot.get("label", "Unknown"),
                    "geometry": mapping(det_geom),
                    "area_sqm": round(compute_area_sqm(det_geom), 2),
                }
            )
            results["summary"]["unmatched_detected"] += 1

    # Find unmatched basemap features (plots that exist in basemap but no detected match)
    for i, (bm_geom, bm_feature) in enumerate(basemap_geoms):
        if i not in matched_basemap:
            results["unmatched_basemap"].append(
                {
                    "name": bm_feature.get("properties", {}).get("ia_name", "Unknown"),
                    "geometry": mapping(bm_geom),
                    "area_sqm": round(compute_area_sqm(bm_geom), 2),
                }
            )
            results["summary"]["unmatched_basemap"] += 1

    return results
