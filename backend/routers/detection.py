"""Detection router - SAM boundary detection endpoints."""

import json
import logging
import time

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.models import Plot, Project, CsidcReferencePlot

logger = logging.getLogger(__name__)
router = APIRouter()


class AutoDetectRequest(BaseModel):
    bbox: list[float]  # [minLon, minLat, maxLon, maxLat]
    zoom: int = 18
    project_id: int | None = None
    project_name: str | None = None
    area_name: str | None = None
    area_category: str | None = None
    min_area_sqm: float = 50.0


class PromptDetectRequest(BaseModel):
    bbox: list[float]
    zoom: int = 18
    project_id: int
    points: list[dict] | None = None  # [{"lon": ..., "lat": ..., "label": 1}]
    boxes: list[list[float]] | None = None  # [[minLon, minLat, maxLon, maxLat], ...]


@router.post("/auto")
async def auto_detect(data: AutoDetectRequest, db: AsyncSession = Depends(get_db)):
    """
    Run automatic boundary detection on a satellite image region.

    Creates or uses an existing project and saves detected plots.
    """
    try:
        from backend.services.tile_fetcher import fetch_satellite_image
        from backend.services.sam_detector import (
            detect_boundaries_auto,
            detect_boundaries_csidc_guided,
        )
        from backend.services.vectorizer import (
            process_masks_to_plots,
            merge_overlapping_polygons,
            remove_contained_polygons,
            clip_to_boundary,
            renumber_labels,
        )

        t_start = time.time()

        # ── PHASE 0: Import CSIDC reference data BEFORE detection ──
        # Fetch boundary + reference plots first so we can use them
        # to guide SAM and fill in any plots SAM misses.
        boundary_geom = None
        csidc_plots: list[dict] = []

        if data.area_name:
            # 0a. Fetch area boundary (from local DB, or fetch+cache from CSIDC)
            try:
                from backend.models import BasemapCache
                from backend.routers.areas import _ensure_areas_cached

                category = data.area_category or "industrial"

                cached = await db.execute(
                    select(BasemapCache).where(
                        BasemapCache.area_name == data.area_name,
                        BasemapCache.layer_name == category,
                    )
                )
                cached_entry = cached.scalar_one_or_none()

                if cached_entry and cached_entry.geometry:
                    boundary_geom = cached_entry.geometry
                    logger.info(f"Using cached boundary for {data.area_name}")
                else:
                    # Fetch all areas for this category and cache them
                    all_cached = await _ensure_areas_cached(db, category)
                    for entry in all_cached:
                        if entry.area_name == data.area_name and entry.geometry:
                            boundary_geom = entry.geometry
                            logger.info(
                                f"Fetched & cached boundary for {data.area_name}"
                            )
                            break
            except Exception as e:
                logger.warning(f"Failed to fetch area boundary: {e}")

            # 0b. Fetch CSIDC reference plots (from cache or API)
            try:
                from backend.services.csidc_client import csidc_client
                from backend.models import CsidcReferencePlot

                cached_ref = await db.execute(
                    select(CsidcReferencePlot).where(
                        CsidcReferencePlot.area_name == data.area_name,
                    )
                )
                cached_ref_plots = cached_ref.scalars().all()

                if cached_ref_plots:
                    csidc_plots = [
                        {"geometry": p.geometry, "name": p.plot_name}
                        for p in cached_ref_plots
                    ]
                    logger.info(
                        f"Loaded {len(csidc_plots)} cached CSIDC ref plots BEFORE detection"
                    )
                else:
                    csidc_plots_raw = await csidc_client.get_individual_plots(
                        data.area_name,
                        boundary_geometry=boundary_geom,
                    )
                    csidc_plots = csidc_plots_raw

                    for plot in csidc_plots_raw:
                        entry = CsidcReferencePlot(
                            area_name=data.area_name,
                            plot_name=plot.get("name"),
                            geometry_json=json.dumps(plot["geometry"]),
                            properties_json=json.dumps(plot.get("properties", {})),
                        )
                        db.add(entry)
                    if csidc_plots_raw:
                        await db.flush()
                    logger.info(
                        f"Fetched & cached {len(csidc_plots)} CSIDC ref plots BEFORE detection"
                    )
            except Exception as e:
                logger.warning(f"Failed to fetch CSIDC reference plots: {e}")

        t_preload = time.time()
        logger.info(
            f"[TIMING] CSIDC preload: {t_preload - t_start:.2f}s | "
            f"boundary={'yes' if boundary_geom else 'no'}, ref_plots={len(csidc_plots)}"
        )

        # ── PHASE 1: Fetch satellite imagery ──
        logger.info(f"Fetching satellite imagery for bbox: {data.bbox}")
        image, meta = await fetch_satellite_image(data.bbox, data.zoom)
        t_fetch = time.time()
        logger.info(
            f"[TIMING] Tile fetch: {t_fetch - t_preload:.2f}s | Image: {image.shape}"
        )

        # ── PHASE 2: Run SAM auto-detection ──
        logger.info("Running SAM auto-detection...")
        raw_masks = await detect_boundaries_auto(image, meta)
        t_sam = time.time()
        logger.info(
            f"[TIMING] SAM detection: {t_sam - t_fetch:.2f}s | Raw masks: {len(raw_masks)}"
        )

        # ── PHASE 2b: CSIDC-guided detection for missed plots ──
        csidc_guided_count = 0
        if csidc_plots:
            try:
                t_csidc_start = time.time()
                extra_masks = await detect_boundaries_csidc_guided(
                    image, meta, raw_masks, csidc_plots
                )
                csidc_guided_count = len(extra_masks)
                raw_masks.extend(extra_masks)
                logger.info(
                    f"[TIMING] CSIDC-guided pass: {time.time() - t_csidc_start:.2f}s | "
                    f"Extra masks: {csidc_guided_count}"
                )
            except Exception as e:
                logger.warning(
                    f"CSIDC-guided detection failed, continuing with auto only: {e}"
                )

        # ── PHASE 3: Process masks into plots ──
        plots_data = process_masks_to_plots(
            raw_masks, min_area_sqm=data.min_area_sqm, image=image, meta=meta
        )
        t_process = time.time()
        logger.info(
            f"[TIMING] Vectorization: {t_process - t_sam:.2f}s | Plots: {len(plots_data)}"
        )

        # ── PHASE 3b: Inject CSIDC reference plots that SAM missed entirely ──
        # After processing masks, check which CSIDC plots are still undetected
        # and inject their geometries directly as detected plots.
        if csidc_plots:
            try:
                from backend.services.vectorizer import inject_missing_csidc_plots

                injected_count_before = len(plots_data)
                plots_data = inject_missing_csidc_plots(
                    plots_data, csidc_plots, image=image, meta=meta
                )
                injected = len(plots_data) - injected_count_before
                logger.info(
                    f"Injected {injected} CSIDC reference plots that SAM missed entirely"
                )
            except Exception as e:
                logger.warning(f"CSIDC injection failed: {e}")

        # ── PHASE 4: Post-processing ──
        # 4a. Merge overlapping polygons
        plots_data = merge_overlapping_polygons(plots_data)
        t_merge = time.time()
        logger.info(
            f"[TIMING] Merge: {t_merge - t_process:.2f}s | After merge: {len(plots_data)}"
        )

        # 4b. Merge small nearby polygons that should be one plot
        from backend.services.vectorizer import merge_small_nearby_polygons

        plots_data = merge_small_nearby_polygons(plots_data)
        logger.info(f"After small-nearby merge: {len(plots_data)} plots")

        # 4c. Area-based noise filter: drop tiny road fragments that are
        # almost always SAM noise (shadows, road markings, tiny slivers).
        # Plots are kept regardless of size (MIN_POLYGON_AREA_SQM handles that).
        NOISE_AREA_THRESHOLD_SQM = 100.0
        before_noise = len(plots_data)
        plots_data = [
            p
            for p in plots_data
            if not (
                p.get("category") == "road"
                and p.get("area_sqm", 0) < NOISE_AREA_THRESHOLD_SQM
            )
        ]
        noise_dropped = before_noise - len(plots_data)
        if noise_dropped:
            logger.info(
                f"Noise filter: dropped {noise_dropped} tiny features "
                f"(<{NOISE_AREA_THRESHOLD_SQM} sqm), {len(plots_data)} remaining"
            )

        # 4d. Remove smaller polygons contained inside larger ones
        plots_data = remove_contained_polygons(plots_data)

        # 4e. Clip to area boundary
        if boundary_geom:
            try:
                t_clip_start = time.time()
                plots_data = clip_to_boundary(plots_data, boundary_geom)
                logger.info(
                    f"[TIMING] Boundary clip: {time.time() - t_clip_start:.2f}s | "
                    f"Clipped to {data.area_name}: {len(plots_data)} plots"
                )
            except Exception as e:
                logger.warning(f"Boundary clip failed, keeping all plots: {e}")

        # 5. Re-number labels sequentially (merge/clip may have removed some)
        plots_data = renumber_labels(plots_data)

        # 6. Create or get project
        if data.project_id:
            result = await db.execute(
                select(Project).where(Project.id == data.project_id)
            )
            project = result.scalar_one_or_none()
            if not project:
                raise HTTPException(status_code=404, detail="Project not found")

            # Clear existing plots before saving new detection results
            from sqlalchemy import delete

            await db.execute(delete(Plot).where(Plot.project_id == project.id))
            logger.info(f"Cleared existing plots for project {project.id}")

            # Update project bbox/zoom in case they changed
            project.bbox_json = json.dumps(data.bbox)
            project.center_lon = (data.bbox[0] + data.bbox[2]) / 2
            project.center_lat = (data.bbox[1] + data.bbox[3]) / 2
            project.zoom = data.zoom
        else:
            project = Project(
                name=data.project_name or f"Detection {data.bbox}",
                area_name=data.area_name,
                area_category=data.area_category,
                bbox_json=json.dumps(data.bbox),
                center_lon=(data.bbox[0] + data.bbox[2]) / 2,
                center_lat=(data.bbox[1] + data.bbox[3]) / 2,
                zoom=data.zoom,
            )
            db.add(project)
            await db.flush()
            await db.refresh(project)

        # 7. Save plots to DB
        saved_plots = []
        for plot_data in plots_data:
            plot = Plot(
                project_id=project.id,
                label=plot_data["label"],
                category=plot_data["category"],
                geometry_json=json.dumps(plot_data["geometry"]),
                area_sqm=plot_data["area_sqm"],
                area_sqft=plot_data["area_sqft"],
                perimeter_m=plot_data["perimeter_m"],
                color=plot_data["color"],
                confidence=plot_data.get("confidence"),
            )
            db.add(plot)
            await db.flush()
            await db.refresh(plot)

            saved_plots.append(
                {
                    "id": plot.id,
                    "label": plot.label,
                    "category": plot.category,
                    "geometry": plot_data["geometry"],
                    "area_sqm": plot.area_sqm,
                    "area_sqft": plot.area_sqft,
                    "perimeter_m": plot.perimeter_m,
                    "color": plot.color,
                    "centroid": plot_data.get("centroid"),
                }
            )

        t_total = time.time() - t_start
        logger.info(
            f"[TIMING] Total pipeline: {t_total:.2f}s | "
            f"{len(saved_plots)} plots saved to project {project.id}"
        )

        return {
            "project_id": project.id,
            "project_name": project.name,
            "plots": saved_plots,
            "total": len(saved_plots),
            "image_size": list(image.shape[:2]),
            "meta": {
                "bbox": meta["bbox"],
                "zoom": meta["zoom"],
                "tiles": f"{meta['tiles_x']}x{meta['tiles_y']}",
                "csidc_guided_extra": csidc_guided_count,
            },
            "timing_seconds": round(time.time() - t_start, 2),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Detection failed: {e}")
        raise HTTPException(status_code=500, detail=f"Detection failed: {str(e)}")


@router.post("/prompt")
async def prompt_detect(data: PromptDetectRequest, db: AsyncSession = Depends(get_db)):
    """
    Run prompted boundary detection using point/box prompts.
    """
    try:
        from backend.services.tile_fetcher import fetch_satellite_image
        from backend.services.sam_detector import detect_boundaries_prompted
        from backend.services.vectorizer import process_masks_to_plots

        # Verify project exists
        result = await db.execute(select(Project).where(Project.id == data.project_id))
        project = result.scalar_one_or_none()
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        # Fetch satellite imagery
        image, meta = await fetch_satellite_image(data.bbox, data.zoom)

        # Prepare prompts
        point_coords = None
        point_labels = None
        box_coords = None

        if data.points:
            point_coords = [[p["lon"], p["lat"]] for p in data.points]
            point_labels = [p.get("label", 1) for p in data.points]

        if data.boxes:
            box_coords = data.boxes

        # Run prompted detection
        raw_masks = await detect_boundaries_prompted(
            image,
            meta,
            point_coords=point_coords,
            point_labels=point_labels,
            box_coords=box_coords,
        )

        # Process masks (pass satellite image for color-based classification)
        plots_data = process_masks_to_plots(raw_masks, image=image, meta=meta)

        # Get existing plot count for numbering
        existing_result = await db.execute(
            select(Plot).where(
                Plot.project_id == data.project_id, Plot.is_active == True
            )
        )
        existing_count = len(existing_result.scalars().all())

        # Save new plots
        saved_plots = []
        for i, plot_data in enumerate(plots_data):
            num = existing_count + i + 1
            label = f"{plot_data['category'].capitalize()} {num}"

            plot = Plot(
                project_id=project.id,
                label=label,
                category=plot_data["category"],
                geometry_json=json.dumps(plot_data["geometry"]),
                area_sqm=plot_data["area_sqm"],
                area_sqft=plot_data["area_sqft"],
                perimeter_m=plot_data["perimeter_m"],
                color=plot_data["color"],
                confidence=plot_data.get("confidence"),
            )
            db.add(plot)
            await db.flush()
            await db.refresh(plot)

            saved_plots.append(
                {
                    "id": plot.id,
                    "label": label,
                    "category": plot.category,
                    "geometry": plot_data["geometry"],
                    "area_sqm": plot.area_sqm,
                    "area_sqft": plot.area_sqft,
                    "color": plot.color,
                    "centroid": plot_data.get("centroid"),
                }
            )

        return {
            "project_id": project.id,
            "new_plots": saved_plots,
            "total_new": len(saved_plots),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Prompted detection failed: {e}")
        raise HTTPException(status_code=500, detail=f"Detection failed: {str(e)}")


@router.get("/model-status")
async def model_status():
    """Check if SAM model is loaded."""
    from backend.services.sam_detector import _sam_model

    from backend.config import settings

    return {
        "loaded": _sam_model is not None,
        "model_type": f"SAM ({settings.SAM_MODEL_TYPE})",
        "device": settings.SAM_DEVICE,
    }


@router.post("/preload-model")
async def preload_model():
    """Pre-load the SAM model into memory."""
    try:
        from backend.services.sam_detector import get_sam_model

        model = get_sam_model()
        from backend.config import settings

        return {"status": "loaded", "model_type": f"SAM ({settings.SAM_MODEL_TYPE})"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load model: {str(e)}")


@router.post("/reload-model")
async def reload_model():
    """Force reload SAM model (use after changing parameters)."""
    try:
        from backend.services.sam_detector import reload_models, get_sam_model

        reload_models()
        model = get_sam_model()
        from backend.config import settings

        return {
            "status": "reloaded",
            "model_type": f"SAM ({settings.SAM_MODEL_TYPE})",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to reload model: {str(e)}")
