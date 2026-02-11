"""Areas router - CSIDC area listing and basemap proxy."""

import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.models import BasemapCache
from backend.services.csidc_client import csidc_client

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("")
async def list_areas(
    category: str = Query(
        None, description="Filter: industrial, old_industrial, directorate"
    ),
    db: AsyncSession = Depends(get_db),
):
    """List all available industrial areas from CSIDC."""
    try:
        areas = []

        if category is None or category == "industrial":
            industrial = await csidc_client.get_industrial_areas()
            areas.extend(industrial)

        if category is None or category == "old_industrial":
            old_industrial = await csidc_client.get_old_industrial_areas()
            areas.extend(old_industrial)

        if category is None or category == "directorate":
            directorate = await csidc_client.get_directorate_areas()
            areas.extend(directorate)

        # Cache boundaries in DB
        for area in areas:
            if area.get("geometry"):
                existing = await db.execute(
                    select(BasemapCache).where(
                        BasemapCache.area_name == area["name"],
                        BasemapCache.layer_name == area["category"],
                    )
                )
                if not existing.scalar_one_or_none():
                    cache_entry = BasemapCache(
                        layer_name=area["category"],
                        area_name=area["name"],
                        geometry_json=json.dumps(area["geometry"]),
                        properties_json=json.dumps(area.get("properties", {})),
                    )
                    db.add(cache_entry)

        # Return without heavy geometry for listing
        return {
            "areas": [
                {
                    "name": a["name"],
                    "category": a["category"],
                    "has_geometry": bool(a.get("geometry")),
                }
                for a in areas
            ],
            "total": len(areas),
        }

    except Exception as e:
        logger.error(f"Failed to fetch areas: {e}")
        raise HTTPException(
            status_code=502, detail=f"Failed to fetch from CSIDC: {str(e)}"
        )


@router.get("/cached")
async def list_cached_areas(db: AsyncSession = Depends(get_db)):
    """List areas already cached in local DB."""
    result = await db.execute(select(BasemapCache))
    entries = result.scalars().all()
    return {
        "areas": [
            {
                "id": e.id,
                "name": e.area_name,
                "category": e.layer_name,
                "fetched_at": str(e.fetched_at),
            }
            for e in entries
        ],
        "total": len(entries),
    }


@router.get("/{area_name}/boundary")
async def get_area_boundary(
    area_name: str,
    category: str = Query("industrial"),
    db: AsyncSession = Depends(get_db),
):
    """Get boundary GeoJSON for a specific area."""
    # Check cache first
    result = await db.execute(
        select(BasemapCache).where(
            BasemapCache.area_name == area_name,
            BasemapCache.layer_name == category,
        )
    )
    cached = result.scalar_one_or_none()

    if cached:
        return {
            "name": cached.area_name,
            "category": cached.layer_name,
            "geometry": cached.geometry,
            "properties": cached.properties,
        }

    # Fetch from CSIDC
    try:
        if category == "industrial":
            areas = await csidc_client.get_industrial_areas()
        elif category == "old_industrial":
            areas = await csidc_client.get_old_industrial_areas()
        elif category == "directorate":
            areas = await csidc_client.get_directorate_areas()
        else:
            raise HTTPException(status_code=400, detail=f"Unknown category: {category}")

        for area in areas:
            if area["name"] == area_name:
                # Cache it
                cache_entry = BasemapCache(
                    layer_name=category,
                    area_name=area_name,
                    geometry_json=json.dumps(area["geometry"]),
                    properties_json=json.dumps(area.get("properties", {})),
                )
                db.add(cache_entry)
                return {
                    "name": area_name,
                    "category": category,
                    "geometry": area["geometry"],
                    "properties": area.get("properties", {}),
                }

        raise HTTPException(status_code=404, detail=f"Area '{area_name}' not found")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to fetch boundary: {e}")
        raise HTTPException(status_code=502, detail=str(e))


@router.get("/wms-config")
async def get_wms_config():
    """Get WMS configuration for frontend map layers."""
    from backend.config import settings

    return {
        "wms_url": settings.CSIDC_WMS_URL,
        "workspace": settings.CSIDC_WORKSPACE,
        "layers": {
            "industrial_plots": settings.LAYER_INDUSTRIAL_PLOTS,
            "industrial_boundary": settings.LAYER_INDUSTRIAL_BOUNDARY,
            "old_industrial": settings.LAYER_OLD_INDUSTRIAL,
            "directorate": settings.LAYER_DIRECTORATE,
            "districts": settings.LAYER_DISTRICTS,
            "amenities": settings.LAYER_AMENITIES,
            "rivers": settings.LAYER_RIVERS,
            "substations": settings.LAYER_SUBSTATIONS,
        },
        "satellite_url": settings.ESRI_SATELLITE_URL,
        "map_center": [settings.MAP_CENTER_LON, settings.MAP_CENTER_LAT],
        "map_zoom": settings.MAP_DEFAULT_ZOOM,
    }


@router.get("/districts")
async def list_districts():
    """List all districts."""
    try:
        districts = await csidc_client.get_districts()
        return {"districts": districts, "total": len(districts)}
    except Exception as e:
        logger.error(f"Failed to fetch districts: {e}")
        raise HTTPException(status_code=502, detail=str(e))
