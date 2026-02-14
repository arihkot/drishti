"""Compliance orchestrator — runs all compliance checks for a project.

Coordinates green cover analysis and construction timeline checks,
matches detected plots to allotment records, and persists results
in the PlotCompliance table.
"""

import json
import logging
from datetime import datetime, timezone

import numpy as np
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import AllotmentRecord, Plot, PlotCompliance, Project
from backend.services.allotment_service import get_allotment_records
from backend.services.green_cover import compute_green_cover_pct

logger = logging.getLogger(__name__)

GREEN_COVER_THRESHOLD = 20.0  # minimum required %


def _match_plot_to_allotment(
    plot_label: str,
    allotment_records: list[AllotmentRecord],
) -> AllotmentRecord | None:
    """Best-effort match a detected plot to an allotment record by name.

    Matching strategy:
    1. Exact match on plot number extracted from label.
    2. Substring match.
    """
    # Extract number from label like "Plot 3" → "3", or "Plot (Ref: P-12)" → "P-12"
    label_lower = plot_label.lower().strip()

    # Try direct plot name match
    for rec in allotment_records:
        rec_name = (rec.plot_name or "").lower().strip()
        if not rec_name:
            continue
        if (
            rec_name == label_lower
            or rec_name in label_lower
            or label_lower in rec_name
        ):
            return rec

    # Try matching by number suffix
    # "Plot 5" → try matching a record whose plot_name contains "5"
    parts = plot_label.split()
    if len(parts) >= 2:
        num_part = parts[-1].strip("()")
        for rec in allotment_records:
            rec_name = (rec.plot_name or "").strip()
            # Match "5" to "P-5", "Plot-5", "5", etc.
            if rec_name.endswith(num_part) or rec_name == num_part:
                return rec

    return None


