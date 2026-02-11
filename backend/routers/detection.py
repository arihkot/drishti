"""Detection router - SAM boundary detection endpoints."""

import json
import logging
import time

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.models import Plot, Project

logger = logging.getLogger(__name__)
router = APIRouter()


class AutoDetectRequest(BaseModel):
    bbox: list[float]  # [minLon, minLat, maxLon, maxLat]
    zoom: int = 18
    project_id: int | None = None
    project_name: str | None = None
    area_name: str | None = None
    area_category: str | None = None
    min_area_sqm: float = 10.0


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
        from backend.services.sam_detector import detect_boundaries_auto
        from backend.services.vectorizer import (
            process_masks_to_plots,
            merge_overlapping_polygons,
            clip_to_boundary,
        )

        t_start = time.time()

        # 1. Fetch satellite imagery
        logger.info(f"Fetching satellite imagery for bbox: {data.bbox}")
        image, meta = await fetch_satellite_image(data.bbox, data.zoom)
        t_fetch = time.time()
        logger.info(
            f"[TIMING] Tile fetch: {t_fetch - t_start:.2f}s | Image: {image.shape}"
        )

        # 2. Run SAM detection
        logger.info("Running SAM auto-detection...")
        raw_masks = await detect_boundaries_auto(image, meta)
        t_sam = time.time()
        logger.info(
            f"[TIMING] SAM detection: {t_sam - t_fetch:.2f}s | Raw masks: {len(raw_masks)}"
        )

        # 3. Process masks into plots
        plots_data = process_masks_to_plots(raw_masks, min_area_sqm=data.min_area_sqm)
        t_process = time.time()
        logger.info(
            f"[TIMING] Vectorization: {t_process - t_sam:.2f}s | Plots: {len(plots_data)}"
        )

        # 4. Merge overlapping
        plots_data = merge_overlapping_polygons(plots_data)
        t_merge = time.time()
        logger.info(
            f"[TIMING] Merge: {t_merge - t_process:.2f}s | After merge: {len(plots_data)}"
        )

        # 4b. Clip to area boundary if area_name provided
        if data.area_name:
            try:
                from backend.models import BasemapCache

                t_clip_start = time.time()
                category = data.area_category or "industrial"
                boundary_geom = None

                # Check local DB cache first
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
                    # Fall back to CSIDC API and cache the result
                    from backend.services.csidc_client import csidc_client

                    if category == "industrial":
                        all_areas = await csidc_client.get_industrial_areas()
                    elif category == "old_industrial":
                        all_areas = await csidc_client.get_old_industrial_areas()
                    elif category == "directorate":
                        all_areas = await csidc_client.get_directorate_areas()
                    else:
                        all_areas = []

                    for area in all_areas:
                        if area["name"] == data.area_name and area.get("geometry"):
                            boundary_geom = area["geometry"]
                            # Cache for future use
                            cache_entry = BasemapCache(
                                layer_name=category,
                                area_name=data.area_name,
                                geometry_json=json.dumps(boundary_geom),
                                properties_json=json.dumps(area.get("properties", {})),
                            )
                            db.add(cache_entry)
                            logger.info(
                                f"Fetched & cached boundary for {data.area_name}"
                            )
                            break

                if boundary_geom:
                    plots_data = clip_to_boundary(plots_data, boundary_geom)
                    logger.info(
                        f"[TIMING] Boundary clip: {time.time() - t_clip_start:.2f}s | "
                        f"Clipped to {data.area_name}: {len(plots_data)} plots"
                    )
            except Exception as e:
                logger.warning(f"Boundary clip failed, keeping all plots: {e}")

        # 5. Create or get project
        if data.project_id:
            result = await db.execute(
                select(Project).where(Project.id == data.project_id)
            )
            project = result.scalar_one_or_none()
            if not project:
                raise HTTPException(status_code=404, detail="Project not found")
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

        # 6. Save plots to DB
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

        # Process masks
        plots_data = process_masks_to_plots(raw_masks)

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
