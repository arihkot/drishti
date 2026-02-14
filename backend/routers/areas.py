"""Areas router - CSIDC area listing and basemap proxy."""

import hashlib
import json
import logging

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import settings
from backend.database import get_db
from backend.models import BasemapCache, CsidcReferencePlot, WmsTileCache
from backend.services.csidc_client import csidc_client

logger = logging.getLogger(__name__)
router = APIRouter()


async def _ensure_areas_cached(
    db: AsyncSession,
    category: str | None = None,
    force_refresh: bool = False,
) -> list[BasemapCache]:
    """Ensure area boundaries are stored in the local DB.

    On the very first call (or when ``force_refresh=True``), fetches all
    areas from CSIDC and bulk-inserts them into ``basemap_cache``. Every
    subsequent call just reads from the DB — no network requests.

    Returns the list of ``BasemapCache`` rows matching *category* (or all
    categories if *category* is ``None``).
    """
    categories_to_check = (
        [category] if category else ["industrial", "old_industrial", "directorate"]
    )

    # Check which categories still need fetching
    categories_to_fetch: list[str] = []
    for cat in categories_to_check:
        if force_refresh:
            categories_to_fetch.append(cat)
            continue
        result = await db.execute(
            select(BasemapCache).where(BasemapCache.layer_name == cat).limit(1)
        )
        if not result.scalar_one_or_none():
            categories_to_fetch.append(cat)

    # Fetch missing categories from CSIDC and store
    if categories_to_fetch:
        for cat in categories_to_fetch:
            try:
                if cat == "industrial":
                    areas = await csidc_client.get_industrial_areas()
                elif cat == "old_industrial":
                    areas = await csidc_client.get_old_industrial_areas()
                elif cat == "directorate":
                    areas = await csidc_client.get_directorate_areas()
                else:
                    continue

                if force_refresh:
                    # Delete old entries for this category before re-inserting
                    from sqlalchemy import delete

                    await db.execute(
                        delete(BasemapCache).where(BasemapCache.layer_name == cat)
                    )

                for area in areas:
                    if not area.get("geometry"):
                        continue
                    cache_entry = BasemapCache(
                        layer_name=cat,
                        area_name=area["name"],
                        geometry_json=json.dumps(area["geometry"]),
                        properties_json=json.dumps(area.get("properties", {})),
                    )
                    db.add(cache_entry)

                await db.flush()
                logger.info(
                    f"Cached {len(areas)} areas for category '{cat}' from CSIDC"
                )
            except Exception as e:
                logger.error(f"Failed to fetch {cat} areas from CSIDC: {e}")

    # Return cached entries
    query = select(BasemapCache)
    if category:
        query = query.where(BasemapCache.layer_name == category)
    result = await db.execute(query)
    return list(result.scalars().all())


