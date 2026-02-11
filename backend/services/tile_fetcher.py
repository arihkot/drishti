"""Satellite tile fetcher - downloads and stitches tiles into GeoTIFFs."""

import hashlib
import logging
import math
from pathlib import Path

import httpx
import mercantile
import numpy as np
from PIL import Image

from backend.config import settings

logger = logging.getLogger(__name__)

TIMEOUT = httpx.Timeout(30.0, connect=10.0)


def _tile_url(x: int, y: int, z: int) -> str:
    """Get ESRI satellite tile URL."""
    return settings.ESRI_SATELLITE_URL.format(x=x, y=y, z=z)


def bbox_to_tiles(bbox: list[float], zoom: int) -> list[mercantile.Tile]:
    """Convert bbox [minLon, minLat, maxLon, maxLat] to list of map tiles."""
    west, south, east, north = bbox
    tiles = list(mercantile.tiles(west, south, east, north, zooms=zoom))
    return tiles


def tiles_grid(
    tiles: list[mercantile.Tile],
) -> tuple[list[list[mercantile.Tile]], int, int]:
    """Organize tiles into a grid (rows x cols)."""
    if not tiles:
        return [], 0, 0

    min_x = min(t.x for t in tiles)
    max_x = max(t.x for t in tiles)
    min_y = min(t.y for t in tiles)
    max_y = max(t.y for t in tiles)

    cols = max_x - min_x + 1
    rows = max_y - min_y + 1

    grid = [[None] * cols for _ in range(rows)]
    for t in tiles:
        row = t.y - min_y
        col = t.x - min_x
        grid[row][col] = t

    return grid, rows, cols


def bbox_hash(bbox: list[float], zoom: int) -> str:
    """Create a deterministic hash for a bbox+zoom combination."""
    key = f"{bbox[0]:.6f}_{bbox[1]:.6f}_{bbox[2]:.6f}_{bbox[3]:.6f}_{zoom}"
    return hashlib.md5(key.encode()).hexdigest()[:12]


async def fetch_tile(
    client: httpx.AsyncClient, tile: mercantile.Tile
) -> np.ndarray | None:
    """Fetch a single tile and return as numpy array."""
    url = _tile_url(tile.x, tile.y, tile.z)
    try:
        resp = await client.get(url)
        resp.raise_for_status()
        img = Image.open(__import__("io").BytesIO(resp.content))
        return np.array(img.convert("RGB"))
    except Exception as e:
        logger.warning(f"Failed to fetch tile {tile}: {e}")
        return None


async def fetch_satellite_image(
    bbox: list[float], zoom: int = None
) -> tuple[np.ndarray, dict]:
    """
    Fetch satellite imagery for a bounding box.

    Returns:
        tuple of (image as numpy RGB array, metadata dict with bounds info)
    """
    if zoom is None:
        zoom = settings.DEFAULT_TILE_ZOOM

    # Check cache first
    cache_key = bbox_hash(bbox, zoom)
    cache_path = settings.TILES_DIR / f"{cache_key}.npy"
    meta_path = settings.TILES_DIR / f"{cache_key}_meta.npy"

    if cache_path.exists() and meta_path.exists():
        logger.info(f"Using cached satellite image: {cache_key}")
        image = np.load(str(cache_path))
        meta = np.load(str(meta_path), allow_pickle=True).item()
        return image, meta

    tiles = bbox_to_tiles(bbox, zoom)
    if not tiles:
        raise ValueError(f"No tiles found for bbox {bbox} at zoom {zoom}")

    logger.info(f"Fetching {len(tiles)} tiles at zoom {zoom} for bbox {bbox}")

    grid, rows, cols = tiles_grid(tiles)
    tile_size = 256

    # Fetch all tiles
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        tile_images = {}
        for row in grid:
            for tile in row:
                if tile:
                    img = await fetch_tile(client, tile)
                    if img is not None:
                        tile_images[tile] = img

    # Stitch into single image
    stitched = np.zeros((rows * tile_size, cols * tile_size, 3), dtype=np.uint8)
    for r, row in enumerate(grid):
        for c, tile in enumerate(row):
            if tile and tile in tile_images:
                y_start = r * tile_size
                x_start = c * tile_size
                img = tile_images[tile]
                h, w = img.shape[:2]
                stitched[y_start : y_start + h, x_start : x_start + w] = img

    # Compute actual bounds of the stitched image
    first_tile = tiles[0]
    last_tile = tiles[-1]
    all_x = [t.x for t in tiles]
    all_y = [t.y for t in tiles]
    min_tile = mercantile.Tile(min(all_x), min(all_y), zoom)
    max_tile = mercantile.Tile(max(all_x), max(all_y), zoom)

    min_bounds = mercantile.bounds(min_tile)
    max_bounds = mercantile.bounds(max_tile)

    actual_bbox = [
        min_bounds.west,
        max_bounds.south,
        max_bounds.east,
        min_bounds.north,
    ]

    meta = {
        "bbox": actual_bbox,
        "requested_bbox": bbox,
        "zoom": zoom,
        "tiles_x": cols,
        "tiles_y": rows,
        "width": cols * tile_size,
        "height": rows * tile_size,
        "pixel_size_lon": (actual_bbox[2] - actual_bbox[0]) / (cols * tile_size),
        "pixel_size_lat": (actual_bbox[3] - actual_bbox[1]) / (rows * tile_size),
    }

    # Cache
    np.save(str(cache_path), stitched)
    np.save(str(meta_path), meta)

    logger.info(f"Stitched image: {stitched.shape}, cached as {cache_key}")
    return stitched, meta


def pixel_to_lonlat(px: int, py: int, meta: dict) -> tuple[float, float]:
    """Convert pixel coordinates to lon/lat."""
    lon = meta["bbox"][0] + px * meta["pixel_size_lon"]
    lat = meta["bbox"][3] - py * meta["pixel_size_lat"]  # y is inverted
    return lon, lat


def lonlat_to_pixel(lon: float, lat: float, meta: dict) -> tuple[int, int]:
    """Convert lon/lat to pixel coordinates."""
    px = int((lon - meta["bbox"][0]) / meta["pixel_size_lon"])
    py = int((meta["bbox"][3] - lat) / meta["pixel_size_lat"])
    return px, py
