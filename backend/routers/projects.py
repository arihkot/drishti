"""Projects router - CRUD for project management."""

import json
import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.database import get_db
from backend.models import Plot, Project

logger = logging.getLogger(__name__)
router = APIRouter()


class ProjectCreate(BaseModel):
    name: str
    area_name: str | None = None
    area_category: str | None = None
    description: str | None = None
    bbox: list[float] | None = None
    center_lon: float | None = None
    center_lat: float | None = None
    zoom: int = 18


class ProjectUpdate(BaseModel):
    name: str | None = None
    description: str | None = None


class PlotUpdate(BaseModel):
    label: str | None = None
    category: str | None = None
    color: str | None = None


@router.get("")
async def list_projects(db: AsyncSession = Depends(get_db)):
    """List all projects."""
    result = await db.execute(select(Project).order_by(Project.updated_at.desc()))
    projects = result.scalars().all()
    return {
        "projects": [
            {
                "id": p.id,
                "name": p.name,
                "area_name": p.area_name,
                "area_category": p.area_category,
                "description": p.description,
                "bbox": p.bbox,
                "center_lon": p.center_lon,
                "center_lat": p.center_lat,
                "zoom": p.zoom,
                "created_at": str(p.created_at),
                "updated_at": str(p.updated_at),
            }
            for p in projects
        ],
    }


@router.post("")
async def create_project(data: ProjectCreate, db: AsyncSession = Depends(get_db)):
    """Create a new project."""
    project = Project(
        name=data.name,
        area_name=data.area_name,
        area_category=data.area_category,
        description=data.description,
        bbox_json=json.dumps(data.bbox) if data.bbox else None,
        center_lon=data.center_lon,
        center_lat=data.center_lat,
        zoom=data.zoom,
    )
    db.add(project)
    await db.flush()
    await db.refresh(project)
    return {"id": project.id, "name": project.name}


@router.get("/{project_id}")
async def get_project(project_id: int, db: AsyncSession = Depends(get_db)):
    """Get project with all plots."""
    result = await db.execute(
        select(Project)
        .where(Project.id == project_id)
        .options(selectinload(Project.plots))
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    return {
        "id": project.id,
        "name": project.name,
        "area_name": project.area_name,
        "area_category": project.area_category,
        "description": project.description,
        "bbox": project.bbox,
        "center_lon": project.center_lon,
        "center_lat": project.center_lat,
        "zoom": project.zoom,
        "created_at": str(project.created_at),
        "updated_at": str(project.updated_at),
        "plots": [
            {
                "id": p.id,
                "label": p.label,
                "category": p.category,
                "geometry": p.geometry,
                "area_sqm": p.area_sqm,
                "area_sqft": p.area_sqft,
                "perimeter_m": p.perimeter_m,
                "color": p.color,
                "confidence": p.confidence,
                "is_active": p.is_active,
                "properties": p.properties,
                "created_at": str(p.created_at),
            }
            for p in project.plots
            if p.is_active
        ],
    }


@router.put("/{project_id}")
async def update_project(
    project_id: int, data: ProjectUpdate, db: AsyncSession = Depends(get_db)
):
    """Update project details."""
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if data.name is not None:
        project.name = data.name
    if data.description is not None:
        project.description = data.description

    return {"id": project.id, "name": project.name}


@router.delete("/{project_id}")
async def delete_project(project_id: int, db: AsyncSession = Depends(get_db)):
    """Delete a project and all its plots."""
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    await db.delete(project)
    return {"deleted": True}


@router.put("/{project_id}/plots/{plot_id}")
async def update_plot(
    project_id: int,
    plot_id: int,
    data: PlotUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update a plot (rename, change category/color)."""
    result = await db.execute(
        select(Plot).where(Plot.id == plot_id, Plot.project_id == project_id)
    )
    plot = result.scalar_one_or_none()
    if not plot:
        raise HTTPException(status_code=404, detail="Plot not found")

    if data.label is not None:
        plot.label = data.label
    if data.category is not None:
        plot.category = data.category
    if data.color is not None:
        plot.color = data.color

    return {
        "id": plot.id,
        "label": plot.label,
        "category": plot.category,
        "color": plot.color,
    }


@router.delete("/{project_id}/plots/{plot_id}")
async def delete_plot(
    project_id: int, plot_id: int, db: AsyncSession = Depends(get_db)
):
    """Soft-delete a plot."""
    result = await db.execute(
        select(Plot).where(Plot.id == plot_id, Plot.project_id == project_id)
    )
    plot = result.scalar_one_or_none()
    if not plot:
        raise HTTPException(status_code=404, detail="Plot not found")

    plot.is_active = False
    return {"deleted": True, "id": plot_id}