@router.get("")
async def list_areas(
    category: str = Query(
        None, description="Filter: industrial, old_industrial, directorate"
    ),
    refresh: bool = Query(False, description="Force re-fetch from CSIDC"),
    db: AsyncSession = Depends(get_db),
):
    """List all available industrial areas.

    Serves from local DB cache. On first call, fetches from CSIDC and
    stores locally. Pass ``?refresh=true`` to force a re-fetch.
    """
    try:
        cached_areas = await _ensure_areas_cached(db, category, force_refresh=refresh)

        return {
            "areas": [
                {
                    "name": e.area_name,
                    "category": e.layer_name,
                    "has_geometry": True,
                }
                for e in cached_areas
            ],
            "total": len(cached_areas),
            "source": "cache",
        }

    except Exception as e:
        logger.error(f"Failed to list areas: {e}")
        raise HTTPException(status_code=502, detail=f"Failed to fetch areas: {str(e)}")


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
    """Get boundary GeoJSON for a specific area.

    Checks local cache first. On miss, fetches ALL areas for that
    category from CSIDC (so future boundary lookups are instant too).
    """
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

    # Cache miss — fetch the entire category so all areas are cached at once
    try:
        all_cached = await _ensure_areas_cached(db, category)

        # Find the requested area in the freshly-cached list
        for entry in all_cached:
            if entry.area_name == area_name:
                return {
                    "name": entry.area_name,
                    "category": entry.layer_name,
                    "geometry": entry.geometry,
                    "properties": entry.properties,
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


@router.get("/{area_name}/reference-plots")
async def get_reference_plots(
    area_name: str,
    db: AsyncSession = Depends(get_db),
):
    """Get cached CSIDC reference plots for an area.

    Fetches from CSIDC once, caches in local DB, serves from cache thereafter.
    """
    # Check cache first
    result = await db.execute(
        select(CsidcReferencePlot).where(
            CsidcReferencePlot.area_name == area_name,
        )
    )
    cached = result.scalars().all()

    if cached:
        logger.info(f"Serving {len(cached)} cached reference plots for {area_name}")
        return {
            "area_name": area_name,
            "plots": [
                {
                    "id": p.id,
                    "name": p.plot_name,
                    "geometry": p.geometry,
                    "properties": p.properties,
                }
                for p in cached
            ],
            "total": len(cached),
            "source": "cache",
        }

    # Fetch from CSIDC and cache
    try:
        # Get the boundary geometry for spatial fallback
        boundary_geom = None
        bm_result = await db.execute(
            select(BasemapCache).where(
                BasemapCache.area_name == area_name,
            )
        )
        bm_entry = bm_result.scalars().first()
        if bm_entry and bm_entry.geometry:
            boundary_geom = bm_entry.geometry

        plots = await csidc_client.get_individual_plots(
            area_name, boundary_geometry=boundary_geom
        )

        if not plots:
            return {
                "area_name": area_name,
                "plots": [],
                "total": 0,
                "source": "csidc",
            }

        for plot in plots:
            entry = CsidcReferencePlot(
                area_name=area_name,
                plot_name=plot.get("name"),
                geometry_json=json.dumps(plot["geometry"]),
                properties_json=json.dumps(plot.get("properties", {})),
            )
            db.add(entry)

        await db.flush()
        logger.info(f"Fetched & cached {len(plots)} reference plots for {area_name}")

        return {
            "area_name": area_name,
            "plots": [
                {
                    "name": p.get("name"),
                    "geometry": p["geometry"],
                    "properties": p.get("properties", {}),
                }
                for p in plots
            ],
            "total": len(plots),
            "source": "csidc",
        }

    except Exception as e:
        logger.error(f"Failed to fetch reference plots for {area_name}: {e}")
        raise HTTPException(
            status_code=502,
            detail=f"Failed to fetch reference plots from CSIDC: {str(e)}",
        )


@router.get("/wms-proxy")
async def wms_proxy(request: Request, db: AsyncSession = Depends(get_db)):
    """Proxy WMS requests to CSIDC GeoServer with local DB tile caching.

    Forwards all query params to the CSIDC WMS endpoint, adds auth token,
    and returns the response (typically a PNG image). This solves CORS/auth
    issues when the browser tries to load WMS tiles directly.

    Tiles are cached in SQLite by a SHA-256 hash of the canonical query params
    so subsequent identical requests are served from local DB instantly.
    """
    params = dict(request.query_params)
    if not params:
        raise HTTPException(status_code=400, detail="No WMS params provided")

    # Build a deterministic cache key from sorted query params
    canonical = "&".join(f"{k}={v}" for k, v in sorted(params.items()))
    cache_key = hashlib.sha256(canonical.encode()).hexdigest()

    # Check DB cache first
    result = await db.execute(
        select(WmsTileCache).where(WmsTileCache.cache_key == cache_key)
    )
    cached = result.scalar_one_or_none()

    if cached:
        return Response(
            content=cached.tile_data,
            media_type=cached.content_type,
            headers={
                "Cache-Control": "public, max-age=86400",
                "Access-Control-Allow-Origin": "*",
                "X-Cache": "HIT",
            },
        )

    # Cache miss — fetch from CSIDC
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(30.0, connect=10.0), verify=False
        ) as client:
            resp = await client.get(
                settings.CSIDC_WMS_URL,
                params=params,
                headers={"Authorization": settings.CSIDC_AUTH_TOKEN},
            )
            resp.raise_for_status()

            content_type = resp.headers.get("content-type", "image/png")
            tile_data = resp.content

            # Store in DB cache
            entry = WmsTileCache(
                cache_key=cache_key,
                content_type=content_type,
                tile_data=tile_data,
            )
            db.add(entry)
            # Flush so it's persisted (session auto-commits via middleware)
            await db.flush()

            logger.info(
                f"WMS tile cached: {cache_key[:12]}... ({len(tile_data)} bytes)"
            )

            return Response(
                content=tile_data,
                media_type=content_type,
                headers={
                    "Cache-Control": "public, max-age=86400",
                    "Access-Control-Allow-Origin": "*",
                    "X-Cache": "MISS",
                },
            )
    except httpx.HTTPStatusError as e:
        logger.error(f"WMS proxy error: {e.response.status_code}")
        raise HTTPException(
            status_code=e.response.status_code, detail="WMS request failed"
        )
    except Exception as e:
        logger.error(f"WMS proxy error: {e}")
        raise HTTPException(status_code=502, detail=f"WMS proxy failed: {str(e)}")