async def run_compliance_checks(
    db: AsyncSession,
    project_id: int,
    image: np.ndarray | None = None,
    meta: dict | None = None,
) -> dict:
    """Run all compliance checks for a project.

    Args:
        db: Database session.
        project_id: Project to check.
        image: Optional satellite image for green cover analysis.
              If None, green cover is skipped.
        meta: Tile metadata (required if image is provided).

    Returns:
        Summary dict with compliance results.
    """
    # Load project
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise ValueError(f"Project {project_id} not found")

    area_name = project.area_name

    # Load detected plots (only actual plots, not roads)
    plots_result = await db.execute(
        select(Plot).where(
            Plot.project_id == project_id,
            Plot.is_active == True,  # noqa: E712
            Plot.category == "plot",
        )
    )
    plots = plots_result.scalars().all()

    if not plots:
        logger.warning(f"No active plots found for project {project_id}")
        return {
            "project_id": project_id,
            "area_name": area_name,
            "total_plots": 0,
            "results": [],
            "summary": _empty_summary(),
        }

    # Clear existing compliance records for this project
    await db.execute(
        delete(PlotCompliance).where(PlotCompliance.project_id == project_id)
    )

    # Load allotment records (fetches from CSIDC or generates mock)
    allotment_records = []
    if area_name:
        allotment_records = await get_allotment_records(db, area_name)

    # Use naive UTC — SQLite/aiosqlite strips tzinfo on round-trip,
    # so allotment dates loaded from DB are naive.
    now = datetime.utcnow()
    compliance_results = []

    for plot in plots:
        violations = []
        geom = plot.geometry

        # ── Green cover check ──
        green_pct = None
        is_green_compliant = None

        if image is not None and meta is not None and geom:
            green_pct = compute_green_cover_pct(geom, image, meta)
            if green_pct is not None:
                is_green_compliant = green_pct >= GREEN_COVER_THRESHOLD
                if not is_green_compliant:
                    violations.append(
                        f"Green cover {green_pct:.1f}% is below "
                        f"minimum {GREEN_COVER_THRESHOLD}%"
                    )

        # ── Construction timeline check ──
        allotment_date = None
        construction_deadline = None
        construction_started = None
        is_construction_compliant = None
        data_source = "mock"
        matched_plot_name = None

        allotment_rec = _match_plot_to_allotment(plot.label, allotment_records)
        if allotment_rec:
            matched_plot_name = allotment_rec.plot_name
            allotment_date = allotment_rec.allotment_date
            construction_deadline = allotment_rec.construction_deadline
            data_source = allotment_rec.data_source

            # Determine construction status from allotment record
            status_lower = (allotment_rec.status or "").lower()
            construction_keywords = [
                "operational",
                "constructed",
                "construction in progress",
                "running",
                "production",
                "under development",
            ]
            no_construction_keywords = [
                "no construction",
                "not started",
                "vacant",
                "show cause",
                "cancelled",
            ]
            for kw in no_construction_keywords:
                if kw in status_lower:
                    construction_started = False
                    break
            else:
                for kw in construction_keywords:
                    if kw in status_lower:
                        construction_started = True
                        break

            # Check compliance
            if construction_deadline:
                if construction_deadline < now and not construction_started:
                    is_construction_compliant = False
                    days_overdue = (now - construction_deadline).days
                    violations.append(
                        f"Construction not started; {days_overdue} days past "
                        f"2-year deadline (allotted {allotment_date.strftime('%d %b %Y') if allotment_date else 'N/A'})"
                    )
                elif construction_started:
                    is_construction_compliant = True
                elif construction_deadline >= now:
                    is_construction_compliant = True  # still within deadline

        # ── Overall compliance ──
        checks = [is_green_compliant, is_construction_compliant]
        evaluated_checks = [c for c in checks if c is not None]

        if evaluated_checks:
            is_compliant = all(evaluated_checks)
        else:
            is_compliant = None  # no checks could be performed

        # ── Save to DB ──
        compliance = PlotCompliance(
            project_id=project_id,
            plot_id=plot.id,
            area_name=area_name,
            plot_name=matched_plot_name or plot.label,
            green_cover_pct=green_pct,
            green_cover_threshold=GREEN_COVER_THRESHOLD,
            is_green_compliant=is_green_compliant,
            allotment_date=allotment_date,
            construction_deadline=construction_deadline,
            construction_started=construction_started,
            is_construction_compliant=is_construction_compliant,
            is_compliant=is_compliant,
            violations_json=json.dumps(violations) if violations else None,
            data_source=data_source,
        )
        db.add(compliance)

        compliance_results.append(
            {
                "plot_id": plot.id,
                "label": plot.label,
                "matched_allotment_plot": matched_plot_name,
                "green_cover_pct": green_pct,
                "is_green_compliant": is_green_compliant,
                "allotment_date": allotment_date.isoformat()
                if allotment_date
                else None,
                "construction_deadline": (
                    construction_deadline.isoformat() if construction_deadline else None
                ),
                "construction_started": construction_started,
                "is_construction_compliant": is_construction_compliant,
                "is_compliant": is_compliant,
                "violations": violations,
                "data_source": data_source,
            }
        )

    await db.flush()

    # ── Build summary ──
    total = len(compliance_results)
    green_checked = [
        r for r in compliance_results if r["is_green_compliant"] is not None
    ]
    construction_checked = [
        r for r in compliance_results if r["is_construction_compliant"] is not None
    ]

    summary = {
        "total_plots": total,
        "green_cover": {
            "checked": len(green_checked),
            "compliant": sum(1 for r in green_checked if r["is_green_compliant"]),
            "non_compliant": sum(
                1 for r in green_checked if not r["is_green_compliant"]
            ),
            "threshold_pct": GREEN_COVER_THRESHOLD,
        },
        "construction_timeline": {
            "checked": len(construction_checked),
            "compliant": sum(
                1 for r in construction_checked if r["is_construction_compliant"]
            ),
            "non_compliant": sum(
                1 for r in construction_checked if not r["is_construction_compliant"]
            ),
            "deadline_years": 2,
        },
        "overall": {
            "fully_compliant": sum(
                1 for r in compliance_results if r["is_compliant"] is True
            ),
            "non_compliant": sum(
                1 for r in compliance_results if r["is_compliant"] is False
            ),
            "unchecked": sum(
                1 for r in compliance_results if r["is_compliant"] is None
            ),
        },
        "data_sources": {
            "csidc": sum(1 for r in compliance_results if r["data_source"] == "csidc"),
            "mock": sum(1 for r in compliance_results if r["data_source"] == "mock"),
        },
    }

    logger.info(
        f"Compliance check for project {project_id}: "
        f"{summary['overall']['fully_compliant']}/{total} compliant, "
        f"{summary['overall']['non_compliant']}/{total} non-compliant"
    )

    return {
        "project_id": project_id,
        "area_name": area_name,
        "total_plots": total,
        "results": compliance_results,
        "summary": summary,
    }


