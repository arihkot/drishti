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
    """Shape-only fallback classifier (used when no satellite image available).

    Only returns 'road' or 'plot' — all non-road features are plots.
    """
    aspect = _shape_aspect(polygon)
    if aspect > 5.0 and area_sqm > 50:
        return "road"
    return "plot"


def classify_by_color_and_shape(
    polygon: Polygon,
    area_sqm: float,
    image: np.ndarray,
    meta: dict,
) -> str:
    """Classify a detected polygon as either 'road' or 'plot'.

    Uses satellite pixel colors and geometric shape to distinguish roads
    from plots. Everything that is not a road is classified as a plot.
    This keeps the output restricted to 3 categories: plot, road, boundary.

    Args:
        polygon: Shapely Polygon in EPSG:4326.
        area_sqm: Geodetic area of the polygon.
        image: RGB numpy array of the stitched satellite image.
        meta: Tile metadata with bbox and pixel_size fields.

    Returns:
        'road' or 'plot'.
    """
    from backend.services.tile_fetcher import lonlat_to_pixel

    aspect = _shape_aspect(polygon)

    # --- extract pixel crop for this polygon ---
    bounds = polygon.bounds  # (minLon, minLat, maxLon, maxLat)
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
    brightness = total / 3.0

    max_c = max(mean_r, mean_g, mean_b)
    min_c = min(mean_r, mean_g, mean_b)
    saturation = (max_c - min_c) / (max_c + 1e-6)  # 0..1

    # --- road detection rules ---

    # 1. Very elongated → road regardless of color
    if aspect > 5.0 and area_sqm > 50:
        return "road"

    # 2. Road-like pavement — gray, low saturation, somewhat elongated
    if saturation < 0.25 and 60 < brightness < 190 and aspect > 2.5:
        return "road"

    # Everything else is a plot (industrial/commercial land, buildings,
    # open land, vegetation — all treated as "plot" for CSIDC purposes)
    return "plot"


# ---- category → display colour mapping ----
# Restricted to 3 categories: plot, road, boundary
CATEGORY_COLORS: dict[str, str] = {
    "plot": "#ef4444",  # Red — industrial/commercial plots
    "road": "#64748b",  # Slate — roads & pavement
    "boundary": "#f97316",  # Orange — area boundary
}

# Human-readable labels for each category
CATEGORY_LABELS: dict[str, str] = {
    "plot": "Plot",
    "road": "Road",
    "boundary": "Boundary",
}


def get_color_for_category(category: str) -> str:
    """Get default display color for a category."""
    return CATEGORY_COLORS.get(category, CATEGORY_COLORS["plot"])


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


def renumber_labels(plots: list[dict]) -> list[dict]:
    """Re-number plot labels sequentially per category.

    After merge/clip steps remove some plots the original numbering has gaps
    (e.g. Plot 1, Plot 4, Plot 23).  This assigns clean sequential numbers
    (Plot 1, Plot 2, Plot 3…) while preserving category order.
    """
    counters: dict[str, int] = {}
    for plot in plots:
        cat = plot.get("category", "plot")
        counters[cat] = counters.get(cat, 0) + 1
        cat_label = CATEGORY_LABELS.get(cat, cat.capitalize())
        plot["label"] = f"{cat_label} {counters[cat]}"
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
    polygons: list[dict], overlap_threshold: float = 0.30
) -> list[dict]:
    """Merge polygons that overlap significantly.

    Uses 30% overlap threshold (lowered from 50%) to catch more cases
    where SAM creates overlapping detections for the same plot.
    """
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


