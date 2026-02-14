"""Compliance router — endpoints for running and retrieving compliance checks."""

import json
import logging

import numpy as np
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.models import Project

logger = logging.getLogger(__name__)
router = APIRouter()


class ComplianceRunRequest(BaseModel):
    """Request body for running compliance checks."""

    include_green_cover: bool = True
    include_construction_timeline: bool = True


@router.post("/{project_id}")
async def run_compliance(
    project_id: int,
    data: ComplianceRunRequest = ComplianceRunRequest(),
    db: AsyncSession = Depends(get_db),
):
    """Run compliance checks for a project.

    Performs:
    - Green cover analysis (requires cached satellite imagery)
    - Construction timeline compliance (uses allotment records)

    Results are persisted in the database.
    """
    try:
        from backend.services.compliance import run_compliance_checks
        from backend.services.tile_fetcher import bbox_hash
        from backend.config import settings

        # Verify project exists
        result = await db.execute(select(Project).where(Project.id == project_id))
        project = result.scalar_one_or_none()
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        # Try to load cached satellite image for green cover analysis
        image = None
        meta = None

        if data.include_green_cover and project.bbox:
            bbox = project.bbox
            zoom = project.zoom or settings.DEFAULT_TILE_ZOOM
            cache_key = bbox_hash(bbox, zoom)
            cache_path = settings.TILES_DIR / f"{cache_key}.npy"
            meta_path = settings.TILES_DIR / f"{cache_key}_meta.npy"

            if cache_path.exists() and meta_path.exists():
                image = np.load(str(cache_path))
                meta = np.load(str(meta_path), allow_pickle=True).item()
                logger.info(f"Loaded cached satellite image for green cover analysis")
            else:
                logger.warning(
                    f"No cached satellite image for project {project_id}. "
                    f"Run detection first. Skipping green cover analysis."
                )

        results = await run_compliance_checks(
            db=db,
            project_id=project_id,
            image=image,
            meta=meta,
        )

        return results

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Compliance check failed: {e}")
        raise HTTPException(
            status_code=500, detail=f"Compliance check failed: {str(e)}"
        )


@router.get("/{project_id}")
async def get_compliance(
    project_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Retrieve previously computed compliance results for a project."""
    try:
        from backend.services.compliance import get_compliance_results

        # Verify project exists
        result = await db.execute(select(Project).where(Project.id == project_id))
        project = result.scalar_one_or_none()
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        results = await get_compliance_results(db, project_id)
        if results is None:
            raise HTTPException(
                status_code=404,
                detail="No compliance data found. Run compliance checks first.",
            )

        return results

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to retrieve compliance data: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{project_id}/summary")
async def get_compliance_summary(
    project_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Get a compact compliance summary for dashboard display."""
    try:
        from backend.services.compliance import get_compliance_results

        results = await get_compliance_results(db, project_id)
        if results is None:
            return {
                "project_id": project_id,
                "has_data": False,
                "summary": None,
            }

        return {
            "project_id": project_id,
            "has_data": True,
            "summary": results["summary"],
        }

    except Exception as e:
        logger.exception(f"Failed to get compliance summary: {e}")
        raise HTTPException(status_code=500, detail=str(e))
