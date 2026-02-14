"""Green cover analysis using RGB satellite imagery.

Computes vegetation percentage for each plot polygon by applying
the Excess Green Index (ExG = 2G - R - B) to the satellite image
pixels within the polygon's bounding box.  This is a reliable
proxy for green cover from standard RGB imagery without needing
multispectral NDVI data.
"""

import logging

import numpy as np
from shapely.geometry import Polygon, shape

from backend.services.tile_fetcher import lonlat_to_pixel

logger = logging.getLogger(__name__)

# ExG threshold — pixels with normalised ExG above this are "green".
# Tuned for ESRI World Imagery where vegetation is clearly green but
# not as vivid as drone imagery.  A value of 0.08 means the green
# channel must exceed the average of R and B by at least ~8%.
EXG_THRESHOLD = 0.08

# Minimum pixel crop size to attempt analysis (avoids noise on tiny crops)
MIN_CROP_PIXELS = 25


def compute_green_cover_pct(
    polygon_geojson: dict,
    image: np.ndarray,
    meta: dict,
) -> float | None:
    """Compute green cover percentage for a single plot polygon.

    Args:
        polygon_geojson: GeoJSON geometry dict of the plot polygon.
        image: RGB numpy array of the stitched satellite image.
        meta: Tile metadata with bbox and pixel_size fields.

    Returns:
        Green cover percentage (0.0 – 100.0), or None if analysis fails.
    """
    try:
        poly = shape(polygon_geojson)
        if not isinstance(poly, Polygon) or poly.is_empty:
            return None

        bounds = poly.bounds  # (minLon, minLat, maxLon, maxLat)
        min_px, min_py = lonlat_to_pixel(bounds[0], bounds[3], meta)  # top-left
        max_px, max_py = lonlat_to_pixel(bounds[2], bounds[1], meta)  # bottom-right

        h, w = image.shape[:2]
        min_px = max(0, min(min_px, w - 1))
        max_px = max(0, min(max_px, w - 1))
        min_py = max(0, min(min_py, h - 1))
        max_py = max(0, min(max_py, h - 1))

        if max_px <= min_px or max_py <= min_py:
            return None

        crop = image[min_py:max_py, min_px:max_px]
        if crop.size == 0 or crop.shape[0] * crop.shape[1] < MIN_CROP_PIXELS:
            return None

        # Compute Excess Green Index per pixel
        # ExG = (2*G - R - B) / (R + G + B + epsilon)
        r = crop[:, :, 0].astype(np.float32)
        g = crop[:, :, 1].astype(np.float32)
        b = crop[:, :, 2].astype(np.float32)

        total = r + g + b + 1e-6
        exg = (2.0 * g - r - b) / total

        # Count pixels exceeding the green threshold
        green_pixels = np.sum(exg > EXG_THRESHOLD)
        total_pixels = crop.shape[0] * crop.shape[1]

        pct = float(green_pixels / total_pixels) * 100.0
        return round(pct, 2)

    except Exception as e:
        logger.warning(f"Green cover analysis failed for polygon: {e}")
        return None


def analyse_plots_green_cover(
    plots: list[dict],
    image: np.ndarray,
    meta: dict,
    threshold_pct: float = 20.0,
) -> list[dict]:
    """Analyse green cover for a list of detected plots.

    Args:
        plots: List of plot dicts (must have 'geometry' key with GeoJSON).
        image: RGB satellite image numpy array.
        meta: Tile metadata.
        threshold_pct: Minimum green cover % to be considered compliant.

    Returns:
        List of dicts with green cover results per plot:
        [{"plot_index": int, "label": str, "green_cover_pct": float,
          "is_compliant": bool}, ...]
    """
    results = []
    for idx, plot in enumerate(plots):
        geom = plot.get("geometry")
        if not geom:
            continue

        # Only analyse actual plots, skip roads / boundaries
        category = plot.get("category", "plot")
        if category != "plot":
            continue

        pct = compute_green_cover_pct(geom, image, meta)
        if pct is None:
            continue

        results.append(
            {
                "plot_index": idx,
                "plot_id": plot.get("id"),
                "label": plot.get("label", f"Plot {idx + 1}"),
                "green_cover_pct": pct,
                "is_compliant": pct >= threshold_pct,
            }
        )

    compliant = sum(1 for r in results if r["is_compliant"])
    logger.info(
        f"Green cover analysis: {len(results)} plots analysed, "
        f"{compliant} compliant (>= {threshold_pct}%), "
        f"{len(results) - compliant} non-compliant"
    )
    return results