@router.get("/{area_name}/reference-plots/geojson")
async def get_reference_plots_geojson(
    area_name: str,
    category: str = Query("industrial"),
    db: AsyncSession = Depends(get_db),
):
    """Get CSIDC reference plots as a GeoJSON FeatureCollection.

    Optimized for direct use by the frontend map vector layer.
    Fetches from CSIDC on first call, caches in local DB, serves from cache
    thereafter -- so hover/tooltip is instant without hitting the remote server.
    """
    # Check cache first
    result = await db.execute(
        select(CsidcReferencePlot).where(
            CsidcReferencePlot.area_name == area_name,
        )
    )
    cached = list(result.scalars().all())

    if not cached:
        # Fetch from CSIDC and cache
        try:
            # Get the boundary geometry for spatial fallback
            boundary_geom = None
            bm_result = await db.execute(
                select(BasemapCache).where(
                    BasemapCache.area_name == area_name,
                )
            )
            bm_entry = bm_result.scalars().first()
            if bm_entry and bm_entry.geometry:
                boundary_geom = bm_entry.geometry

            plots = await csidc_client.get_individual_plots(
                area_name, boundary_geometry=boundary_geom
            )

            if plots:
                for plot in plots:
                    entry = CsidcReferencePlot(
                        area_name=area_name,
                        plot_name=plot.get("name"),
                        geometry_json=json.dumps(plot["geometry"]),
                        properties_json=json.dumps(plot.get("properties", {})),
                    )
                    db.add(entry)
                await db.flush()
                logger.info(
                    f"Fetched & cached {len(plots)} reference plots for {area_name}"
                )

            # Re-read from DB to get IDs
            result = await db.execute(
                select(CsidcReferencePlot).where(
                    CsidcReferencePlot.area_name == area_name,
                )
            )
            cached = list(result.scalars().all())
        except Exception as e:
            logger.error(f"Failed to fetch reference plots for {area_name}: {e}")
            raise HTTPException(
                status_code=502,
                detail=f"Failed to fetch reference plots from CSIDC: {str(e)}",
            )

    # Build GeoJSON FeatureCollection
    features = []
    for p in cached:
        geom = p.geometry
        props = p.properties or {}
        if not geom:
            continue
        # Extract useful display properties
        plot_name = (
            p.plot_name
            or props.get("plotno_inf")
            or props.get("PLOT_NO")
            or props.get("plot_no")
            or props.get("plot_name")
            or props.get("kh_no")
            or f"Plot-{p.id}"
        )
        allottee = (
            props.get("allottee")
            or props.get("ALLOTTEE")
            or props.get("allottee_name")
            or props.get("allottee_n")
            or props.get("firm_name")
            or props.get("FIRM_NAME")
            or props.get("allotmentr")
            or ""
        )
        area_val = (
            props.get("total_area")
            or props.get("area_sqm")
            or props.get("AREA_SQM")
            or props.get("shape_area")
            or props.get("Shape_Area")
            or props.get("SHAPE_AREA")
            or props.get("st_area_sh")
            or None
        )
        status = (
            props.get("status_inf")
            or props.get("status_from_csidc")
            or props.get("status")
            or props.get("STATUS")
            or props.get("allot_status")
            or props.get("category_i")
            or ""
        )
        plot_type = props.get("plot_type") or props.get("PLOT_TYPE") or ""
        location = props.get("location") or props.get("LOCATION") or ""
        district = (
            props.get("district")
            or props.get("DISTRICT")
            or props.get("district_i")
            or ""
        )
        allotment_date = props.get("allotment_date") or ""
        features.append(
            {
                "type": "Feature",
                "id": f"csidc-{p.id}",
                "geometry": geom,
                "properties": {
                    "ref_id": p.id,
                    "name": str(plot_name),
                    "allottee": str(allottee),
                    "area_sqm": float(area_val) if area_val else None,
                    "status": _normalize_status(str(status)),
                    "plot_type": str(plot_type),
                    "location": str(location),
                    "district": str(district),
                    "allotment_date": str(allotment_date),
                    "source": "csidc_reference",
                },
            }
        )

    return {
        "type": "FeatureCollection",
        "features": features,
        "properties": {
            "area_name": area_name,
            "total": len(features),
            "source": "cache" if cached else "csidc",
        },
    }