def remove_contained_polygons(
    polygons: list[dict], containment_threshold: float = 0.35
) -> list[dict]:
    """Remove smaller polygons that are mostly contained inside larger ones.

    After merge and simplification, SAM may still produce nested detections
    where a smaller feature sits inside a larger one without exceeding the
    merge overlap threshold.  This pass removes the smaller polygon when
    >= containment_threshold of its area falls inside a larger polygon.

    Also removes polygons where the larger polygon covers a significant portion
    of the smaller one's bounding box, indicating the smaller is a sub-detection.

    Polygons are compared largest-first so that a small polygon contained
    by *any* larger one is dropped.

    Uses 35% threshold (lowered from 40%) to be more aggressive about
    removing nested detections that SAM creates inside larger plots.
    """
    if len(polygons) < 2:
        return polygons

    # Build (geom, idx) pairs sorted by area descending
    items = []
    for idx, p in enumerate(polygons):
        try:
            geom = shape(p["geometry"])
            if not geom.is_valid:
                geom = make_valid(geom)
            items.append((geom, idx))
        except Exception:
            items.append((None, idx))

    # Sort by area descending (largest first)
    items.sort(key=lambda x: x[0].area if x[0] else 0, reverse=True)

    drop = set()
    for pos_j in range(len(items)):
        geom_j, idx_j = items[pos_j]
        if geom_j is None or idx_j in drop:
            continue

        # Check against all larger polygons (earlier in sorted list)
        for pos_i in range(pos_j):
            geom_i, idx_i = items[pos_i]
            if geom_i is None or idx_i in drop:
                continue

            try:
                if not geom_i.intersects(geom_j):
                    continue

                intersection = geom_i.intersection(geom_j)
                # What fraction of the smaller polygon is inside the larger?
                ratio = intersection.area / (geom_j.area + 1e-12)

                if ratio >= containment_threshold:
                    drop.add(idx_j)
                    break  # Already dropping this one, no need to check more

                # Also check if the smaller polygon's centroid is inside the larger
                # This catches cases where overlap area is low but the small plot
                # is clearly inside the larger one
                if geom_i.contains(geom_j.centroid) and ratio >= 0.20:
                    drop.add(idx_j)
                    break
            except Exception:
                continue

    kept = [p for idx, p in enumerate(polygons) if idx not in drop]
    if drop:
        logger.info(
            f"Containment filter: removed {len(drop)} nested polygons, "
            f"{len(kept)} retained"
        )
    return kept


def merge_small_nearby_polygons(
    polygons: list[dict],
    proximity_degrees: float = 0.0003,  # ~30m at equator
    small_area_threshold_sqm: float = 2000.0,
) -> list[dict]:
    """Merge small nearby/overlapping polygons that should be one plot.

    SAM often fragments a single plot into multiple small detections.
    This function finds clusters of small polygons that are near each other
    (within proximity_degrees) and merges them into single polygons.

    Args:
        polygons: List of plot dicts with 'geometry' keys.
        proximity_degrees: Max gap between polygons to consider them neighbors.
        small_area_threshold_sqm: Polygons smaller than this are candidates for merging.

    Returns:
        List of plot dicts with small clusters merged.
    """
    if len(polygons) < 2:
        return polygons

    # Separate large plots (keep as-is) from small candidates
    large_plots = []
    small_items: list[tuple[Polygon, int]] = []

    for idx, p in enumerate(polygons):
        try:
            geom = shape(p["geometry"])
            if not geom.is_valid:
                geom = make_valid(geom)
            area_sqm = p.get("area_sqm", compute_geodetic_area(geom))
            if area_sqm >= small_area_threshold_sqm:
                large_plots.append(p)
            else:
                small_items.append((geom, idx))
        except Exception:
            large_plots.append(p)

    if len(small_items) < 2:
        return polygons  # nothing to merge

    # Build adjacency clusters: two small polygons are "neighbors" if
    # buffering one by proximity_degrees makes it intersect the other
    parent = list(range(len(small_items)))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    for i in range(len(small_items)):
        geom_i = small_items[i][0]
        buffered_i = geom_i.buffer(proximity_degrees)
        for j in range(i + 1, len(small_items)):
            geom_j = small_items[j][0]
            try:
                if buffered_i.intersects(geom_j):
                    union(i, j)
            except Exception:
                continue

    # Group clusters
    clusters: dict[int, list[int]] = {}
    for i in range(len(small_items)):
        root = find(i)
        clusters.setdefault(root, []).append(i)

    merged_plots = list(large_plots)
    singles_kept = 0
    clusters_merged = 0

    for members in clusters.values():
        if len(members) == 1:
            # Single small polygon — keep as-is
            idx = small_items[members[0]][1]
            merged_plots.append(polygons[idx])
            singles_kept += 1
        else:
            # Merge cluster into one polygon
            geoms = [small_items[m][0] for m in members]
            merged_geom = unary_union(geoms)

            if isinstance(merged_geom, MultiPolygon):
                merged_geom = max(merged_geom.geoms, key=lambda g: g.area)

            if not isinstance(merged_geom, Polygon):
                # Fallback: keep the largest member
                largest_idx = max(members, key=lambda m: small_items[m][0].area)
                merged_plots.append(polygons[small_items[largest_idx][1]])
                continue

            # Use the first member's metadata as base
            base_idx = small_items[members[0]][1]
            base_plot = polygons[base_idx].copy()

            area_sqm = compute_geodetic_area(merged_geom)
            base_plot["geometry"] = mapping(merged_geom)
            base_plot["area_sqm"] = round(area_sqm, 2)
            base_plot["area_sqft"] = round(sqm_to_sqft(area_sqm), 2)
            base_plot["perimeter_m"] = round(compute_geodetic_perimeter(merged_geom), 2)
            base_plot["centroid"] = [merged_geom.centroid.x, merged_geom.centroid.y]
            merged_plots.append(base_plot)
            clusters_merged += 1

    if clusters_merged > 0:
        logger.info(
            f"Small-nearby merge: {len(small_items)} small polygons → "
            f"{singles_kept} kept + {clusters_merged} merged clusters"
        )
    return merged_plots