async def get_compliance_results(
    db: AsyncSession,
    project_id: int,
) -> dict | None:
    """Retrieve previously computed compliance results from the DB.

    Returns None if no compliance data exists for this project.
    """
    result = await db.execute(
        select(PlotCompliance).where(PlotCompliance.project_id == project_id)
    )
    records = result.scalars().all()

    if not records:
        return None

    # Load project for area_name
    proj_result = await db.execute(select(Project).where(Project.id == project_id))
    project = proj_result.scalar_one_or_none()

    compliance_results = []
    for rec in records:
        compliance_results.append(
            {
                "plot_id": rec.plot_id,
                "label": rec.plot_name,
                "matched_allotment_plot": rec.plot_name,
                "green_cover_pct": rec.green_cover_pct,
                "is_green_compliant": rec.is_green_compliant,
                "allotment_date": rec.allotment_date.isoformat()
                if rec.allotment_date
                else None,
                "construction_deadline": (
                    rec.construction_deadline.isoformat()
                    if rec.construction_deadline
                    else None
                ),
                "construction_started": rec.construction_started,
                "is_construction_compliant": rec.is_construction_compliant,
                "is_compliant": rec.is_compliant,
                "violations": rec.violations,
                "data_source": rec.data_source,
            }
        )

    total = len(compliance_results)
    green_checked = [
        r for r in compliance_results if r["is_green_compliant"] is not None
    ]
    construction_checked = [
        r for r in compliance_results if r["is_construction_compliant"] is not None
    ]

    summary = {
        "total_plots": total,
        "green_cover": {
            "checked": len(green_checked),
            "compliant": sum(1 for r in green_checked if r["is_green_compliant"]),
            "non_compliant": sum(
                1 for r in green_checked if not r["is_green_compliant"]
            ),
            "threshold_pct": GREEN_COVER_THRESHOLD,
        },
        "construction_timeline": {
            "checked": len(construction_checked),
            "compliant": sum(
                1 for r in construction_checked if r["is_construction_compliant"]
            ),
            "non_compliant": sum(
                1 for r in construction_checked if not r["is_construction_compliant"]
            ),
            "deadline_years": 2,
        },
        "overall": {
            "fully_compliant": sum(
                1 for r in compliance_results if r["is_compliant"] is True
            ),
            "non_compliant": sum(
                1 for r in compliance_results if r["is_compliant"] is False
            ),
            "unchecked": sum(
                1 for r in compliance_results if r["is_compliant"] is None
            ),
        },
        "data_sources": {
            "csidc": sum(1 for r in compliance_results if r["data_source"] == "csidc"),
            "mock": sum(1 for r in compliance_results if r["data_source"] == "mock"),
        },
    }

    return {
        "project_id": project_id,
        "area_name": project.area_name if project else None,
        "total_plots": total,
        "results": compliance_results,
        "summary": summary,
    }


def _empty_summary() -> dict:
    return {
        "total_plots": 0,
        "green_cover": {
            "checked": 0,
            "compliant": 0,
            "non_compliant": 0,
            "threshold_pct": GREEN_COVER_THRESHOLD,
        },
        "construction_timeline": {
            "checked": 0,
            "compliant": 0,
            "non_compliant": 0,
            "deadline_years": 2,
        },
        "overall": {"fully_compliant": 0, "non_compliant": 0, "unchecked": 0},
        "data_sources": {"csidc": 0, "mock": 0},
    }
