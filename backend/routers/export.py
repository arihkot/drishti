"""Export router - PDF report generation."""

import json
import logging

import numpy as np
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.config import settings
from backend.database import get_db
from backend.models import BasemapCache, Comparison, CsidcReferencePlot, Plot, Project
from backend.services.tile_fetcher import bbox_hash

logger = logging.getLogger(__name__)
router = APIRouter()


class ExportRequest(BaseModel):
    include_satellite: bool = True
    include_schematic: bool = True
    include_deviations: bool = True


@router.post("/{project_id}/pdf")
async def export_pdf(
    project_id: int,
    data: ExportRequest = ExportRequest(),
    db: AsyncSession = Depends(get_db),
):
    """Generate and download PDF report for a project."""
    from backend.services.pdf_generator import generate_pdf_report

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

    plots_data = [
        {
            "label": p.label,
            "category": p.category,
            "geometry": p.geometry,
            "area_sqm": p.area_sqm,
            "area_sqft": p.area_sqft,
            "perimeter_m": p.perimeter_m,
            "color": p.color,
        }
        for p in active_plots
    ]

    # Get basemap features
    basemap_features = []
    if project.area_name:
        bm_result = await db.execute(
            select(BasemapCache).where(BasemapCache.area_name == project.area_name)
        )
        for entry in bm_result.scalars().all():
            basemap_features.append(
                {
                    "geometry": entry.geometry,
                    "properties": entry.properties,
                }
            )

    # Get comparison results
    deviations = []
    comparison_summary = None
    if data.include_deviations:
        comp_result = await db.execute(
            select(Comparison).where(Comparison.project_id == project_id)
        )
        comparisons = comp_result.scalars().all()
        if comparisons:
            comparison_summary = {
                "total_detected": len(active_plots),
                "compliant": sum(
                    1 for c in comparisons if c.deviation_type == "COMPLIANT"
                ),
                "encroachment": sum(
                    1 for c in comparisons if c.deviation_type == "ENCROACHMENT"
                ),
                "boundary_mismatch": sum(
                    1 for c in comparisons if c.deviation_type == "BOUNDARY_MISMATCH"
                ),
                "vacant": sum(1 for c in comparisons if c.deviation_type == "VACANT"),
                "unauthorized": sum(
                    1
                    for c in comparisons
                    if c.deviation_type == "UNAUTHORIZED_DEVELOPMENT"
                ),
            }
            deviations = [
                {
                    "plot_label": f"Plot {c.plot_id}",
                    "deviation_type": c.deviation_type,
                    "severity": c.severity,
                    "deviation_area_sqm": c.deviation_area_sqm,
                    "deviation_geometry": c.deviation_geometry,
                    "details": c.details,
                    "description": c.description,
                }
                for c in comparisons
            ]

    # Load cached satellite image for the project's bbox/zoom
    satellite_image = None
    satellite_meta = None
    if project.bbox_json:
        try:
            bbox = json.loads(project.bbox_json)
            zoom = project.zoom or settings.DEFAULT_TILE_ZOOM
            cache_key = bbox_hash(bbox, zoom)
            cache_path = settings.TILES_DIR / f"{cache_key}.npy"
            meta_path = settings.TILES_DIR / f"{cache_key}_meta.npy"
            if cache_path.exists() and meta_path.exists():
                satellite_image = np.load(str(cache_path))
                satellite_meta = np.load(str(meta_path), allow_pickle=True).item()
                logger.info(f"Loaded cached satellite image: {cache_key}")
            else:
                logger.warning(f"Satellite cache not found for key {cache_key}")
        except Exception as e:
            logger.warning(f"Failed to load satellite image cache: {e}")

    # Extract boundary geometry from basemap features
    boundary_geom = None
    if basemap_features:
        boundary_geom = basemap_features[0].get("geometry")

    # Load CSIDC reference plots for the area
    csidc_ref_plots = []
    if project.area_name:
        ref_result = await db.execute(
            select(CsidcReferencePlot).where(
                CsidcReferencePlot.area_name == project.area_name
            )
        )
        for ref in ref_result.scalars().all():
            csidc_ref_plots.append(
                {
                    "geometry": ref.geometry,
                    "plot_name": ref.plot_name,
                    "properties": ref.properties,
                }
            )
        logger.info(
            f"Loaded {len(csidc_ref_plots)} CSIDC reference plots for {project.area_name}"
        )

    # Generate PDF
    try:
        pdf_path = generate_pdf_report(
            project_name=project.name,
            area_name=project.area_name or "N/A",
            plots=plots_data,
            basemap_features=basemap_features if basemap_features else None,
            deviations=deviations if deviations else None,
            comparison_summary=comparison_summary,
            satellite_image=satellite_image,
            satellite_meta=satellite_meta,
            boundary_geom=boundary_geom,
            csidc_ref_plots=csidc_ref_plots if csidc_ref_plots else None,
        )

        return FileResponse(
            str(pdf_path),
            media_type="application/pdf",
            filename=pdf_path.name,
        )
    except Exception as e:
        logger.exception(f"PDF generation failed: {e}")
        raise HTTPException(status_code=500, detail=f"PDF generation failed: {str(e)}")


@router.post("/{project_id}/geojson")
async def export_geojson(project_id: int, db: AsyncSession = Depends(get_db)):
    """Export detected boundaries as GeoJSON."""
    result = await db.execute(
        select(Project)
        .where(Project.id == project_id)
        .options(selectinload(Project.plots))
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    features = []
    for plot in project.plots:
        if not plot.is_active:
            continue
        features.append(
            {
                "type": "Feature",
                "geometry": plot.geometry,
                "properties": {
                    "id": plot.id,
                    "label": plot.label,
                    "category": plot.category,
                    "area_sqm": plot.area_sqm,
                    "area_sqft": plot.area_sqft,
                    "perimeter_m": plot.perimeter_m,
                    "color": plot.color,
                },
            }
        )

    return {
        "type": "FeatureCollection",
        "features": features,
        "properties": {
            "project_name": project.name,
            "area_name": project.area_name,
        },
    }