def filter_noisy_polygons(
    polygons: list[dict],
    min_compactness: float = 0.08,
    min_area_sqm: float = 80.0,
    max_aspect_ratio: float = 12.0,
) -> list[dict]:
    """Remove noisy, distorted, or implausibly shaped polygons.

    Applies three shape quality filters beyond the existing area threshold:

    1. **Compactness** (Polsby-Popper score = 4*pi*area / perimeter^2).
       A circle scores 1.0, a square ~0.785.  Very distorted slivers
       score close to 0.  Polygons below min_compactness are dropped.

    2. **Minimum area** — a stricter area threshold for non-road features.
       Tiny "plot" detections under min_area_sqm are noise.

    3. **Aspect ratio** — bounding box aspect ratio > max_aspect_ratio
       is almost certainly a road fragment that wasn't classified as road.

    Only 'plot' category polygons are filtered; roads and boundaries pass through.

    Args:
        polygons: List of plot dicts with 'geometry', 'area_sqm', 'category'.
        min_compactness: Minimum Polsby-Popper score (0..1).
        min_area_sqm: Minimum area for plot polygons.
        max_aspect_ratio: Maximum bbox aspect ratio for plot polygons.

    Returns:
        Filtered list of plot dicts.
    """
    if not polygons:
        return polygons

    kept = []
    dropped_compactness = 0
    dropped_area = 0
    dropped_aspect = 0

    for p in polygons:
        category = p.get("category", "plot")

        # Only filter 'plot' category — roads/boundaries pass through
        if category != "plot":
            kept.append(p)
            continue

        area_sqm = p.get("area_sqm", 0)
        if area_sqm < min_area_sqm:
            dropped_area += 1
            continue

        try:
            geom = shape(p["geometry"])
            if not geom.is_valid:
                geom = make_valid(geom)

            # Compactness check (Polsby-Popper)
            perimeter = geom.length
            if perimeter > 0:
                compactness = (4.0 * math.pi * geom.area) / (perimeter**2)
            else:
                compactness = 0.0

            if compactness < min_compactness:
                dropped_compactness += 1
                continue

            # Aspect ratio check
            aspect = _shape_aspect(geom)
            if aspect > max_aspect_ratio:
                dropped_aspect += 1
                continue

        except Exception:
            pass  # If we can't analyse the shape, keep it

        kept.append(p)

    total_dropped = dropped_compactness + dropped_area + dropped_aspect
    if total_dropped > 0:
        logger.info(
            f"Noise filter: dropped {total_dropped} distorted polygons "
            f"(compactness={dropped_compactness}, area={dropped_area}, "
            f"aspect={dropped_aspect}), {len(kept)} retained"
        )

    return kept


def filter_unmatched_detected_plots(
    detected_plots: list[dict],
    csidc_plots: list[dict],
    overlap_threshold: float = 0.10,
) -> list[dict]:
    """Remove detected plots that have no matching CSIDC reference plot.

    A detected plot is kept if it overlaps with at least one CSIDC
    reference plot by >= overlap_threshold of the detected plot's area.
    Plots from the 'csidc_reference' source are always kept.

    Args:
        detected_plots: List of detected plot dicts.
        csidc_plots: List of CSIDC reference plot dicts with 'geometry'.
        overlap_threshold: Minimum overlap ratio to consider a match.

    Returns:
        Filtered list of detected plots.
    """
    if not csidc_plots or not detected_plots:
        return detected_plots

    # Build union of all CSIDC reference geometries
    ref_geoms = []
    for cp in csidc_plots:
        try:
            geom = cp.get("geometry")
            if not geom:
                continue
            g = shape(geom)
            if not g.is_valid:
                g = make_valid(g)
            ref_geoms.append(g)
        except Exception:
            continue

    if not ref_geoms:
        return detected_plots

    ref_union = unary_union(ref_geoms)

    kept = []
    dropped = 0

    for p in detected_plots:
        # Always keep non-plot features (roads, boundaries)
        category = p.get("category", "plot")
        if category != "plot":
            kept.append(p)
            continue

        # Always keep injected CSIDC reference plots
        if p.get("source") == "csidc_reference":
            kept.append(p)
            continue

        try:
            geom = shape(p["geometry"])
            if not geom.is_valid:
                geom = make_valid(geom)

            intersection = geom.intersection(ref_union)
            overlap_ratio = intersection.area / (geom.area + 1e-12)

            if overlap_ratio >= overlap_threshold:
                kept.append(p)
            else:
                dropped += 1
        except Exception:
            kept.append(p)  # keep on error

    if dropped > 0:
        logger.info(
            f"Unmatched filter: dropped {dropped} detected plots with no "
            f"CSIDC reference match, {len(kept)} retained"
        )

    return kept


