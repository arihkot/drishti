"""Comparison router - deviation detection endpoints."""

import json
import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.database import get_db
from backend.models import BasemapCache, Comparison, Plot, Project

logger = logging.getLogger(__name__)
router = APIRouter()


class CompareRequest(BaseModel):
    tolerance_m: float = 2.0


@router.post("/{project_id}")
async def compare_project(
    project_id: int,
    data: CompareRequest,
    db: AsyncSession = Depends(get_db),
):
    """Compare detected boundaries with basemap for a project."""
    from backend.services.comparator import compare_project_with_basemap

    # Get project with plots
    result = await db.execute(
        select(Project)
        .where(Project.id == project_id)
        .options(selectinload(Project.plots))
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    active_plots = [p for p in project.plots if p.is_active]
    if not active_plots:
        raise HTTPException(status_code=400, detail="No active plots in project")

    # Get basemap features for comparison
    # Prefer individual plot features over outer boundary for better accuracy
    basemap_features = []
    use_individual_plots = False

    if project.area_name:
        # First, try to fetch individual plot features from CSIDC
        try:
            from backend.services.csidc_client import csidc_client

            # Get boundary geometry for spatial fallback
            boundary_geom = None
            bm_result = await db.execute(
                select(BasemapCache).where(
                    BasemapCache.area_name == project.area_name,
                )
            )
            bm_entry = bm_result.scalars().first()
            if bm_entry and bm_entry.geometry:
                boundary_geom = bm_entry.geometry

            plots_data = await csidc_client.get_individual_plots(
                project.area_name, boundary_geometry=boundary_geom
            )
            if plots_data:
                for plot in plots_data:
                    basemap_features.append(
                        {
                            "name": plot["name"],
                            "geometry": plot["geometry"],
                            "properties": plot.get("properties", {}),
                        }
                    )
                use_individual_plots = True
                logger.info(
                    f"Using {len(basemap_features)} individual plot features for comparison"
                )
        except Exception as e:
            logger.warning(f"Failed to fetch individual plots: {e}")

        # Fall back to cached basemap or outer boundary
        if not basemap_features:
            bm_result = await db.execute(
                select(BasemapCache).where(BasemapCache.area_name == project.area_name)
            )
            basemap_entries = bm_result.scalars().all()
            for entry in basemap_entries:
                basemap_features.append(
                    {
                        "id": entry.id,
                        "name": entry.area_name,
                        "geometry": entry.geometry,
                        "properties": entry.properties,
                    }
                )

    if not basemap_features:
        # Try to ensure areas are cached locally, then read from DB
        try:
            from backend.routers.areas import _ensure_areas_cached

            category = project.area_category or "industrial"
            await _ensure_areas_cached(db, category)

            bm_result = await db.execute(
                select(BasemapCache).where(
                    BasemapCache.area_name == project.area_name,
                    BasemapCache.layer_name == category,
                )
            )
            bm_entry = bm_result.scalar_one_or_none()
            if bm_entry:
                basemap_features.append(
                    {
                        "name": bm_entry.area_name,
                        "geometry": bm_entry.geometry,
                        "properties": bm_entry.properties,
                    }
                )
        except Exception as e:
            logger.warning(f"Failed to fetch basemap: {e}")

    if not basemap_features:
        raise HTTPException(
            status_code=400,
            detail="No basemap boundary found for comparison. Ensure the area name matches a CSIDC industrial area.",
        )

    # Prepare plot data for comparison
    detected_plots = [
        {
            "id": p.id,
            "label": p.label,
            "geometry": p.geometry,
            "area_sqm": p.area_sqm,
        }
        for p in active_plots
    ]

    # Run comparison
    comparison_result = compare_project_with_basemap(
        detected_plots, basemap_features, tolerance_m=data.tolerance_m
    )

    # Save comparison results to DB
    # Clear old comparisons for this project
    old_comparisons = await db.execute(
        select(Comparison).where(Comparison.project_id == project_id)
    )
    for old in old_comparisons.scalars().all():
        await db.delete(old)

    # Save new comparisons
    for dev in comparison_result["deviations"]:
        comparison = Comparison(
            project_id=project_id,
            plot_id=dev.get("plot_id"),
            deviation_type=dev["deviation_type"],
            severity=dev["severity"],
            deviation_area_sqm=dev.get("deviation_area_sqm", 0),
            deviation_geometry_json=json.dumps(dev.get("deviation_geometry"))
            if dev.get("deviation_geometry")
            else None,
            details_json=json.dumps(dev.get("details", {})),
            description=dev.get("description", ""),
        )
        db.add(comparison)

    return comparison_result


@router.get("/{project_id}")
async def get_comparison_results(project_id: int, db: AsyncSession = Depends(get_db)):
    """Get existing comparison results for a project."""
    result = await db.execute(
        select(Comparison).where(Comparison.project_id == project_id)
    )
    comparisons = result.scalars().all()

    if not comparisons:
        raise HTTPException(
            status_code=404, detail="No comparison results found. Run comparison first."
        )

    deviations = []
    summary = {
        "total": len(comparisons),
        "total_detected": len(comparisons),
        "total_basemap": 0,
        "compliant": 0,
        "encroachment": 0,
        "boundary_mismatch": 0,
        "vacant": 0,
        "unauthorized": 0,
        "unmatched_detected": 0,
        "unmatched_basemap": 0,
    }

    for c in comparisons:
        dev_type = c.deviation_type
        if dev_type == "COMPLIANT":
            summary["compliant"] += 1
        elif dev_type == "ENCROACHMENT":
            summary["encroachment"] += 1
        elif dev_type == "BOUNDARY_MISMATCH":
            summary["boundary_mismatch"] += 1
        elif dev_type == "VACANT":
            summary["vacant"] += 1
        elif dev_type == "UNAUTHORIZED_DEVELOPMENT":
            summary["unauthorized"] += 1

        deviations.append(
            {
                "id": c.id,
                "plot_id": c.plot_id,
                "deviation_type": c.deviation_type,
                "severity": c.severity,
                "deviation_area_sqm": c.deviation_area_sqm,
                "deviation_geometry": c.deviation_geometry,
                "details": c.details,
                "description": c.description,
                "created_at": str(c.created_at),
            }
        )

    return {"summary": summary, "deviations": deviations}