def _normalize_status(raw: str) -> str:
    """Map raw CSIDC status values to canonical display labels."""
    low = raw.strip().lower()
    if not low:
        return "AVAILABLE"
    if low.startswith("allot") or low in ("occupied", "leased"):
        return "ALLOTTED"
    if low in ("unallotted", "vacant", "available", "open", "free"):
        return "AVAILABLE"
    if low in ("cancelled", "canceled", "cancelled - returned"):
        return "CANCELLED"
    if low in ("disputed", "dispute"):
        return "DISPUTED"
    if low in ("under_review", "under review", "review"):
        return "UNDER REVIEW"
    # Fallback: uppercase whatever came in
    return raw.upper()


class UpdateReferencePlotRequest(BaseModel):
    """Request body for updating a CSIDC reference plot's properties."""

    allottee: str | None = None
    status: str | None = None
    allotment_date: str | None = None  # ISO format date string


@router.put("/reference-plots/{plot_id}")
async def update_reference_plot(
    plot_id: int,
    body: UpdateReferencePlotRequest,
    db: AsyncSession = Depends(get_db),
):
    """Update editable properties of a CSIDC reference plot.

    Persists changes to the cached properties_json so they survive
    across sessions.
    """
    result = await db.execute(
        select(CsidcReferencePlot).where(CsidcReferencePlot.id == plot_id)
    )
    plot = result.scalar_one_or_none()
    if not plot:
        raise HTTPException(status_code=404, detail="Reference plot not found")

    # Parse existing properties
    props = json.loads(plot.properties_json) if plot.properties_json else {}

    # Update only the fields that were provided
    if body.allottee is not None:
        props["allottee"] = body.allottee
    if body.status is not None:
        props["status"] = body.status
        props["status_inf"] = body.status
    if body.allotment_date is not None:
        props["allotment_date"] = body.allotment_date

    plot.properties_json = json.dumps(props)
    await db.flush()

    logger.info(f"Updated reference plot {plot_id} properties")

    # Return the updated properties in the same format as the GeoJSON endpoint
    plot_name = (
        plot.plot_name
        or props.get("plotno_inf")
        or props.get("PLOT_NO")
        or props.get("plot_no")
        or props.get("plot_name")
        or props.get("kh_no")
        or f"Plot-{plot.id}"
    )
    allottee = (
        props.get("allottee")
        or props.get("ALLOTTEE")
        or props.get("allottee_name")
        or props.get("allottee_n")
        or props.get("firm_name")
        or props.get("FIRM_NAME")
        or props.get("allotmentr")
        or ""
    )
    status = (
        props.get("status_inf")
        or props.get("status_from_csidc")
        or props.get("status")
        or props.get("STATUS")
        or props.get("allot_status")
        or props.get("category_i")
        or ""
    )

    return {
        "ref_id": plot.id,
        "name": str(plot_name),
        "allottee": str(allottee),
        "status": _normalize_status(str(status)),
        "allotment_date": props.get("allotment_date"),
        "area_name": plot.area_name,
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