def inject_missing_csidc_plots(
    detected_plots: list[dict],
    csidc_plots: list[dict],
    coverage_threshold: float = 0.25,
    image: np.ndarray | None = None,
    meta: dict | None = None,
) -> list[dict]:
    """Inject CSIDC reference plots that were completely missed by SAM detection.

    After SAM auto-detection + guided detection + vectorization, some CSIDC
    reference plots may still not be detected. This function checks each
    CSIDC reference plot against the already-detected plots. If a reference
    plot has less than coverage_threshold overlap with any detected plot,
    its geometry is injected directly as a detected plot.

    This ensures that known plots from the CSIDC reference map are always
    represented in the output, even if SAM couldn't segment them.

    Args:
        detected_plots: Already-detected and processed plot dicts.
        csidc_plots: CSIDC reference plot dicts with 'geometry' and 'name'.
        coverage_threshold: Min coverage ratio to consider a ref plot "found".
        image: Optional satellite image for color classification.
        meta: Optional tile metadata.

    Returns:
        Extended list of plot dicts with missing CSIDC plots injected.
    """
    if not csidc_plots:
        return detected_plots

    # Build union of all detected geometries
    detected_geoms = []
    for p in detected_plots:
        try:
            g = shape(p["geometry"])
            if not g.is_valid:
                g = make_valid(g)
            detected_geoms.append(g)
        except Exception:
            continue

    if detected_geoms:
        detected_union = unary_union(detected_geoms)
    else:
        detected_union = Polygon()  # empty

    injected = []
    use_color = image is not None and meta is not None

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

            if isinstance(ref_poly, MultiPolygon):
                ref_poly = max(ref_poly.geoms, key=lambda g: g.area)

            if not isinstance(ref_poly, Polygon):
                continue

            # Check coverage: how much of this CSIDC plot is already detected?
            try:
                intersection = ref_poly.intersection(detected_union)
                coverage = intersection.area / ref_poly.area if ref_poly.area > 0 else 0
            except Exception:
                coverage = 0.0

            if coverage >= coverage_threshold:
                continue  # Already detected

            # This plot was missed — inject its geometry
            simplified = simplify_polygon(ref_poly)
            area_sqm = compute_geodetic_area(simplified)

            if area_sqm < settings.MIN_POLYGON_AREA_SQM:
                continue

            # Classify
            if use_color:
                category = classify_by_color_and_shape(
                    simplified, area_sqm, image, meta
                )
            else:
                category = classify_polygon(simplified, area_sqm)

            plot_name = csidc_plot.get("name", "")
            label = f"{CATEGORY_LABELS.get(category, category.capitalize())} (Ref: {plot_name})"

            plot = {
                "label": label,
                "category": category,
                "geometry": mapping(simplified),
                "area_sqm": round(area_sqm, 2),
                "area_sqft": round(sqm_to_sqft(area_sqm), 2),
                "perimeter_m": round(compute_geodetic_perimeter(simplified), 2),
                "color": get_color_for_category(category),
                "confidence": 0.7,  # lower confidence since not SAM-detected
                "centroid": [simplified.centroid.x, simplified.centroid.y],
                "source": "csidc_reference",
            }
            injected.append(plot)

        except Exception as e:
            logger.warning(f"Error injecting CSIDC plot: {e}")
            continue

    if injected:
        logger.info(
            f"CSIDC injection: {len(injected)} missed ref plots injected "
            f"(out of {len(csidc_plots)} total ref plots)"
        )

    return detected_plots + injected
