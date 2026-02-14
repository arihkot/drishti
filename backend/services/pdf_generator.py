"""PDF report generator — CSIDC-branded, professional layout."""

import io
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch, mm
from reportlab.platypus import (
    Image as RLImage,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
    KeepTogether,
)
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from shapely.geometry import shape

from backend.config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# CSIDC Brand Colors
# ---------------------------------------------------------------------------
CSIDC_BLUE = "#0D47A1"
CSIDC_BLUE_LIGHT = "#1976D2"
CSIDC_DARK = "#1B2631"
CSIDC_GRAY = "#5D6D7E"
CSIDC_BG = "#E3F2FD"

# Category styling — matches frontend 3-category system (plot, road, boundary)
CATEGORY_STYLES: dict[str, dict[str, str]] = {
    "plot": {"fill": "rgba(239,68,68,0.20)", "stroke": "#ef4444", "label": "Plot"},
    "road": {"fill": "rgba(100,116,139,0.15)", "stroke": "#64748b", "label": "Road"},
    "boundary": {
        "fill": "rgba(249,115,22,0.10)",
        "stroke": "#f97316",
        "label": "Boundary",
    },
    # Legacy
    "parcel": {"fill": "rgba(239,68,68,0.20)", "stroke": "#ef4444", "label": "Parcel"},
}

# CSIDC reference plot status styling — matches frontend MapView.tsx
CSIDC_REF_STATUS_COLORS: dict[str, dict[str, str]] = {
    "ALLOTTED": {"fill": "#dc2626", "stroke": "#dc2626", "label": "Allotted"},
    "AVAILABLE": {"fill": "#22c55e", "stroke": "#16a34a", "label": "Available"},
    "CANCELLED": {"fill": "#9ca3af", "stroke": "#9ca3af", "label": "Cancelled"},
    "DISPUTED": {"fill": "#f97316", "stroke": "#f97316", "label": "Disputed"},
    "UNDER REVIEW": {"fill": "#eab308", "stroke": "#eab308", "label": "Under Review"},
}
CSIDC_REF_DEFAULT_COLOR = {"fill": "#22c55e", "stroke": "#16a34a", "label": "Available"}
CSIDC_REF_FILL_ALPHA = 0.30


def _get_csidc_ref_style(status: str) -> dict[str, str]:
    """Get color style for a CSIDC reference plot based on its status."""
    return CSIDC_REF_STATUS_COLORS.get(
        (status or "").strip().upper(), CSIDC_REF_DEFAULT_COLOR
    )


DEVIATION_COLORS: dict[str, str] = {
    "ENCROACHMENT": "#ef4444",
    "BOUNDARY_MISMATCH": "#f97316",
    "VACANT": "#eab308",
    "UNAUTHORIZED_DEVELOPMENT": "#dc2626",
    "COMPLIANT": "#22c55e",
}

SEVERITY_BG: dict[str, str] = {
    "low": "#dcfce7",
    "medium": "#fef9c3",
    "high": "#ffedd5",
    "critical": "#fee2e2",
}


def _hex_to_rgba(hex_color: str, alpha: float = 1.0) -> tuple[float, ...]:
    """Convert hex color to matplotlib RGBA tuple (0-1 range)."""
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16) / 255, int(h[2:4], 16) / 255, int(h[4:6], 16) / 255
    return (r, g, b, alpha)


def _parse_rgba_string(s: str) -> tuple[float, ...]:
    """Parse 'rgba(r,g,b,a)' string to matplotlib tuple."""
    inner = s.replace("rgba(", "").replace(")", "")
    parts = [float(x.strip()) for x in inner.split(",")]
    return (parts[0] / 255, parts[1] / 255, parts[2] / 255, parts[3])


def _draw_geometry(
    ax, geom, fill_color, stroke_color, stroke_width=1.5, zorder=3, hatch=None
):
    """Draw a shapely geometry (Polygon or MultiPolygon) on a matplotlib axis."""
    if geom.geom_type == "Polygon":
        if hasattr(geom, "exterior"):
            x, y = geom.exterior.xy
            ax.fill(
                x,
                y,
                alpha=fill_color[3] if len(fill_color) > 3 else 0.2,
                color=fill_color[:3],
                hatch=hatch,
                zorder=zorder - 1,
            )
            ax.plot(x, y, color=stroke_color, linewidth=stroke_width, zorder=zorder)
    elif geom.geom_type == "MultiPolygon":
        for poly in geom.geoms:
            _draw_geometry(
                ax, poly, fill_color, stroke_color, stroke_width, zorder, hatch
            )


# ---------------------------------------------------------------------------
# Page header/footer template
# ---------------------------------------------------------------------------
def _page_template(canvas, doc):
    """Draw CSIDC-branded header and footer on every page."""
    canvas.saveState()
    page_width, page_height = landscape(A4)

    # --- Header bar ---
    # Orange gradient bar at top
    canvas.setFillColor(colors.HexColor(CSIDC_BLUE))
    canvas.rect(0, page_height - 28, page_width, 28, fill=1, stroke=0)

    # Header text
    canvas.setFillColor(colors.white)
    canvas.setFont("Helvetica-Bold", 9)
    canvas.drawString(
        20,
        page_height - 20,
        "CHHATTISGARH STATE INDUSTRIAL DEVELOPMENT CORPORATION (CSIDC)",
    )
    canvas.setFont("Helvetica", 8)
    canvas.drawRightString(
        page_width - 20, page_height - 20, "Drishti — Automated Land Monitoring System"
    )

    # Thin accent line below header
    canvas.setStrokeColor(colors.HexColor(CSIDC_BLUE_LIGHT))
    canvas.setLineWidth(1.5)
    canvas.line(0, page_height - 30, page_width, page_height - 30)

    # --- Footer ---
    canvas.setStrokeColor(colors.HexColor(CSIDC_GRAY))
    canvas.setLineWidth(0.5)
    canvas.line(20, 25, page_width - 20, 25)

    canvas.setFillColor(colors.HexColor(CSIDC_GRAY))
    canvas.setFont("Helvetica", 7)
    canvas.drawString(20, 13, "CONFIDENTIAL — For CSIDC Internal Use Only")
    canvas.drawCentredString(
        page_width / 2,
        13,
        f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
    )
    canvas.drawRightString(page_width - 20, 13, f"Page {canvas.getPageNumber()}")

    canvas.restoreState()


# ---------------------------------------------------------------------------
# Schematic Map Renderer
# ---------------------------------------------------------------------------
def _render_schematic(
    plots: list[dict],
    basemap_features: list[dict] | None = None,
    deviations: list[dict] | None = None,
    title: str = "Land Parcel Schematic",
    figsize: tuple[float, float] = (16, 10),
) -> bytes:
    """Render a professional schematic of all plots as PNG bytes."""
    fig, ax = plt.subplots(1, 1, figsize=figsize, dpi=150)
    ax.set_facecolor("#fafafa")
    fig.patch.set_facecolor("white")

    # Draw basemap boundaries if available
    if basemap_features:
        for feature in basemap_features:
            try:
                geom = shape(feature.get("geometry", feature))
                _draw_geometry(
                    ax,
                    geom,
                    fill_color=(0, 0.8, 0.85, 0.06),
                    stroke_color="#00897B",
                    stroke_width=2.5,
                    zorder=2,
                )
            except Exception:
                continue

    # Draw detected plots with category-specific styling
    for i, plot in enumerate(plots):
        try:
            geom = shape(plot["geometry"])
            category = plot.get("category", "plot")
            style = CATEGORY_STYLES.get(category, CATEGORY_STYLES["plot"])
            fill_rgba = _parse_rgba_string(style["fill"])
            stroke_hex = style["stroke"]

            hatch = "///" if category in ("plot", "parcel") else None
            _draw_geometry(
                ax, geom, fill_rgba, stroke_hex, stroke_width=1.5, zorder=3, hatch=hatch
            )

            # Label at centroid
            label = plot.get("label", f"Plot {i + 1}")
            cx, cy = geom.centroid.x, geom.centroid.y
            ax.annotate(
                label,
                (cx, cy),
                fontsize=5,
                ha="center",
                va="center",
                fontweight="bold",
                color="#333333",
                bbox=dict(
                    boxstyle="round,pad=0.15",
                    facecolor="white",
                    edgecolor=stroke_hex,
                    alpha=0.92,
                    linewidth=0.6,
                ),
                zorder=5,
            )
        except Exception:
            continue

    # Draw deviations
    if deviations:
        for dev in deviations:
            if dev.get("deviation_geometry"):
                try:
                    geom = shape(dev["deviation_geometry"])
                    dev_type = dev.get("deviation_type", "")
                    dev_color = DEVIATION_COLORS.get(dev_type, "#9ca3af")
                    dev_rgba = _hex_to_rgba(dev_color, 0.35)
                    _draw_geometry(
                        ax, geom, dev_rgba, dev_color, stroke_width=2, zorder=4
                    )
                except Exception:
                    continue

    ax.set_title(
        title,
        fontsize=13,
        fontweight="bold",
        pad=12,
        color=CSIDC_DARK,
        fontfamily="sans-serif",
    )
    ax.set_xlabel("Longitude", fontsize=9, color=CSIDC_GRAY)
    ax.set_ylabel("Latitude", fontsize=9, color=CSIDC_GRAY)
    ax.set_aspect("equal")
    ax.grid(True, alpha=0.15, linestyle="--", color="#aaa")
    ax.tick_params(labelsize=7, colors=CSIDC_GRAY)

    # Legend with all categories present in data
    seen_categories = set()
    for p in plots:
        seen_categories.add(p.get("category", "plot"))

    legend_elements = []
    for cat_key in ["plot", "road", "boundary"]:
        if cat_key in seen_categories:
            st = CATEGORY_STYLES[cat_key]
            fill_rgba = _parse_rgba_string(st["fill"])
            legend_elements.append(
                mpatches.Patch(
                    facecolor=fill_rgba[:3] + (fill_rgba[3],),
                    edgecolor=st["stroke"],
                    label=st["label"],
                    linewidth=1.2,
                )
            )
    if basemap_features:
        legend_elements.append(
            mpatches.Patch(
                facecolor=(0, 0.8, 0.85, 0.06),
                edgecolor="#00897B",
                label="CSIDC Boundary",
                linewidth=1.2,
            )
        )
    if deviations:
        for dev_type, dev_color in DEVIATION_COLORS.items():
            if any(d.get("deviation_type") == dev_type for d in deviations):
                legend_elements.append(
                    mpatches.Patch(
                        facecolor=_hex_to_rgba(dev_color, 0.35),
                        edgecolor=dev_color,
                        label=dev_type.replace("_", " ").title(),
                        linewidth=1.2,
                    )
                )

    if legend_elements:
        leg = ax.legend(
            handles=legend_elements,
            loc="upper right",
            fontsize=7,
            framealpha=0.92,
            edgecolor="#ddd",
            fancybox=True,
        )
        leg.get_frame().set_linewidth(0.5)

    plt.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight", dpi=150)
    plt.close(fig)
    buf.seek(0)
    return buf.read()


# ---------------------------------------------------------------------------
# CSIDC Reference Schematic Renderer
# ---------------------------------------------------------------------------
def _render_csidc_ref_schematic(
    csidc_ref_plots: list[dict],
    boundary_geom: dict | None = None,
    title: str = "CSIDC Reference Plots — Schematic",
    figsize: tuple[float, float] = (16, 10),
) -> bytes:
    """Render a CAD-style schematic of CSIDC reference plots as PNG bytes."""
    fig, ax = plt.subplots(1, 1, figsize=figsize, dpi=150)
    ax.set_facecolor("#fafafa")
    fig.patch.set_facecolor("white")

    # Draw outer boundary
    if boundary_geom:
        try:
            geom = shape(boundary_geom)
            _draw_geometry(
                ax,
                geom,
                fill_color=(0.05, 0.28, 0.63, 0.04),
                stroke_color="#1976D2",
                stroke_width=2.5,
                zorder=2,
            )
        except Exception:
            pass

    # Draw CSIDC reference plots with status-based colors
    seen_statuses: set[str] = set()
    for i, ref in enumerate(csidc_ref_plots):
        try:
            geom = shape(ref["geometry"])
            status = (ref.get("status") or "").strip().upper()
            style = _get_csidc_ref_style(status)
            fill_color = _hex_to_rgba(style["fill"], CSIDC_REF_FILL_ALPHA)
            stroke_color = style["stroke"]
            seen_statuses.add(status or "AVAILABLE")
            _draw_geometry(
                ax,
                geom,
                fill_color=fill_color,
                stroke_color=stroke_color,
                stroke_width=1.5,
                zorder=3,
            )

            # Label at centroid
            label = ref.get("plot_name") or f"Ref {i + 1}"
            cx, cy = geom.centroid.x, geom.centroid.y
            ax.annotate(
                label,
                (cx, cy),
                fontsize=4.5,
                ha="center",
                va="center",
                fontweight="bold",
                color="#1B2631",
                bbox=dict(
                    boxstyle="round,pad=0.12",
                    facecolor="white",
                    edgecolor=stroke_color,
                    alpha=0.90,
                    linewidth=0.5,
                ),
                zorder=5,
            )
        except Exception:
            continue

    ax.set_title(
        title,
        fontsize=13,
        fontweight="bold",
        pad=12,
        color=CSIDC_DARK,
        fontfamily="sans-serif",
    )
    ax.set_xlabel("Longitude", fontsize=9, color=CSIDC_GRAY)
    ax.set_ylabel("Latitude", fontsize=9, color=CSIDC_GRAY)
    ax.set_aspect("equal")
    ax.grid(True, alpha=0.15, linestyle="--", color="#aaa")
    ax.tick_params(labelsize=7, colors=CSIDC_GRAY)

    # Legend — status-based entries
    legend_elements = []
    for status_key in [
        "ALLOTTED",
        "AVAILABLE",
        "CANCELLED",
        "DISPUTED",
        "UNDER REVIEW",
    ]:
        if status_key in seen_statuses:
            st = CSIDC_REF_STATUS_COLORS[status_key]
            legend_elements.append(
                mpatches.Patch(
                    facecolor=_hex_to_rgba(st["fill"], CSIDC_REF_FILL_ALPHA),
                    edgecolor=st["stroke"],
                    label=f"{st['label']} ({sum(1 for r in csidc_ref_plots if (r.get('status') or '').strip().upper() == status_key)})",
                    linewidth=1.2,
                )
            )
    if boundary_geom:
        legend_elements.append(
            mpatches.Patch(
                facecolor=(0.05, 0.28, 0.63, 0.04),
                edgecolor="#1976D2",
                label="CSIDC Outer Boundary",
                linewidth=1.2,
            )
        )
    leg = ax.legend(
        handles=legend_elements,
        loc="upper right",
        fontsize=7,
        framealpha=0.92,
        edgecolor="#ddd",
        fancybox=True,
    )
    leg.get_frame().set_linewidth(0.5)

    plt.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight", dpi=150)
    plt.close(fig)
    buf.seek(0)
    return buf.read()


# ---------------------------------------------------------------------------
# Satellite + Overlay Renderer
# ---------------------------------------------------------------------------
def _render_satellite_overlay(
    satellite_image: np.ndarray,
    meta: dict,
    plots: list[dict],
    boundary_geom: dict | None = None,
    title: str = "Satellite Imagery with Detected Boundaries",
) -> bytes:
    """Render the satellite image with plot boundaries overlaid."""
    fig, ax = plt.subplots(1, 1, figsize=(16, 10), dpi=150)
    fig.patch.set_facecolor("white")

    bbox = meta["bbox"]
    ax.imshow(
        satellite_image,
        extent=[bbox[0], bbox[2], bbox[1], bbox[3]],
        aspect="auto",
        zorder=1,
    )

    # Overlay boundary
    if boundary_geom:
        try:
            geom = shape(boundary_geom)
            _draw_geometry(
                ax,
                geom,
                fill_color=(0.05, 0.28, 0.63, 0.05),
                stroke_color="#1976D2",
                stroke_width=2.5,
                zorder=2,
            )
        except Exception:
            pass

    # Overlay plots
    for i, plot in enumerate(plots):
        try:
            geom = shape(plot["geometry"])
            color = plot.get("color", "#3b82f6")
            label = plot.get("label", f"Plot {i + 1}")

            stroke_rgba = _hex_to_rgba(color)
            _draw_geometry(
                ax,
                geom,
                fill_color=_hex_to_rgba(color, 0.25),
                stroke_color=color,
                stroke_width=1.2,
                zorder=3,
            )

            cx, cy = geom.centroid.x, geom.centroid.y
            ax.annotate(
                label,
                (cx, cy),
                fontsize=4.5,
                ha="center",
                va="center",
                fontweight="bold",
                color="white",
                bbox=dict(
                    boxstyle="round,pad=0.12", facecolor="black", alpha=0.6, linewidth=0
                ),
                zorder=5,
            )
        except Exception:
            continue

    ax.set_title(
        title,
        fontsize=13,
        fontweight="bold",
        pad=12,
        color=CSIDC_DARK,
        fontfamily="sans-serif",
    )
    ax.set_xlabel("Longitude", fontsize=9, color=CSIDC_GRAY)
    ax.set_ylabel("Latitude", fontsize=9, color=CSIDC_GRAY)
    ax.tick_params(labelsize=7, colors=CSIDC_GRAY)

    plt.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight", dpi=150)
    plt.close(fig)
    buf.seek(0)
    return buf.read()


# ---------------------------------------------------------------------------
# CSIDC Reference Overlay Renderer
# ---------------------------------------------------------------------------
def _render_csidc_ref_overlay(
    satellite_image: np.ndarray,
    meta: dict,
    csidc_ref_plots: list[dict],
    boundary_geom: dict | None = None,
    title: str = "CSIDC Reference Plots — Satellite Overlay",
) -> bytes:
    """Render the satellite image with CSIDC reference plot boundaries overlaid."""
    fig, ax = plt.subplots(1, 1, figsize=(16, 10), dpi=150)
    fig.patch.set_facecolor("white")

    bbox = meta["bbox"]
    ax.imshow(
        satellite_image,
        extent=[bbox[0], bbox[2], bbox[1], bbox[3]],
        aspect="auto",
        zorder=1,
    )

    # Draw outer boundary
    if boundary_geom:
        try:
            geom = shape(boundary_geom)
            _draw_geometry(
                ax,
                geom,
                fill_color=(0.05, 0.28, 0.63, 0.05),
                stroke_color="#1976D2",
                stroke_width=2.5,
                zorder=2,
            )
        except Exception:
            pass

    # Draw CSIDC reference plots with status-based colors
    seen_statuses: set[str] = set()
    for i, ref in enumerate(csidc_ref_plots):
        try:
            geom = shape(ref["geometry"])
            status = (ref.get("status") or "").strip().upper()
            style = _get_csidc_ref_style(status)
            fill_color = _hex_to_rgba(style["fill"], CSIDC_REF_FILL_ALPHA)
            stroke_color = style["stroke"]
            seen_statuses.add(status or "AVAILABLE")
            _draw_geometry(
                ax,
                geom,
                fill_color=fill_color,
                stroke_color=stroke_color,
                stroke_width=1.5,
                zorder=3,
            )

            # Label with plot name if available
            label = ref.get("plot_name") or f"Ref {i + 1}"
            cx, cy = geom.centroid.x, geom.centroid.y
            ax.annotate(
                label,
                (cx, cy),
                fontsize=4,
                ha="center",
                va="center",
                fontweight="bold",
                color="white",
                bbox=dict(
                    boxstyle="round,pad=0.1",
                    facecolor=stroke_color,
                    alpha=0.7,
                    linewidth=0,
                ),
                zorder=5,
            )
        except Exception:
            continue

    # Legend — status-based entries
    legend_elements = []
    for status_key in [
        "ALLOTTED",
        "AVAILABLE",
        "CANCELLED",
        "DISPUTED",
        "UNDER REVIEW",
    ]:
        if status_key in seen_statuses:
            st = CSIDC_REF_STATUS_COLORS[status_key]
            legend_elements.append(
                mpatches.Patch(
                    facecolor=_hex_to_rgba(st["fill"], CSIDC_REF_FILL_ALPHA),
                    edgecolor=st["stroke"],
                    label=f"{st['label']} ({sum(1 for r in csidc_ref_plots if (r.get('status') or '').strip().upper() == status_key)})",
                    linewidth=1.2,
                )
            )
    if boundary_geom:
        legend_elements.append(
            mpatches.Patch(
                facecolor=(0.05, 0.28, 0.63, 0.05),
                edgecolor="#1976D2",
                label="CSIDC Outer Boundary",
                linewidth=1.2,
            )
        )
    leg = ax.legend(
        handles=legend_elements,
        loc="upper right",
        fontsize=7,
        framealpha=0.92,
        edgecolor="#ddd",
        fancybox=True,
    )
    leg.get_frame().set_linewidth(0.5)

    ax.set_title(
        title,
        fontsize=13,
        fontweight="bold",
        pad=12,
        color=CSIDC_DARK,
        fontfamily="sans-serif",
    )
    ax.set_xlabel("Longitude", fontsize=9, color=CSIDC_GRAY)
    ax.set_ylabel("Latitude", fontsize=9, color=CSIDC_GRAY)
    ax.tick_params(labelsize=7, colors=CSIDC_GRAY)

    plt.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight", dpi=150)
    plt.close(fig)
    buf.seek(0)
    return buf.read()


# ---------------------------------------------------------------------------
# Combined Overlay Renderer (Detected + CSIDC Reference)
# ---------------------------------------------------------------------------
def _render_combined_overlay(
    satellite_image: np.ndarray,
    meta: dict,
    plots: list[dict],
    csidc_ref_plots: list[dict],
    boundary_geom: dict | None = None,
    title: str = "Combined View — Detected & CSIDC Reference Plots",
) -> bytes:
    """Render satellite image with both detected and CSIDC reference boundaries."""
    fig, ax = plt.subplots(1, 1, figsize=(16, 10), dpi=150)
    fig.patch.set_facecolor("white")

    bbox = meta["bbox"]
    ax.imshow(
        satellite_image,
        extent=[bbox[0], bbox[2], bbox[1], bbox[3]],
        aspect="auto",
        zorder=1,
    )

    # Layer 1: Outer boundary
    if boundary_geom:
        try:
            geom = shape(boundary_geom)
            _draw_geometry(
                ax,
                geom,
                fill_color=(0.05, 0.28, 0.63, 0.05),
                stroke_color="#1976D2",
                stroke_width=2.5,
                zorder=2,
            )
        except Exception:
            pass

    # Layer 2: CSIDC reference plots (status-based colors, drawn first so detected overlays on top)
    seen_statuses: set[str] = set()
    for i, ref in enumerate(csidc_ref_plots):
        try:
            geom = shape(ref["geometry"])
            status = (ref.get("status") or "").strip().upper()
            style = _get_csidc_ref_style(status)
            fill_color = _hex_to_rgba(style["fill"], CSIDC_REF_FILL_ALPHA)
            stroke_color = style["stroke"]
            seen_statuses.add(status or "AVAILABLE")
            _draw_geometry(
                ax,
                geom,
                fill_color=fill_color,
                stroke_color=stroke_color,
                stroke_width=1.2,
                zorder=3,
            )
        except Exception:
            continue

    # Layer 3: Detected plots (category colors, on top)
    for i, plot in enumerate(plots):
        try:
            geom = shape(plot["geometry"])
            color = plot.get("color", "#3b82f6")
            label = plot.get("label", f"Plot {i + 1}")

            _draw_geometry(
                ax,
                geom,
                fill_color=_hex_to_rgba(color, 0.20),
                stroke_color=color,
                stroke_width=1.4,
                zorder=4,
            )

            cx, cy = geom.centroid.x, geom.centroid.y
            ax.annotate(
                label,
                (cx, cy),
                fontsize=4.5,
                ha="center",
                va="center",
                fontweight="bold",
                color="white",
                bbox=dict(
                    boxstyle="round,pad=0.12",
                    facecolor="black",
                    alpha=0.6,
                    linewidth=0,
                ),
                zorder=6,
            )
        except Exception:
            continue

    # Legend
    legend_elements = [
        mpatches.Patch(
            facecolor=_hex_to_rgba("#ef4444", 0.20),
            edgecolor="#ef4444",
            label=f"Detected Plots ({len(plots)})",
            linewidth=1.2,
        ),
    ]
    for status_key in [
        "ALLOTTED",
        "AVAILABLE",
        "CANCELLED",
        "DISPUTED",
        "UNDER REVIEW",
    ]:
        if status_key in seen_statuses:
            st = CSIDC_REF_STATUS_COLORS[status_key]
            legend_elements.append(
                mpatches.Patch(
                    facecolor=_hex_to_rgba(st["fill"], CSIDC_REF_FILL_ALPHA),
                    edgecolor=st["stroke"],
                    label=f"Ref: {st['label']}",
                    linewidth=1.2,
                )
            )
    if boundary_geom:
        legend_elements.append(
            mpatches.Patch(
                facecolor=(0.05, 0.28, 0.63, 0.05),
                edgecolor="#1976D2",
                label="CSIDC Outer Boundary",
                linewidth=1.2,
            )
        )
    leg = ax.legend(
        handles=legend_elements,
        loc="upper right",
        fontsize=7,
        framealpha=0.92,
        edgecolor="#ddd",
        fancybox=True,
    )
    leg.get_frame().set_linewidth(0.5)

    ax.set_title(
        title,
        fontsize=13,
        fontweight="bold",
        pad=12,
        color=CSIDC_DARK,
        fontfamily="sans-serif",
    )
    ax.set_xlabel("Longitude", fontsize=9, color=CSIDC_GRAY)
    ax.set_ylabel("Latitude", fontsize=9, color=CSIDC_GRAY)
    ax.tick_params(labelsize=7, colors=CSIDC_GRAY)

    plt.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight", dpi=150)
    plt.close(fig)
    buf.seek(0)
    return buf.read()


# ---------------------------------------------------------------------------
# Individual Plot Detail Renderer
# ---------------------------------------------------------------------------
def _render_plot_detail_grid(
    plots: list[dict],
    satellite_image: np.ndarray | None = None,
    meta: dict | None = None,
    csidc_ref_plots: list[dict] | None = None,
    cols: int = 3,
    rows: int = 3,
) -> list[bytes]:
    """Render individual zoomed-in plot views, returning list of PNG page images."""
    from shapely.geometry import box as shapely_box

    pages: list[bytes] = []
    per_page = cols * rows
    plot_plots = [p for p in plots if p.get("category") in ("plot", "parcel")]
    if not plot_plots:
        plot_plots = plots  # Fall back to all if no "plot" category

    # Pre-parse CSIDC ref geometries once for spatial lookups
    ref_geoms: list[tuple[Any, dict]] = []
    if csidc_ref_plots:
        for ref in csidc_ref_plots:
            try:
                ref_geoms.append((shape(ref["geometry"]), ref))
            except Exception:
                continue

    for page_start in range(0, len(plot_plots), per_page):
        page_plots = plot_plots[page_start : page_start + per_page]
        fig, axes = plt.subplots(rows, cols, figsize=(16, 10), dpi=150)
        fig.patch.set_facecolor("white")
        fig.suptitle(
            "Individual Plot Details",
            fontsize=13,
            fontweight="bold",
            color=CSIDC_DARK,
            y=0.98,
        )

        flat_axes = axes.flatten() if hasattr(axes, "flatten") else [axes]

        for idx, ax in enumerate(flat_axes):
            if idx < len(page_plots):
                plot = page_plots[idx]
                try:
                    geom = shape(plot["geometry"])
                    category = plot.get("category", "plot")
                    style = CATEGORY_STYLES.get(category, CATEGORY_STYLES["plot"])
                    label = plot.get("label", f"Plot {idx + 1}")
                    area_sqm = plot.get("area_sqm", 0)
                    area_sqft = plot.get("area_sqft", 0)

                    # Compute bounds with padding
                    bounds = geom.bounds  # minx, miny, maxx, maxy
                    dx = (bounds[2] - bounds[0]) * 0.3
                    dy = (bounds[3] - bounds[1]) * 0.3
                    pad = max(dx, dy, 0.0003)

                    view_minx = bounds[0] - pad
                    view_miny = bounds[1] - pad
                    view_maxx = bounds[2] + pad
                    view_maxy = bounds[3] + pad

                    # Draw satellite background if available
                    if satellite_image is not None and meta is not None:
                        bbox_img = meta["bbox"]
                        ax.imshow(
                            satellite_image,
                            extent=[bbox_img[0], bbox_img[2], bbox_img[1], bbox_img[3]],
                            aspect="auto",
                            zorder=1,
                        )
                    else:
                        ax.set_facecolor("#f5f5f5")

                    # Draw CSIDC reference plots that overlap this view
                    if ref_geoms:
                        view_box = shapely_box(
                            view_minx, view_miny, view_maxx, view_maxy
                        )
                        for ref_geom, ref_data in ref_geoms:
                            if ref_geom.intersects(view_box):
                                ref_status = (
                                    (ref_data.get("status") or "").strip().upper()
                                )
                                ref_style = _get_csidc_ref_style(ref_status)
                                _draw_geometry(
                                    ax,
                                    ref_geom,
                                    fill_color=_hex_to_rgba(
                                        ref_style["fill"], CSIDC_REF_FILL_ALPHA
                                    ),
                                    stroke_color=ref_style["stroke"],
                                    stroke_width=1.0,
                                    zorder=2,
                                )

                    # Draw detected plot boundary (on top)
                    fill_rgba = _parse_rgba_string(style["fill"])
                    _draw_geometry(
                        ax, geom, fill_rgba, style["stroke"], stroke_width=2, zorder=3
                    )

                    ax.set_xlim(view_minx, view_maxx)
                    ax.set_ylim(view_miny, view_maxy)
                    ax.set_aspect("equal")
                    ax.set_title(
                        f"{label}\n{area_sqm:,.0f} sqm / {area_sqft:,.0f} sqft",
                        fontsize=7,
                        fontweight="bold",
                        color=CSIDC_DARK,
                        pad=4,
                    )
                    ax.tick_params(labelsize=5, colors=CSIDC_GRAY)
                except Exception:
                    ax.set_visible(False)
            else:
                ax.set_visible(False)

        plt.tight_layout(rect=[0, 0, 1, 0.95])
        buf = io.BytesIO()
        fig.savefig(buf, format="png", bbox_inches="tight", dpi=150)
        plt.close(fig)
        buf.seek(0)
        pages.append(buf.read())

    return pages


# ---------------------------------------------------------------------------
# Main PDF Generator
# ---------------------------------------------------------------------------
def generate_pdf_report(
    project_name: str,
    area_name: str,
    plots: list[dict],
    basemap_features: list[dict] | None = None,
    deviations: list[dict] | None = None,
    comparison_summary: dict | None = None,
    satellite_image: np.ndarray | None = None,
    satellite_meta: dict | None = None,
    boundary_geom: dict | None = None,
    csidc_ref_plots: list[dict] | None = None,
    compliance_results: list[dict] | None = None,
    compliance_summary: dict | None = None,
) -> Path:
    """Generate a comprehensive, CSIDC-branded PDF report."""

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"drishti_report_{timestamp}.pdf"
    output_path = settings.EXPORTS_DIR / filename

    page_w, page_h = landscape(A4)

    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=landscape(A4),
        rightMargin=20 * mm,
        leftMargin=20 * mm,
        topMargin=38,  # space for header bar
        bottomMargin=32,  # space for footer
    )

    styles = getSampleStyleSheet()

    # Custom styles
    s_title = ParagraphStyle(
        "CTitle",
        parent=styles["Title"],
        fontSize=28,
        textColor=colors.HexColor(CSIDC_DARK),
        spaceAfter=6,
        alignment=TA_CENTER,
    )
    s_org = ParagraphStyle(
        "COrg",
        parent=styles["Title"],
        fontSize=14,
        textColor=colors.HexColor(CSIDC_BLUE),
        spaceAfter=4,
        alignment=TA_CENTER,
    )
    s_subtitle = ParagraphStyle(
        "CSub",
        parent=styles["Heading2"],
        fontSize=16,
        textColor=colors.HexColor(CSIDC_DARK),
        spaceBefore=14,
        spaceAfter=8,
    )
    s_section = ParagraphStyle(
        "CSec",
        parent=styles["Heading3"],
        fontSize=13,
        textColor=colors.HexColor(CSIDC_BLUE),
        spaceBefore=10,
        spaceAfter=6,
    )
    s_body = ParagraphStyle(
        "CBody",
        parent=styles["Normal"],
        fontSize=10,
        leading=14,
        textColor=colors.HexColor(CSIDC_DARK),
    )
    s_small = ParagraphStyle(
        "CSmall",
        parent=styles["Normal"],
        fontSize=8,
        leading=11,
        textColor=colors.HexColor(CSIDC_GRAY),
    )
    s_center = ParagraphStyle("CCenter", parent=s_body, alignment=TA_CENTER)
    s_meta_label = ParagraphStyle(
        "CMetaL", parent=s_body, fontSize=10, textColor=colors.HexColor(CSIDC_GRAY)
    )
    s_meta_val = ParagraphStyle(
        "CMetaV",
        parent=s_body,
        fontSize=11,
        textColor=colors.HexColor(CSIDC_DARK),
        fontName="Helvetica-Bold",
    )

    elements: list = []

    # ===================================================================
    # PAGE 1: COVER PAGE
    # ===================================================================
    elements.append(Spacer(1, 70))

    # Orange accent line
    cover_line = Table([[""]], colWidths=[page_w - 40 * mm], rowHeights=[3])
    cover_line.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(CSIDC_BLUE)),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    elements.append(cover_line)
    elements.append(Spacer(1, 20))

    elements.append(
        Paragraph("CHHATTISGARH STATE INDUSTRIAL<br/>DEVELOPMENT CORPORATION", s_org)
    )
    elements.append(Spacer(1, 8))
    elements.append(Paragraph("Drishti — Automated Land Monitoring Report", s_title))
    elements.append(Spacer(1, 30))

    # Project metadata table
    now_str = datetime.now(timezone.utc).strftime("%d %B %Y, %H:%M UTC")
    active_plots = [p for p in plots if p.get("category") in ("plot", "parcel")]
    total_area_sqm = sum(p.get("area_sqm", 0) for p in plots)
    total_area_sqft = sum(p.get("area_sqft", 0) for p in plots)

    meta_data = [
        ["Project Name", project_name],
        ["Industrial Area", area_name or "N/A"],
        ["Report Date", now_str],
        ["Total Features Detected", str(len(plots))],
        ["Plot Features", str(len(active_plots))],
        [
            "Total Area Covered",
            f"{total_area_sqm:,.0f} sq.m ({total_area_sqft:,.0f} sq.ft)",
        ],
    ]
    meta_table = Table(meta_data, colWidths=[180, 320])
    meta_table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("FONTNAME", (1, 0), (1, -1), "Helvetica"),
                ("FONTSIZE", (0, 0), (-1, -1), 11),
                ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor(CSIDC_GRAY)),
                ("TEXTCOLOR", (1, 0), (1, -1), colors.HexColor(CSIDC_DARK)),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("LINEBELOW", (0, 0), (-1, -2), 0.3, colors.HexColor("#E0E0E0")),
                ("ALIGN", (0, 0), (0, -1), "RIGHT"),
                ("ALIGN", (1, 0), (1, -1), "LEFT"),
                ("LEFTPADDING", (1, 0), (1, -1), 15),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]
        )
    )
    elements.append(meta_table)

    # Compliance summary on cover if available
    if comparison_summary:
        elements.append(Spacer(1, 25))
        elements.append(Paragraph("Compliance Summary", s_section))

        comp_data = [
            ["Metric", "Count"],
            [
                "Total Detected",
                str(comparison_summary.get("total_detected", len(plots))),
            ],
            ["Compliant", str(comparison_summary.get("compliant", 0))],
            ["Encroachments", str(comparison_summary.get("encroachment", 0))],
            [
                "Boundary Mismatches",
                str(comparison_summary.get("boundary_mismatch", 0)),
            ],
            ["Vacant Plots", str(comparison_summary.get("vacant", 0))],
            ["Unauthorized", str(comparison_summary.get("unauthorized", 0))],
        ]
        comp_table = Table(comp_data, colWidths=[200, 100])
        comp_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(CSIDC_BLUE)),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 10),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E0E0E0")),
                    (
                        "ROWBACKGROUNDS",
                        (0, 1),
                        (-1, -1),
                        [colors.HexColor("#E3F2FD"), colors.white],
                    ),
                    ("ALIGN", (1, 0), (1, -1), "CENTER"),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ]
            )
        )
        elements.append(comp_table)

    elements.append(PageBreak())

    # ===================================================================
    # PAGE 2: CATEGORY BREAKDOWN
    # ===================================================================
    elements.append(Paragraph("Category Breakdown", s_subtitle))
    elements.append(Spacer(1, 6))
    elements.append(
        Paragraph(
            "Summary of detected features grouped by category, showing count and total area.",
            s_small,
        )
    )
    elements.append(Spacer(1, 10))

    # Compute category stats
    category_stats: dict[str, dict[str, float]] = {}
    for p in plots:
        cat = p.get("category", "plot")
        if cat not in category_stats:
            category_stats[cat] = {
                "count": 0,
                "area_sqm": 0,
                "area_sqft": 0,
                "perimeter_m": 0,
            }
        category_stats[cat]["count"] += 1
        category_stats[cat]["area_sqm"] += p.get("area_sqm", 0)
        category_stats[cat]["area_sqft"] += p.get("area_sqft", 0)
        category_stats[cat]["perimeter_m"] += p.get("perimeter_m", 0)

    cat_header = [
        "Category",
        "Count",
        "Total Area (sq.m)",
        "Total Area (sq.ft)",
        "Total Perimeter (m)",
        "% of Total Area",
    ]
    cat_rows = [cat_header]
    cat_order = ["plot", "road", "boundary"]
    for cat in cat_order:
        if cat in category_stats:
            st = category_stats[cat]
            pct = (st["area_sqm"] / total_area_sqm * 100) if total_area_sqm > 0 else 0
            cat_label = CATEGORY_STYLES.get(cat, {}).get(
                "label", cat.replace("_", " ").title()
            )
            cat_rows.append(
                [
                    cat_label,
                    str(int(st["count"])),
                    f"{st['area_sqm']:,.1f}",
                    f"{st['area_sqft']:,.1f}",
                    f"{st['perimeter_m']:,.1f}",
                    f"{pct:.1f}%",
                ]
            )

    # Totals row
    cat_rows.append(
        [
            "TOTAL",
            str(len(plots)),
            f"{total_area_sqm:,.1f}",
            f"{total_area_sqft:,.1f}",
            f"{sum(s['perimeter_m'] for s in category_stats.values()):,.1f}",
            "100.0%",
        ]
    )

    cat_avail = page_w - 40 * mm
    cat_table = Table(
        cat_rows,
        colWidths=[
            cat_avail * 0.15,  # Category
            cat_avail * 0.08,  # Count
            cat_avail * 0.19,  # Total Area (sq.m)
            cat_avail * 0.19,  # Total Area (sq.ft)
            cat_avail * 0.19,  # Total Perimeter (m)
            cat_avail * 0.14,  # % of Total Area
        ],
    )
    num_cat_rows = len(cat_rows)
    cat_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(CSIDC_BLUE)),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E0E0E0")),
                (
                    "ROWBACKGROUNDS",
                    (0, 1),
                    (-1, -2),
                    [colors.HexColor("#E3F2FD"), colors.white],
                ),
                # Totals row bold
                (
                    "BACKGROUND",
                    (0, num_cat_rows - 1),
                    (-1, num_cat_rows - 1),
                    colors.HexColor("#BBDEFB"),
                ),
                (
                    "FONTNAME",
                    (0, num_cat_rows - 1),
                    (-1, num_cat_rows - 1),
                    "Helvetica-Bold",
                ),
                ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
                ("ALIGN", (0, 0), (0, -1), "LEFT"),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    elements.append(cat_table)

    # Category pie chart
    elements.append(Spacer(1, 15))
    try:
        fig_pie, ax_pie = plt.subplots(1, 1, figsize=(6, 4), dpi=150)
        fig_pie.patch.set_facecolor("white")

        pie_labels = []
        pie_sizes = []
        pie_colors_list = []
        for cat in cat_order:
            if cat in category_stats and category_stats[cat]["area_sqm"] > 0:
                st_info = CATEGORY_STYLES.get(cat, CATEGORY_STYLES["plot"])
                pie_labels.append(st_info["label"])
                pie_sizes.append(category_stats[cat]["area_sqm"])
                pie_colors_list.append(st_info["stroke"])

        if pie_sizes:
            wedges, texts, autotexts = ax_pie.pie(
                pie_sizes,
                labels=pie_labels,
                colors=pie_colors_list,
                autopct="%1.1f%%",
                pctdistance=0.8,
                textprops={"fontsize": 8},
                startangle=90,
            )
            for t in autotexts:
                t.set_fontsize(7)
                t.set_color("white")
                t.set_fontweight("bold")
            ax_pie.set_title(
                "Area Distribution by Category",
                fontsize=10,
                fontweight="bold",
                color=CSIDC_DARK,
                pad=10,
            )

        pie_buf = io.BytesIO()
        fig_pie.savefig(pie_buf, format="png", bbox_inches="tight", dpi=150)
        plt.close(fig_pie)
        pie_buf.seek(0)
        pie_path = settings.EXPORTS_DIR / f"pie_{timestamp}.png"
        with open(pie_path, "wb") as f:
            f.write(pie_buf.read())
        elements.append(RLImage(str(pie_path), width=340, height=220))
    except Exception as e:
        logger.warning(f"Failed to render pie chart: {e}")

    elements.append(PageBreak())

    # ===================================================================
    # PAGE 3: SATELLITE IMAGERY WITH OVERLAY
    # ===================================================================
    if satellite_image is not None and satellite_meta is not None:
        elements.append(
            Paragraph("Satellite Imagery — Detected Boundaries", s_subtitle)
        )
        elements.append(Spacer(1, 4))
        elements.append(
            Paragraph(
                "High-resolution satellite imagery with detected plot boundaries overlaid. "
                "Source: ESRI World Imagery.",
                s_small,
            )
        )
        elements.append(Spacer(1, 8))

        try:
            sat_png = _render_satellite_overlay(
                satellite_image,
                satellite_meta,
                plots,
                boundary_geom=boundary_geom,
                title=f"{area_name or project_name} — Satellite View",
            )
            sat_path = settings.EXPORTS_DIR / f"satellite_{timestamp}.png"
            with open(sat_path, "wb") as f:
                f.write(sat_png)
            elements.append(RLImage(str(sat_path), width=700, height=420))
        except Exception as e:
            logger.warning(f"Failed to render satellite overlay: {e}")
            elements.append(
                Paragraph(f"<i>Satellite overlay rendering failed: {e}</i>", s_small)
            )

        elements.append(PageBreak())

    # ===================================================================
    # CSIDC REFERENCE PLOTS — SATELLITE OVERLAY
    # ===================================================================
    if csidc_ref_plots and satellite_image is not None and satellite_meta is not None:
        elements.append(
            Paragraph("CSIDC Reference Plots — Satellite Overlay", s_subtitle)
        )
        elements.append(Spacer(1, 4))
        elements.append(
            Paragraph(
                f"Official CSIDC reference plot boundaries ({len(csidc_ref_plots)} plots) "
                "overlaid on satellite imagery. These represent the allotted plot layout "
                "as recorded in the CSIDC GeoServer database.",
                s_small,
            )
        )
        elements.append(Spacer(1, 8))

        try:
            ref_png = _render_csidc_ref_overlay(
                satellite_image,
                satellite_meta,
                csidc_ref_plots,
                boundary_geom=boundary_geom,
                title=f"{area_name or project_name} — CSIDC Reference Plots",
            )
            ref_path = settings.EXPORTS_DIR / f"csidc_ref_{timestamp}.png"
            with open(ref_path, "wb") as f:
                f.write(ref_png)
            elements.append(RLImage(str(ref_path), width=700, height=420))
        except Exception as e:
            logger.warning(f"Failed to render CSIDC ref overlay: {e}")
            elements.append(
                Paragraph(
                    f"<i>CSIDC reference overlay rendering failed: {e}</i>", s_small
                )
            )

        elements.append(PageBreak())

    # ===================================================================
    # COMBINED OVERLAY — DETECTED + CSIDC REFERENCE
    # ===================================================================
    if csidc_ref_plots and satellite_image is not None and satellite_meta is not None:
        elements.append(
            Paragraph("Combined View — Detected & CSIDC Reference Plots", s_subtitle)
        )
        elements.append(Spacer(1, 4))
        elements.append(
            Paragraph(
                f"Side-by-side comparison: {len(plots)} detected boundaries (colored) "
                f"and {len(csidc_ref_plots)} CSIDC reference plots (green) overlaid "
                "on satellite imagery for visual deviation assessment.",
                s_small,
            )
        )
        elements.append(Spacer(1, 8))

        try:
            combined_png = _render_combined_overlay(
                satellite_image,
                satellite_meta,
                plots,
                csidc_ref_plots,
                boundary_geom=boundary_geom,
                title=f"{area_name or project_name} — Detected vs CSIDC Reference",
            )
            combined_path = settings.EXPORTS_DIR / f"combined_{timestamp}.png"
            with open(combined_path, "wb") as f:
                f.write(combined_png)
            elements.append(RLImage(str(combined_path), width=700, height=420))
        except Exception as e:
            logger.warning(f"Failed to render combined overlay: {e}")
            elements.append(
                Paragraph(f"<i>Combined overlay rendering failed: {e}</i>", s_small)
            )

        elements.append(PageBreak())

    # ===================================================================
    # SCHEMATIC MAP
    # ===================================================================
    elements.append(Paragraph("Schematic Map — Plot Layout", s_subtitle))
    elements.append(Spacer(1, 4))
    elements.append(
        Paragraph(
            "CAD-style schematic view showing all detected features with category-specific styling.",
            s_small,
        )
    )
    elements.append(Spacer(1, 8))

    try:
        schematic_png = _render_schematic(
            plots,
            basemap_features,
            deviations,
            title=f"{area_name or project_name} — Schematic View",
        )
        schematic_path = settings.EXPORTS_DIR / f"schematic_{timestamp}.png"
        with open(schematic_path, "wb") as f:
            f.write(schematic_png)
        elements.append(RLImage(str(schematic_path), width=700, height=420))
    except Exception as e:
        logger.warning(f"Failed to render schematic: {e}")
        elements.append(Paragraph(f"<i>Schematic rendering failed: {e}</i>", s_small))

    elements.append(PageBreak())

    # ===================================================================
    # CSIDC REFERENCE SCHEMATIC
    # ===================================================================
    if csidc_ref_plots:
        elements.append(Paragraph("Schematic Map — CSIDC Reference Plots", s_subtitle))
        elements.append(Spacer(1, 4))
        elements.append(
            Paragraph(
                f"CAD-style schematic of {len(csidc_ref_plots)} official CSIDC reference "
                "plot boundaries as recorded in the GeoServer database.",
                s_small,
            )
        )
        elements.append(Spacer(1, 8))

        try:
            ref_schematic_png = _render_csidc_ref_schematic(
                csidc_ref_plots,
                boundary_geom=boundary_geom,
                title=f"{area_name or project_name} — CSIDC Reference Schematic",
            )
            ref_schematic_path = settings.EXPORTS_DIR / f"ref_schematic_{timestamp}.png"
            with open(ref_schematic_path, "wb") as f:
                f.write(ref_schematic_png)
            elements.append(RLImage(str(ref_schematic_path), width=700, height=420))
        except Exception as e:
            logger.warning(f"Failed to render CSIDC ref schematic: {e}")
            elements.append(
                Paragraph(
                    f"<i>CSIDC reference schematic rendering failed: {e}</i>",
                    s_small,
                )
            )

        elements.append(PageBreak())

    # ===================================================================
    # PAGE 5+: INDIVIDUAL PLOT DETAILS
    # ===================================================================
    try:
        detail_pages = _render_plot_detail_grid(
            plots,
            satellite_image=satellite_image,
            meta=satellite_meta,
            csidc_ref_plots=csidc_ref_plots,
            cols=3,
            rows=3,
        )
        for page_idx, page_png in enumerate(detail_pages):
            if page_idx == 0:
                elements.append(Paragraph("Individual Plot Details", s_subtitle))
                elements.append(Spacer(1, 4))
                elements.append(
                    Paragraph(
                        "Zoomed-in view of each detected plot showing boundary detail and measurements.",
                        s_small,
                    )
                )
                elements.append(Spacer(1, 8))

            detail_path = settings.EXPORTS_DIR / f"detail_{timestamp}_{page_idx}.png"
            with open(detail_path, "wb") as f:
                f.write(page_png)
            elements.append(RLImage(str(detail_path), width=700, height=420))

            if page_idx < len(detail_pages) - 1:
                elements.append(PageBreak())

    except Exception as e:
        logger.warning(f"Failed to render plot details: {e}")

    elements.append(PageBreak())

    # ===================================================================
    # COMPLIANCE ANALYSIS (Green Cover + Construction Timeline)
    # Placed before Plot Inventory for prominence.
    # ===================================================================
    if compliance_results and compliance_summary:
        avail_w = page_w - 40 * mm
        overall = compliance_summary.get("overall", {})
        gc = compliance_summary.get("green_cover", {})
        ct = compliance_summary.get("construction_timeline", {})
        total_checked = compliance_summary.get("total_plots", 0)
        fully_compliant = overall.get("fully_compliant", 0)
        non_compliant = overall.get("non_compliant", 0)
        unchecked = overall.get("unchecked", 0)
        compliance_rate = (
            (fully_compliant / total_checked * 100) if total_checked > 0 else 0
        )

        # ── Page 1: Overview ──────────────────────────────────────────────
        # Wrap the overview header + rate box + breakdown in KeepTogether
        # so they don't split across pages.
        overview_elements = []
        overview_elements.append(Paragraph("Compliance Analysis", s_subtitle))
        overview_elements.append(Spacer(1, 4))
        overview_elements.append(
            Paragraph(
                "Automated compliance assessment based on satellite-derived green cover "
                "analysis (Excess Green Index) and construction timeline verification "
                "against allotment records.",
                s_small,
            )
        )
        overview_elements.append(Spacer(1, 14))

        # ── Overall compliance rate highlight ──
        rate_color = (
            "#2E7D32"
            if compliance_rate >= 75
            else ("#F57F17" if compliance_rate >= 50 else "#C62828")
        )
        rate_row = [
            [
                Paragraph(
                    f'<font size="28" color="{rate_color}"><b>{compliance_rate:.0f}%</b></font>',
                    ParagraphStyle("rate", parent=s_body, alignment=TA_CENTER),
                ),
                Paragraph(
                    f'<font size="10" color="{CSIDC_DARK}"><b>Overall Compliance Rate</b></font>'
                    f'<br/><font size="8" color="{CSIDC_GRAY}">'
                    f"{fully_compliant} of {total_checked} plots fully compliant | "
                    f"{non_compliant} non-compliant | {unchecked} unchecked</font>",
                    ParagraphStyle(
                        "rate_desc", parent=s_body, alignment=TA_LEFT, leading=15
                    ),
                ),
            ]
        ]
        rate_tbl = Table(rate_row, colWidths=[100, page_w - 40 * mm - 100])
        rate_tbl.setStyle(
            TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("BACKGROUND", (0, 0), (0, 0), colors.HexColor("#F5F5F5")),
                    ("ROUNDEDCORNERS", [6, 6, 6, 6]),
                    ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#E0E0E0")),
                    ("TOPPADDING", (0, 0), (-1, -1), 10),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
                    ("LEFTPADDING", (0, 0), (-1, -1), 10),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ]
            )
        )
        overview_elements.append(rate_tbl)
        overview_elements.append(Spacer(1, 16))

        # ── Detailed summary table ──
        overview_elements.append(Paragraph("Compliance Breakdown", s_section))
        overview_elements.append(Spacer(1, 6))

        # Compute averages
        green_pcts = [
            r.get("green_cover_pct")
            for r in compliance_results
            if r.get("green_cover_pct") is not None
        ]
        avg_green = sum(green_pcts) / len(green_pcts) if green_pcts else 0
        min_green = min(green_pcts) if green_pcts else 0
        max_green = max(green_pcts) if green_pcts else 0

        breakdown_data = [
            ["Metric", "Value", "Details"],
            [
                "Total Plots Assessed",
                str(total_checked),
                f"{fully_compliant} compliant, {non_compliant} non-compliant, {unchecked} unchecked",
            ],
            [
                "Green Cover — Checked",
                str(gc.get("checked", 0)),
                f"{gc.get('compliant', 0)} compliant, "
                f"{gc.get('non_compliant', 0)} non-compliant "
                f"(threshold: {gc.get('threshold_pct', 20)}%)",
            ],
            [
                "Green Cover — Average",
                f"{avg_green:.1f}%",
                f"Range: {min_green:.1f}% – {max_green:.1f}%",
            ],
            [
                "Construction Timeline — Checked",
                str(ct.get("checked", 0)),
                f"{ct.get('compliant', 0)} on track, "
                f"{ct.get('non_compliant', 0)} past deadline "
                f"({ct.get('deadline_years', 2)}-year requirement)",
            ],
        ]
        breakdown_tbl = Table(
            breakdown_data, colWidths=[160, 70, page_w - 40 * mm - 230]
        )
        breakdown_tbl.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(CSIDC_BLUE)),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTNAME", (0, 1), (0, -1), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 9),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E0E0E0")),
                    (
                        "ROWBACKGROUNDS",
                        (0, 1),
                        (-1, -1),
                        [colors.HexColor("#E3F2FD"), colors.white],
                    ),
                    ("ALIGN", (1, 0), (1, -1), "CENTER"),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                    ("LEFTPADDING", (0, 0), (-1, -1), 6),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ]
            )
        )
        overview_elements.append(breakdown_tbl)
        elements.append(KeepTogether(overview_elements))
        elements.append(Spacer(1, 16))

        # ── Green cover bar chart ──
        if green_pcts:
            elements.append(Paragraph("Green Cover Distribution", s_section))
            elements.append(Spacer(1, 6))

            try:
                fig_gc, ax_gc = plt.subplots(1, 1, figsize=(9, 3.2), dpi=150)
                fig_gc.patch.set_facecolor("white")

                labels = []
                values = []
                bar_colors = []
                threshold = gc.get("threshold_pct", 20)
                for r in compliance_results:
                    pct = r.get("green_cover_pct")
                    if pct is not None:
                        lbl = r.get("label", "")
                        # Shorten label if needed
                        if len(lbl) > 12:
                            lbl = lbl[:10] + ".."
                        labels.append(lbl)
                        values.append(pct)
                        bar_colors.append("#4CAF50" if pct >= threshold else "#EF5350")

                x_pos = range(len(labels))
                bars = ax_gc.bar(
                    x_pos, values, color=bar_colors, width=0.7, edgecolor="white"
                )
                ax_gc.axhline(
                    y=threshold,
                    color="#F57F17",
                    linestyle="--",
                    linewidth=1.2,
                    label=f"Threshold ({threshold}%)",
                )
                ax_gc.set_xticks(x_pos)
                ax_gc.set_xticklabels(labels, fontsize=6, rotation=45, ha="right")
                ax_gc.set_ylabel("Green Cover %", fontsize=8)
                ax_gc.set_ylim(0, max(max(values) * 1.15, threshold * 1.5))
                ax_gc.legend(fontsize=7, loc="upper right")
                ax_gc.spines["top"].set_visible(False)
                ax_gc.spines["right"].set_visible(False)
                ax_gc.tick_params(axis="y", labelsize=7)
                ax_gc.set_title(
                    "Per-Plot Green Cover Percentage",
                    fontsize=9,
                    fontweight="bold",
                    color=CSIDC_DARK,
                    pad=8,
                )

                # Add value labels on bars
                for bar, val in zip(bars, values):
                    ax_gc.text(
                        bar.get_x() + bar.get_width() / 2,
                        bar.get_height() + 0.5,
                        f"{val:.0f}%",
                        ha="center",
                        va="bottom",
                        fontsize=5.5,
                        fontweight="bold",
                    )

                gc_buf = io.BytesIO()
                fig_gc.savefig(gc_buf, format="png", bbox_inches="tight", dpi=150)
                plt.close(fig_gc)
                gc_buf.seek(0)
                gc_chart_path = settings.EXPORTS_DIR / f"gc_chart_{timestamp}.png"
                with open(gc_chart_path, "wb") as f:
                    f.write(gc_buf.read())
                elements.append(RLImage(str(gc_chart_path), width=avail_w, height=220))
            except Exception as e:
                logger.warning(f"Failed to render green cover chart: {e}")

        elements.append(PageBreak())

        # ── Page 2: Per-plot compliance detail table (paginated) ───────────
        elements.append(Paragraph("Per-Plot Compliance Details", s_subtitle))
        elements.append(Spacer(1, 4))
        elements.append(
            Paragraph(
                f"Detailed compliance status for each of the {total_checked} assessed plots. "
                "Green cover is computed from satellite imagery using Excess Green Index (ExG = 2G - R - B). "
                f"Construction timeline compliance requires activity within {ct.get('deadline_years', 2)} years of allotment.",
                s_small,
            )
        )
        elements.append(Spacer(1, 10))

        # Table header
        compl_header = [
            "#",
            "Plot Name",
            "Allotment\nDate",
            "Green\nCover %",
            "Green\nStatus",
            "Construction\nDeadline",
            "Construction\nStarted",
            "Construction\nStatus",
            "Overall",
        ]

        # Distribute columns proportionally across the full page width
        compl_col_widths = [
            avail_w * 0.04,  # #
            avail_w * 0.18,  # Plot Name
            avail_w * 0.12,  # Allotment Date
            avail_w * 0.09,  # Green Cover %
            avail_w * 0.10,  # Green Status
            avail_w * 0.12,  # Construction Deadline
            avail_w * 0.10,  # Construction Started
            avail_w * 0.11,  # Construction Status
            avail_w * 0.08,  # Overall
        ]
        # Assign any rounding remainder to Plot Name column
        compl_col_widths[1] += avail_w - sum(compl_col_widths)

        COMPL_ROWS_PER_PAGE = 24
        for chunk_start in range(0, len(compliance_results), COMPL_ROWS_PER_PAGE):
            chunk = compliance_results[chunk_start : chunk_start + COMPL_ROWS_PER_PAGE]
            compl_rows = [compl_header]

            for idx, r in enumerate(chunk, start=chunk_start + 1):
                green_pct = r.get("green_cover_pct")
                green_pct_str = f"{green_pct:.1f}%" if green_pct is not None else "N/A"

                green_status = r.get("is_green_compliant")
                if green_status is True:
                    green_status_str = "Pass"
                elif green_status is False:
                    green_status_str = "Fail"
                else:
                    green_status_str = "N/A"

                allot_date = r.get("allotment_date")
                if allot_date:
                    try:
                        if isinstance(allot_date, str):
                            allot_str = datetime.fromisoformat(allot_date).strftime(
                                "%d %b %Y"
                            )
                        else:
                            allot_str = allot_date.strftime("%d %b %Y")
                    except Exception:
                        allot_str = str(allot_date)
                else:
                    allot_str = "N/A"

                deadline = r.get("construction_deadline")
                if deadline:
                    try:
                        if isinstance(deadline, str):
                            deadline_str = datetime.fromisoformat(deadline).strftime(
                                "%d %b %Y"
                            )
                        else:
                            deadline_str = deadline.strftime("%d %b %Y")
                    except Exception:
                        deadline_str = str(deadline)
                else:
                    deadline_str = "N/A"

                constr_started = r.get("construction_started")
                if constr_started is True:
                    constr_started_str = "Yes"
                elif constr_started is False:
                    constr_started_str = "No"
                else:
                    constr_started_str = "N/A"

                constr_status = r.get("is_construction_compliant")
                if constr_status is True:
                    constr_status_str = "Pass"
                elif constr_status is False:
                    constr_status_str = "Fail"
                else:
                    constr_status_str = "N/A"

                overall_status = r.get("is_compliant")
                if overall_status is True:
                    overall_str = "PASS"
                elif overall_status is False:
                    overall_str = "FAIL"
                else:
                    overall_str = "N/A"

                compl_rows.append(
                    [
                        str(idx),
                        Paragraph(r.get("label", f"Plot {idx}"), s_small),
                        allot_str,
                        green_pct_str,
                        green_status_str,
                        deadline_str,
                        constr_started_str,
                        constr_status_str,
                        overall_str,
                    ]
                )

            compl_tbl = Table(compl_rows, colWidths=compl_col_widths, repeatRows=1)
            compl_tbl_style = [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(CSIDC_BLUE)),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, 0), 7),
                ("FONTSIZE", (0, 1), (-1, -1), 7),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#E0E0E0")),
                (
                    "ROWBACKGROUNDS",
                    (0, 1),
                    (-1, -1),
                    [colors.white, colors.HexColor("#F5F5F5")],
                ),
                ("ALIGN", (0, 0), (0, -1), "CENTER"),
                ("ALIGN", (2, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("LEFTPADDING", (0, 0), (-1, -1), 3),
                ("RIGHTPADDING", (0, 0), (-1, -1), 3),
            ]

            # Colour-code green status cells (col 4)
            for row_idx in range(1, len(compl_rows)):
                g_val = compl_rows[row_idx][4]
                if g_val == "Pass":
                    compl_tbl_style.append(
                        (
                            "BACKGROUND",
                            (4, row_idx),
                            (4, row_idx),
                            colors.HexColor("#C8E6C9"),
                        )
                    )
                    compl_tbl_style.append(
                        (
                            "TEXTCOLOR",
                            (4, row_idx),
                            (4, row_idx),
                            colors.HexColor("#2E7D32"),
                        )
                    )
                elif g_val == "Fail":
                    compl_tbl_style.append(
                        (
                            "BACKGROUND",
                            (4, row_idx),
                            (4, row_idx),
                            colors.HexColor("#FFCDD2"),
                        )
                    )
                    compl_tbl_style.append(
                        (
                            "TEXTCOLOR",
                            (4, row_idx),
                            (4, row_idx),
                            colors.HexColor("#C62828"),
                        )
                    )

                # Colour-code construction status cells (col 7)
                c_val = compl_rows[row_idx][7]
                if c_val == "Pass":
                    compl_tbl_style.append(
                        (
                            "BACKGROUND",
                            (7, row_idx),
                            (7, row_idx),
                            colors.HexColor("#C8E6C9"),
                        )
                    )
                    compl_tbl_style.append(
                        (
                            "TEXTCOLOR",
                            (7, row_idx),
                            (7, row_idx),
                            colors.HexColor("#2E7D32"),
                        )
                    )
                elif c_val == "Fail":
                    compl_tbl_style.append(
                        (
                            "BACKGROUND",
                            (7, row_idx),
                            (7, row_idx),
                            colors.HexColor("#FFCDD2"),
                        )
                    )
                    compl_tbl_style.append(
                        (
                            "TEXTCOLOR",
                            (7, row_idx),
                            (7, row_idx),
                            colors.HexColor("#C62828"),
                        )
                    )

                # Colour-code overall status cells (col 8)
                o_val = compl_rows[row_idx][8]
                if o_val == "PASS":
                    compl_tbl_style.append(
                        (
                            "BACKGROUND",
                            (8, row_idx),
                            (8, row_idx),
                            colors.HexColor("#C8E6C9"),
                        )
                    )
                    compl_tbl_style.append(
                        (
                            "TEXTCOLOR",
                            (8, row_idx),
                            (8, row_idx),
                            colors.HexColor("#2E7D32"),
                        )
                    )
                elif o_val == "FAIL":
                    compl_tbl_style.append(
                        (
                            "BACKGROUND",
                            (8, row_idx),
                            (8, row_idx),
                            colors.HexColor("#FFCDD2"),
                        )
                    )
                    compl_tbl_style.append(
                        (
                            "TEXTCOLOR",
                            (8, row_idx),
                            (8, row_idx),
                            colors.HexColor("#C62828"),
                        )
                    )

            compl_tbl.setStyle(TableStyle(compl_tbl_style))
            elements.append(compl_tbl)

            if chunk_start + COMPL_ROWS_PER_PAGE < len(compliance_results):
                elements.append(PageBreak())

        # ── Violations detail (for non-compliant plots only) ──────────────
        violation_plots = [r for r in compliance_results if r.get("violations")]
        if violation_plots:
            elements.append(PageBreak())
            elements.append(Paragraph("Compliance Violations — Detail", s_subtitle))
            elements.append(Spacer(1, 4))
            elements.append(
                Paragraph(
                    f"{len(violation_plots)} plot(s) have one or more compliance violations "
                    "that require attention.",
                    s_small,
                )
            )
            elements.append(Spacer(1, 10))

            viol_header = ["#", "Plot Name", "Green Cover", "Violation(s)"]
            viol_col_widths = [
                avail_w * 0.04,  # #
                avail_w * 0.16,  # Plot Name
                avail_w * 0.10,  # Green Cover
                avail_w * 0.70,  # Violation(s)
            ]

            VIOL_ROWS_PER_PAGE = 18
            for viol_start in range(0, len(violation_plots), VIOL_ROWS_PER_PAGE):
                viol_chunk = violation_plots[
                    viol_start : viol_start + VIOL_ROWS_PER_PAGE
                ]
                viol_rows = [viol_header]
                for vi, r in enumerate(viol_chunk, start=viol_start + 1):
                    green_pct = r.get("green_cover_pct")
                    green_str = f"{green_pct:.1f}%" if green_pct is not None else "N/A"
                    violations = r.get("violations", [])
                    viol_text = "<br/>".join(
                        f'<font color="#C62828">\u2022 {v}</font>' for v in violations
                    )
                    viol_rows.append(
                        [
                            str(vi),
                            Paragraph(
                                f"<b>{r.get('label', f'Plot {vi}')}</b>",
                                ParagraphStyle("vn", parent=s_small, fontSize=8),
                            ),
                            green_str,
                            Paragraph(
                                viol_text,
                                ParagraphStyle(
                                    "vd",
                                    parent=s_small,
                                    fontSize=7,
                                    leading=10,
                                ),
                            ),
                        ]
                    )

                viol_tbl = Table(
                    viol_rows,
                    colWidths=viol_col_widths,
                    repeatRows=1,
                )
                viol_tbl.setStyle(
                    TableStyle(
                        [
                            (
                                "BACKGROUND",
                                (0, 0),
                                (-1, 0),
                                colors.HexColor("#C62828"),
                            ),
                            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                            ("FONTSIZE", (0, 0), (-1, 0), 8),
                            ("FONTSIZE", (0, 1), (-1, -1), 8),
                            (
                                "GRID",
                                (0, 0),
                                (-1, -1),
                                0.4,
                                colors.HexColor("#E0E0E0"),
                            ),
                            (
                                "ROWBACKGROUNDS",
                                (0, 1),
                                (-1, -1),
                                [colors.HexColor("#FFF3F3"), colors.white],
                            ),
                            ("ALIGN", (0, 0), (0, -1), "CENTER"),
                            ("ALIGN", (2, 0), (2, -1), "CENTER"),
                            ("VALIGN", (0, 0), (-1, -1), "TOP"),
                            ("TOPPADDING", (0, 0), (-1, -1), 4),
                            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                            ("LEFTPADDING", (0, 0), (-1, -1), 5),
                            ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                        ]
                    )
                )
                elements.append(viol_tbl)

                if viol_start + VIOL_ROWS_PER_PAGE < len(violation_plots):
                    elements.append(PageBreak())

        elements.append(PageBreak())

    # ===================================================================
    # PLOT INVENTORY TABLE (paginated with repeated headers)
    # ===================================================================
    elements.append(Paragraph("Plot Inventory", s_subtitle))
    elements.append(Spacer(1, 4))
    elements.append(
        Paragraph(
            f"Complete list of all {len(plots)} detected features with measurements.",
            s_small,
        )
    )
    elements.append(Spacer(1, 10))

    inv_header = [
        "#",
        "Label",
        "Category",
        "Area (sq.m)",
        "Area (sq.ft)",
        "Perimeter (m)",
        "Status",
    ]
    inv_avail = page_w - 40 * mm
    col_widths = [
        inv_avail * 0.04,  # #
        inv_avail * 0.22,  # Label
        inv_avail * 0.12,  # Category
        inv_avail * 0.13,  # Area (sq.m)
        inv_avail * 0.13,  # Area (sq.ft)
        inv_avail * 0.13,  # Perimeter (m)
        inv_avail * 0.18,  # Status
    ]
    # Assign rounding remainder to Label column
    col_widths[1] += inv_avail - sum(col_widths)

    header_style_table = TableStyle(
        [
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(CSIDC_BLUE)),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, 0), 8),
            ("ALIGN", (0, 0), (0, -1), "CENTER"),
            ("ALIGN", (3, 0), (5, -1), "RIGHT"),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("LEFTPADDING", (0, 0), (-1, -1), 5),
            ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ]
    )

    # Split into chunks for pagination with repeated headers
    ROWS_PER_PAGE = 28
    for chunk_start in range(0, len(plots), ROWS_PER_PAGE):
        chunk = plots[chunk_start : chunk_start + ROWS_PER_PAGE]
        table_data = [inv_header]

        for i, plot in enumerate(chunk, start=chunk_start + 1):
            status = "Active"
            if deviations:
                for dev in deviations:
                    if dev.get("plot_label") == plot.get("label"):
                        status = (
                            dev.get("deviation_type", "Unknown")
                            .replace("_", " ")
                            .title()
                        )
                        break

            cat_label = CATEGORY_STYLES.get(plot.get("category", "plot"), {}).get(
                "label", plot.get("category", "plot").replace("_", " ").title()
            )

            table_data.append(
                [
                    str(i),
                    plot.get("label", f"Plot {i}"),
                    cat_label,
                    f"{plot.get('area_sqm', 0):,.1f}",
                    f"{plot.get('area_sqft', 0):,.1f}",
                    f"{plot.get('perimeter_m', 0):,.1f}",
                    status,
                ]
            )

        t = Table(table_data, colWidths=col_widths, repeatRows=1)
        num_rows = len(table_data)
        style_cmds = [
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(CSIDC_BLUE)),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#E0E0E0")),
            (
                "ROWBACKGROUNDS",
                (0, 1),
                (-1, -1),
                [colors.HexColor("#E3F2FD"), colors.white],
            ),
            ("ALIGN", (0, 0), (0, -1), "CENTER"),
            ("ALIGN", (3, 0), (5, -1), "RIGHT"),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("LEFTPADDING", (0, 0), (-1, -1), 5),
            ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ]
        t.setStyle(TableStyle(style_cmds))
        elements.append(t)

        # Page break between chunks (but not after the last one)
        if chunk_start + ROWS_PER_PAGE < len(plots):
            elements.append(PageBreak())

    # ===================================================================
    # DEVIATION DETAILS (if available)
    # ===================================================================
    if deviations:
        non_compliant = [
            d for d in deviations if d.get("deviation_type") != "COMPLIANT"
        ]
        if non_compliant:
            elements.append(PageBreak())
            elements.append(Paragraph("Deviation Details", s_subtitle))
            elements.append(Spacer(1, 4))
            elements.append(
                Paragraph(
                    f"{len(non_compliant)} non-compliant deviation(s) detected.",
                    s_small,
                )
            )
            elements.append(Spacer(1, 10))

            for dev in non_compliant:
                dev_type = dev.get("deviation_type", "Unknown")
                dev_color = DEVIATION_COLORS.get(dev_type, "#9ca3af")
                sev = dev.get("severity", "low")

                # Deviation header
                elements.append(
                    Paragraph(
                        f'<font color="{dev_color}"><b>{dev.get("plot_label", "Unknown")}</b></font>'
                        f" — {dev_type.replace('_', ' ').title()}"
                        f' <font color="{CSIDC_GRAY}" size="8">[{sev.upper()}]</font>',
                        s_section,
                    )
                )

                if dev.get("description"):
                    elements.append(Paragraph(dev["description"], s_body))

                details = dev.get("details", {})
                if details:
                    detail_rows = []
                    if details.get("detected_area_sqm"):
                        detail_rows.append(
                            [
                                "Detected Area",
                                f"{details['detected_area_sqm']:,.1f} sq.m",
                            ]
                        )
                    if details.get("basemap_area_sqm"):
                        detail_rows.append(
                            ["Basemap Area", f"{details['basemap_area_sqm']:,.1f} sq.m"]
                        )
                    if details.get("encroachment_area_sqm"):
                        detail_rows.append(
                            [
                                "Encroachment Area",
                                f"{details['encroachment_area_sqm']:,.1f} sq.m",
                            ]
                        )
                    if details.get("vacant_area_sqm"):
                        detail_rows.append(
                            ["Vacant Area", f"{details['vacant_area_sqm']:,.1f} sq.m"]
                        )
                    if details.get("match_percentage"):
                        detail_rows.append(["Match", f"{details['match_percentage']}%"])

                    if detail_rows:
                        dt = Table(detail_rows, colWidths=[150, 150])
                        dt.setStyle(
                            TableStyle(
                                [
                                    ("FONTSIZE", (0, 0), (-1, -1), 9),
                                    (
                                        "GRID",
                                        (0, 0),
                                        (-1, -1),
                                        0.4,
                                        colors.HexColor("#E0E0E0"),
                                    ),
                                    ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                                    (
                                        "TEXTCOLOR",
                                        (0, 0),
                                        (0, -1),
                                        colors.HexColor(CSIDC_GRAY),
                                    ),
                                    ("TOPPADDING", (0, 0), (-1, -1), 3),
                                    ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                                ]
                            )
                        )
                        elements.append(dt)
                elements.append(Spacer(1, 10))

    # ===================================================================
    # FINAL PAGE: DISCLAIMER / FOOTER
    # ===================================================================
    elements.append(Spacer(1, 30))

    # Orange line
    end_line = Table([[""]], colWidths=[page_w - 40 * mm], rowHeights=[2])
    end_line.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(CSIDC_BLUE)),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    elements.append(end_line)
    elements.append(Spacer(1, 8))

    elements.append(
        Paragraph(
            "<b>Disclaimer:</b> This report was generated by <b>Drishti — Automated Land Monitoring System</b> "
            "for the Chhattisgarh State Industrial Development Corporation (CSIDC). "
            "Data accuracy depends on satellite imagery resolution and AI model predictions. "
            "This report is intended for internal assessment purposes only and should not be used "
            "as a legal survey document.",
            ParagraphStyle(
                "Disclaimer",
                parent=styles["Normal"],
                fontSize=8,
                textColor=colors.HexColor(CSIDC_GRAY),
                leading=11,
                spaceBefore=4,
            ),
        )
    )

    # Build with header/footer
    doc.build(elements, onFirstPage=_page_template, onLaterPages=_page_template)

    # Cleanup temp images
    for pattern in [
        f"schematic_{timestamp}.png",
        f"satellite_{timestamp}.png",
        f"csidc_ref_{timestamp}.png",
        f"combined_{timestamp}.png",
        f"ref_schematic_{timestamp}.png",
        f"pie_{timestamp}.png",
        f"gc_chart_{timestamp}.png",
        f"detail_{timestamp}_*.png",
    ]:
        for temp in settings.EXPORTS_DIR.glob(pattern):
            try:
                temp.unlink()
            except OSError:
                pass

    logger.info(f"PDF report generated: {output_path}")
    return output_path


# ---------------------------------------------------------------------------
# Dashboard PDF Report Generator
# ---------------------------------------------------------------------------
def generate_dashboard_pdf(
    stats: dict[str, Any],
    user: dict[str, str] | None = None,
) -> Path:
    """Generate a CSIDC-branded PDF report of dashboard statistics.

    Parameters
    ----------
    stats : dict
        Dashboard statistics (KPIs, area-wise data, revenue, compliance, etc.)
    user : dict, optional
        User info dict with 'name', 'role', 'department', 'designation' keys.

    Returns
    -------
    Path to the generated PDF file.
    """

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"drishti_dashboard_{timestamp}.pdf"
    output_path = settings.EXPORTS_DIR / filename

    page_w, page_h = landscape(A4)
    avail_w = page_w - 40 * mm  # content width inside margins

    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=landscape(A4),
        rightMargin=20 * mm,
        leftMargin=20 * mm,
        topMargin=38,
        bottomMargin=32,
    )

    styles = getSampleStyleSheet()

    # Custom styles (same as project PDF for visual consistency)
    s_title = ParagraphStyle(
        "DTitle",
        parent=styles["Title"],
        fontSize=28,
        textColor=colors.HexColor(CSIDC_DARK),
        spaceAfter=6,
        alignment=TA_CENTER,
    )
    s_org = ParagraphStyle(
        "DOrg",
        parent=styles["Title"],
        fontSize=14,
        textColor=colors.HexColor(CSIDC_BLUE),
        spaceAfter=4,
        alignment=TA_CENTER,
    )
    s_subtitle = ParagraphStyle(
        "DSub",
        parent=styles["Heading2"],
        fontSize=16,
        textColor=colors.HexColor(CSIDC_DARK),
        spaceBefore=14,
        spaceAfter=8,
    )
    s_section = ParagraphStyle(
        "DSec",
        parent=styles["Heading3"],
        fontSize=13,
        textColor=colors.HexColor(CSIDC_BLUE),
        spaceBefore=10,
        spaceAfter=6,
    )
    s_body = ParagraphStyle(
        "DBody",
        parent=styles["Normal"],
        fontSize=10,
        leading=14,
        textColor=colors.HexColor(CSIDC_DARK),
    )
    s_small = ParagraphStyle(
        "DSmall",
        parent=styles["Normal"],
        fontSize=8,
        leading=11,
        textColor=colors.HexColor(CSIDC_GRAY),
    )
    s_center = ParagraphStyle("DCenter", parent=s_body, alignment=TA_CENTER)
    s_meta_label = ParagraphStyle(
        "DMetaL", parent=s_body, fontSize=10, textColor=colors.HexColor(CSIDC_GRAY)
    )
    s_meta_val = ParagraphStyle(
        "DMetaV",
        parent=s_body,
        fontSize=11,
        textColor=colors.HexColor(CSIDC_DARK),
        fontName="Helvetica-Bold",
    )
    s_kpi_value = ParagraphStyle(
        "DKpiVal",
        parent=s_body,
        fontSize=18,
        textColor=colors.HexColor(CSIDC_DARK),
        fontName="Helvetica-Bold",
        alignment=TA_CENTER,
    )
    s_kpi_label = ParagraphStyle(
        "DKpiLbl",
        parent=s_body,
        fontSize=9,
        textColor=colors.HexColor(CSIDC_GRAY),
        alignment=TA_CENTER,
    )

    elements: list = []

    # Track temp chart files for cleanup
    temp_files: list[str] = []

    # ===================================================================
    # PAGE 1: COVER PAGE
    # ===================================================================
    elements.append(Spacer(1, 70))

    # Accent line
    cover_line = Table([[""]], colWidths=[avail_w], rowHeights=[3])
    cover_line.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(CSIDC_BLUE)),
                ("LINEBELOW", (0, 0), (-1, -1), 0, colors.white),
            ]
        )
    )
    elements.append(cover_line)
    elements.append(Spacer(1, 20))

    elements.append(Paragraph("DRISHTI", s_title))
    elements.append(
        Paragraph(
            "Chhattisgarh State Industrial Development Corporation",
            s_org,
        )
    )
    elements.append(Spacer(1, 8))
    elements.append(Paragraph("Dashboard Statistics Report", s_subtitle))
    elements.append(Spacer(1, 20))

    # Metadata table
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    meta_rows: list[list] = [
        [
            Paragraph("Report Type", s_meta_label),
            Paragraph("Dashboard Summary", s_meta_val),
        ],
        [
            Paragraph("Generated", s_meta_label),
            Paragraph(now_str, s_meta_val),
        ],
    ]
    if user:
        meta_rows.append(
            [
                Paragraph("Prepared By", s_meta_label),
                Paragraph(user.get("name", "N/A"), s_meta_val),
            ]
        )
        meta_rows.append(
            [
                Paragraph("Department", s_meta_label),
                Paragraph(user.get("department", "N/A"), s_meta_val),
            ]
        )
        meta_rows.append(
            [
                Paragraph("Designation", s_meta_label),
                Paragraph(user.get("designation", "N/A"), s_meta_val),
            ]
        )

    meta_table = Table(meta_rows, colWidths=[120, 300])
    meta_table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                (
                    "LINEBELOW",
                    (0, 0),
                    (-1, -2),
                    0.5,
                    colors.HexColor("#E0E0E0"),
                ),
            ]
        )
    )
    elements.append(meta_table)
    elements.append(Spacer(1, 20))

    # Quick summary paragraph
    total_areas = stats.get("totalIndustrialAreas", 0)
    total_plots = stats.get("totalPlots", 0)
    compliance_rate = stats.get("complianceRate", 0)
    revenue_collected = stats.get("totalRevenueCollected", 0)
    revenue_pending = stats.get("totalRevenuePending", 0)

    elements.append(
        Paragraph(
            f"This report summarises the operational dashboard for <b>{total_areas}</b> "
            f"industrial areas comprising <b>{total_plots:,}</b> plots. "
            f"The overall compliance rate stands at <b>{compliance_rate:.1f}%</b>. "
            f"Total revenue collected is <b>\u20b9{revenue_collected:,.1f} Lakhs</b> "
            f"with <b>\u20b9{revenue_pending:,.1f} Lakhs</b> pending.",
            s_body,
        )
    )

    elements.append(PageBreak())

    # ===================================================================
    # PAGE 2: KEY PERFORMANCE INDICATORS
    # ===================================================================
    elements.append(Paragraph("Key Performance Indicators", s_subtitle))
    elements.append(Spacer(1, 8))

    def _fmt_num(n: Any) -> str:
        if isinstance(n, float):
            return f"{n:,.1f}"
        if isinstance(n, int):
            return f"{n:,}"
        return str(n)

    total_allocated = stats.get("totalAllocatedPlots", 0)
    total_vacant = stats.get("totalVacantPlots", 0)
    total_encroach = stats.get("totalEncroachments", 0)
    active_leases = stats.get("activeLeases", 0)

    kpi_data = [
        ("Total Industrial Areas", _fmt_num(total_areas)),
        ("Total Plots", _fmt_num(total_plots)),
        ("Allocated Plots", _fmt_num(total_allocated)),
        ("Vacant Plots", _fmt_num(total_vacant)),
        ("Encroachments", _fmt_num(total_encroach)),
        ("Compliance Rate", f"{compliance_rate:.1f}%"),
        ("Active Leases", _fmt_num(active_leases)),
        (
            "Revenue Collected",
            f"\u20b9{revenue_collected:,.1f} L",
        ),
    ]

    # Build a 4x2 grid of KPI cards
    kpi_rows: list[list] = []
    for row_start in range(0, len(kpi_data), 4):
        label_row = []
        value_row = []
        for label, value in kpi_data[row_start : row_start + 4]:
            label_row.append(Paragraph(label, s_kpi_label))
            value_row.append(Paragraph(value, s_kpi_value))
        # Pad if fewer than 4
        while len(label_row) < 4:
            label_row.append(Paragraph("", s_kpi_label))
            value_row.append(Paragraph("", s_kpi_value))
        kpi_rows.append(value_row)
        kpi_rows.append(label_row)

    col_w = avail_w / 4
    kpi_table = Table(kpi_rows, colWidths=[col_w] * 4)
    kpi_table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("TOPPADDING", (0, 0), (-1, -1), 10),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#E0E0E0")),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E0E0E0")),
                # Alternate shading on value rows (rows 0 and 2)
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(CSIDC_BG)),
                ("BACKGROUND", (0, 2), (-1, 2), colors.HexColor(CSIDC_BG)),
            ]
        )
    )
    elements.append(kpi_table)
    elements.append(Spacer(1, 16))

    # ===================================================================
    # MONTHLY REVENUE CHART
    # ===================================================================
    monthly_revenue = stats.get("monthlyRevenue", [])
    if monthly_revenue:
        elements.append(Paragraph("Monthly Revenue Overview", s_section))
        elements.append(Spacer(1, 4))

        try:
            months = [m.get("month", "")[:3] for m in monthly_revenue]
            collected = [m.get("collected", 0) for m in monthly_revenue]
            pending = [m.get("pending", 0) for m in monthly_revenue]

            fig, ax = plt.subplots(figsize=(12, 4.5), dpi=150)
            fig.patch.set_facecolor("white")
            x = np.arange(len(months))
            bar_w = 0.35

            bars1 = ax.bar(
                x - bar_w / 2,
                collected,
                bar_w,
                label="Collected",
                color=CSIDC_BLUE,
                edgecolor="white",
                linewidth=0.5,
            )
            bars2 = ax.bar(
                x + bar_w / 2,
                pending,
                bar_w,
                label="Pending",
                color="#ef4444",
                edgecolor="white",
                linewidth=0.5,
            )

            # Value labels
            for bar in bars1:
                h = bar.get_height()
                if h > 0:
                    ax.text(
                        bar.get_x() + bar.get_width() / 2,
                        h + 0.3,
                        f"{h:.0f}",
                        ha="center",
                        va="bottom",
                        fontsize=7,
                        color=CSIDC_DARK,
                    )
            for bar in bars2:
                h = bar.get_height()
                if h > 0:
                    ax.text(
                        bar.get_x() + bar.get_width() / 2,
                        h + 0.3,
                        f"{h:.0f}",
                        ha="center",
                        va="bottom",
                        fontsize=7,
                        color="#ef4444",
                    )

            ax.set_xticks(x)
            ax.set_xticklabels(months, fontsize=8)
            ax.set_ylabel("Amount (\u20b9 Lakhs)", fontsize=9, color=CSIDC_GRAY)
            ax.legend(fontsize=8, loc="upper right")
            ax.spines["top"].set_visible(False)
            ax.spines["right"].set_visible(False)
            ax.spines["left"].set_color("#E0E0E0")
            ax.spines["bottom"].set_color("#E0E0E0")
            ax.tick_params(colors=CSIDC_GRAY, labelsize=8)
            ax.set_axisbelow(True)
            ax.yaxis.grid(True, alpha=0.3, color="#E0E0E0")

            plt.tight_layout()

            buf = io.BytesIO()
            fig.savefig(buf, format="png", bbox_inches="tight", dpi=150)
            plt.close(fig)
            buf.seek(0)

            chart_path = settings.EXPORTS_DIR / f"dash_revenue_{timestamp}.png"
            with open(chart_path, "wb") as f:
                f.write(buf.read())
            temp_files.append(str(chart_path))

            elements.append(
                RLImage(str(chart_path), width=avail_w, height=avail_w * 0.375)
            )
        except Exception as e:
            logger.warning(f"Failed to render revenue chart: {e}")

    elements.append(Spacer(1, 8))

    # ===================================================================
    # COMPLIANCE TREND CHART
    # ===================================================================
    compliance_trend = stats.get("complianceTrend", [])
    if compliance_trend:
        elements.append(Paragraph("Compliance Trend", s_section))
        elements.append(Spacer(1, 4))

        try:
            months = [c.get("month", "")[:3] for c in compliance_trend]
            rates = [c.get("rate", 0) for c in compliance_trend]

            fig, ax = plt.subplots(figsize=(12, 3.5), dpi=150)
            fig.patch.set_facecolor("white")

            ax.fill_between(
                range(len(months)),
                rates,
                alpha=0.15,
                color=CSIDC_BLUE,
            )
            ax.plot(
                range(len(months)),
                rates,
                color=CSIDC_BLUE,
                linewidth=2,
                marker="o",
                markersize=5,
                markerfacecolor="white",
                markeredgecolor=CSIDC_BLUE,
                markeredgewidth=1.5,
            )

            for i, rate in enumerate(rates):
                ax.annotate(
                    f"{rate:.1f}%",
                    (i, rate),
                    textcoords="offset points",
                    xytext=(0, 10),
                    ha="center",
                    fontsize=7,
                    color=CSIDC_DARK,
                )

            ax.set_xticks(range(len(months)))
            ax.set_xticklabels(months, fontsize=8)
            ax.set_ylabel("Compliance Rate (%)", fontsize=9, color=CSIDC_GRAY)
            ax.set_ylim(0, 100)
            ax.spines["top"].set_visible(False)
            ax.spines["right"].set_visible(False)
            ax.spines["left"].set_color("#E0E0E0")
            ax.spines["bottom"].set_color("#E0E0E0")
            ax.tick_params(colors=CSIDC_GRAY, labelsize=8)
            ax.set_axisbelow(True)
            ax.yaxis.grid(True, alpha=0.3, color="#E0E0E0")

            plt.tight_layout()

            buf = io.BytesIO()
            fig.savefig(buf, format="png", bbox_inches="tight", dpi=150)
            plt.close(fig)
            buf.seek(0)

            chart_path = settings.EXPORTS_DIR / f"dash_compliance_{timestamp}.png"
            with open(chart_path, "wb") as f:
                f.write(buf.read())
            temp_files.append(str(chart_path))

            elements.append(
                RLImage(str(chart_path), width=avail_w, height=avail_w * 0.29)
            )
        except Exception as e:
            logger.warning(f"Failed to render compliance trend chart: {e}")

    elements.append(PageBreak())

    # ===================================================================
    # PAGE 3: INDUSTRIAL AREA STATISTICS TABLE
    # ===================================================================
    area_wise = stats.get("areaWise", [])
    if area_wise:
        elements.append(Paragraph("Industrial Area Statistics", s_subtitle))
        elements.append(Spacer(1, 8))

        header = [
            "Area Name",
            "District",
            "Plots",
            "Allocated",
            "Vacant",
            "Encroach.",
            "Occupancy",
            "Compliance",
            "Revenue\n(Collected)",
            "Revenue\n(Pending)",
        ]

        s_cell = ParagraphStyle("DCell", parent=s_body, fontSize=8, leading=10)
        s_cell_center = ParagraphStyle("DCellC", parent=s_cell, alignment=TA_CENTER)
        s_hdr = ParagraphStyle(
            "DHdr",
            parent=s_body,
            fontSize=8,
            leading=10,
            textColor=colors.white,
            fontName="Helvetica-Bold",
            alignment=TA_CENTER,
        )

        header_row = [Paragraph(h, s_hdr) for h in header]
        data_rows = [header_row]

        for area in area_wise:
            row = [
                Paragraph(str(area.get("name", "")), s_cell),
                Paragraph(str(area.get("district", "")), s_cell_center),
                Paragraph(str(area.get("plots", 0)), s_cell_center),
                Paragraph(str(area.get("allocated", 0)), s_cell_center),
                Paragraph(str(area.get("vacant", 0)), s_cell_center),
                Paragraph(str(area.get("encroachments", 0)), s_cell_center),
                Paragraph(f"{area.get('occupancy', 0):.0f}%", s_cell_center),
                Paragraph(f"{area.get('compliance', 0):.0f}%", s_cell_center),
                Paragraph(
                    f"\u20b9{area.get('revenueCollected', 0):,.1f}L",
                    s_cell_center,
                ),
                Paragraph(
                    f"\u20b9{area.get('revenuePending', 0):,.1f}L",
                    s_cell_center,
                ),
            ]
            data_rows.append(row)

        col_widths = [
            avail_w * 0.16,  # Name
            avail_w * 0.10,  # District
            avail_w * 0.07,  # Plots
            avail_w * 0.08,  # Allocated
            avail_w * 0.07,  # Vacant
            avail_w * 0.08,  # Encroach
            avail_w * 0.09,  # Occupancy
            avail_w * 0.10,  # Compliance
            avail_w * 0.12,  # Rev Collected
            avail_w * 0.13,  # Rev Pending
        ]

        area_table = Table(data_rows, colWidths=col_widths, repeatRows=1)
        table_style_cmds: list = [
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(CSIDC_BLUE)),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("ALIGN", (0, 1), (0, -1), "LEFT"),  # Name left-aligned
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("INNERGRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#E0E0E0")),
            ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor(CSIDC_BLUE)),
        ]

        # Alternate row shading
        for i in range(1, len(data_rows)):
            if i % 2 == 0:
                table_style_cmds.append(
                    ("BACKGROUND", (0, i), (-1, i), colors.HexColor("#F5F8FF"))
                )

        area_table.setStyle(TableStyle(table_style_cmds))
        elements.append(area_table)

    elements.append(PageBreak())

    # ===================================================================
    # PAGE 4: CATEGORY DISTRIBUTION + SURVEYS + TOP DEFAULTERS
    # ===================================================================

    # -- Category Distribution Chart --
    cat_dist = stats.get("categoryDistribution", [])
    if cat_dist:
        elements.append(Paragraph("Category Distribution", s_section))
        elements.append(Spacer(1, 4))

        try:
            categories = [c.get("category", "") for c in cat_dist]
            counts = [c.get("count", 0) for c in cat_dist]
            areas_sqm = [c.get("area_sqm", 0) for c in cat_dist]

            fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 4), dpi=150)
            fig.patch.set_facecolor("white")

            cat_colors = [
                CSIDC_BLUE,
                "#1976D2",
                "#42A5F5",
                "#64B5F6",
                "#90CAF9",
                "#BBDEFB",
            ]

            # Pie chart of counts
            wedges, texts, autotexts = ax1.pie(
                counts,
                labels=categories,
                autopct="%1.0f%%",
                colors=cat_colors[: len(categories)],
                textprops={"fontsize": 8},
                pctdistance=0.75,
                startangle=90,
            )
            for t in autotexts:
                t.set_fontsize(7)
                t.set_color("white")
                t.set_fontweight("bold")
            ax1.set_title("Plot Count by Category", fontsize=10, color=CSIDC_DARK)

            # Horizontal bar chart of area
            y_pos = range(len(categories))
            ax2.barh(
                y_pos,
                [a / 1000 for a in areas_sqm],
                color=cat_colors[: len(categories)],
                edgecolor="white",
                linewidth=0.5,
            )
            ax2.set_yticks(y_pos)
            ax2.set_yticklabels(categories, fontsize=8)
            ax2.set_xlabel("Area (x1000 sq.m)", fontsize=9, color=CSIDC_GRAY)
            ax2.set_title("Area by Category", fontsize=10, color=CSIDC_DARK)
            ax2.spines["top"].set_visible(False)
            ax2.spines["right"].set_visible(False)
            ax2.spines["left"].set_color("#E0E0E0")
            ax2.spines["bottom"].set_color("#E0E0E0")
            ax2.tick_params(colors=CSIDC_GRAY, labelsize=8)

            plt.tight_layout()

            buf = io.BytesIO()
            fig.savefig(buf, format="png", bbox_inches="tight", dpi=150)
            plt.close(fig)
            buf.seek(0)

            chart_path = settings.EXPORTS_DIR / f"dash_category_{timestamp}.png"
            with open(chart_path, "wb") as f:
                f.write(buf.read())
            temp_files.append(str(chart_path))

            elements.append(
                RLImage(str(chart_path), width=avail_w, height=avail_w * 0.33)
            )
        except Exception as e:
            logger.warning(f"Failed to render category chart: {e}")

    elements.append(Spacer(1, 12))

    # -- Surveys Overview --
    surveys_completed = stats.get("surveysCompleted", 0)
    surveys_pending = stats.get("surveysPending", 0)
    last_survey = stats.get("lastSurveyDate", "N/A")

    elements.append(Paragraph("Surveys Overview", s_section))
    elements.append(Spacer(1, 4))

    survey_data = [
        [
            Paragraph("Surveys Completed", s_meta_label),
            Paragraph(str(surveys_completed), s_meta_val),
            Paragraph("Surveys Pending", s_meta_label),
            Paragraph(str(surveys_pending), s_meta_val),
            Paragraph("Last Survey Date", s_meta_label),
            Paragraph(str(last_survey), s_meta_val),
        ]
    ]
    survey_table = Table(
        survey_data,
        colWidths=[
            avail_w * 0.15,
            avail_w * 0.10,
            avail_w * 0.15,
            avail_w * 0.10,
            avail_w * 0.15,
            avail_w * 0.12,
        ],
    )
    survey_table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#E0E0E0")),
            ]
        )
    )
    elements.append(survey_table)
    elements.append(Spacer(1, 12))

    # -- Top Defaulters --
    top_defaulters = stats.get("topDefaulters", [])
    if top_defaulters:
        elements.append(Paragraph("Top Defaulters", s_section))
        elements.append(Spacer(1, 4))

        def_header = [
            "Plot ID",
            "Allottee Name",
            "Area",
            "Due Amount\n(\u20b9 Lakhs)",
            "Months\nOverdue",
            "Karma Score",
        ]
        s_def_hdr = ParagraphStyle(
            "DDefHdr",
            parent=s_body,
            fontSize=8,
            leading=10,
            textColor=colors.white,
            fontName="Helvetica-Bold",
            alignment=TA_CENTER,
        )
        s_def_cell = ParagraphStyle("DDefCell", parent=s_body, fontSize=8, leading=10)
        s_def_cell_c = ParagraphStyle(
            "DDefCellC", parent=s_def_cell, alignment=TA_CENTER
        )

        def_rows = [[Paragraph(h, s_def_hdr) for h in def_header]]
        for d in top_defaulters:
            karma = d.get("karmaScore", 0)
            if karma >= 80:
                karma_color = "#22c55e"
            elif karma >= 50:
                karma_color = "#eab308"
            else:
                karma_color = "#ef4444"

            def_rows.append(
                [
                    Paragraph(str(d.get("plotId", "")), s_def_cell_c),
                    Paragraph(str(d.get("allotteeName", "")), s_def_cell),
                    Paragraph(str(d.get("area", "")), s_def_cell),
                    Paragraph(f"\u20b9{d.get('dueAmount', 0):,.1f}", s_def_cell_c),
                    Paragraph(str(d.get("monthsOverdue", 0)), s_def_cell_c),
                    Paragraph(
                        f"<font color='{karma_color}'><b>{karma}</b></font>",
                        s_def_cell_c,
                    ),
                ]
            )

        def_col_w = [
            avail_w * 0.12,
            avail_w * 0.22,
            avail_w * 0.22,
            avail_w * 0.14,
            avail_w * 0.12,
            avail_w * 0.12,
        ]
        def_table = Table(def_rows, colWidths=def_col_w, repeatRows=1)
        def_style_cmds: list = [
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(CSIDC_BLUE)),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("ALIGN", (1, 1), (2, -1), "LEFT"),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("INNERGRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#E0E0E0")),
            ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor(CSIDC_BLUE)),
        ]
        for i in range(1, len(def_rows)):
            if i % 2 == 0:
                def_style_cmds.append(
                    ("BACKGROUND", (0, i), (-1, i), colors.HexColor("#F5F8FF"))
                )
        def_table.setStyle(TableStyle(def_style_cmds))
        elements.append(def_table)

    elements.append(PageBreak())

    # ===================================================================
    # PAGE 5: RECENT ACTIVITIES + QUICK STATS
    # ===================================================================
    recent = stats.get("recentActivities", [])
    if recent:
        elements.append(Paragraph("Recent Activities", s_subtitle))
        elements.append(Spacer(1, 8))

        act_header = ["#", "Type", "Description", "Area", "Date", "Status"]
        s_act_hdr = ParagraphStyle(
            "DActHdr",
            parent=s_body,
            fontSize=8,
            leading=10,
            textColor=colors.white,
            fontName="Helvetica-Bold",
            alignment=TA_CENTER,
        )
        s_act_cell = ParagraphStyle("DActCell", parent=s_body, fontSize=8, leading=10)
        s_act_cell_c = ParagraphStyle(
            "DActCellC", parent=s_act_cell, alignment=TA_CENTER
        )

        act_rows = [[Paragraph(h, s_act_hdr) for h in act_header]]
        for idx, a in enumerate(recent[:15], 1):
            status = str(a.get("status", ""))
            if status.lower() in ("completed", "resolved"):
                status_color = "#22c55e"
            elif status.lower() in ("pending", "in_progress"):
                status_color = "#eab308"
            else:
                status_color = CSIDC_GRAY

            act_rows.append(
                [
                    Paragraph(str(idx), s_act_cell_c),
                    Paragraph(str(a.get("type", "")), s_act_cell_c),
                    Paragraph(str(a.get("description", "")), s_act_cell),
                    Paragraph(str(a.get("area", "")), s_act_cell),
                    Paragraph(str(a.get("date", "")), s_act_cell_c),
                    Paragraph(
                        f"<font color='{status_color}'><b>{status}</b></font>",
                        s_act_cell_c,
                    ),
                ]
            )

        act_col_w = [
            avail_w * 0.05,
            avail_w * 0.12,
            avail_w * 0.33,
            avail_w * 0.18,
            avail_w * 0.12,
            avail_w * 0.12,
        ]
        act_table = Table(act_rows, colWidths=act_col_w, repeatRows=1)
        act_style_cmds: list = [
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(CSIDC_BLUE)),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("ALIGN", (2, 1), (2, -1), "LEFT"),
            ("ALIGN", (3, 1), (3, -1), "LEFT"),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("INNERGRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#E0E0E0")),
            ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor(CSIDC_BLUE)),
        ]
        for i in range(1, len(act_rows)):
            if i % 2 == 0:
                act_style_cmds.append(
                    ("BACKGROUND", (0, i), (-1, i), colors.HexColor("#F5F8FF"))
                )
        act_table.setStyle(TableStyle(act_style_cmds))
        elements.append(act_table)

    elements.append(Spacer(1, 16))

    # -- Quick Stats Footer --
    elements.append(Paragraph("Financial & Operational Summary", s_section))
    elements.append(Spacer(1, 6))

    total_area_sqm = stats.get("totalArea_sqm", 0)
    expired_leases = stats.get("expiredLeases", 0)
    total_alloc_area = stats.get("totalAllocatedArea_sqm", 0)

    qs_rows = [
        [
            Paragraph("Revenue Pending", s_meta_label),
            Paragraph(f"\u20b9{revenue_pending:,.1f} Lakhs", s_meta_val),
            Paragraph("Expired Leases", s_meta_label),
            Paragraph(str(expired_leases), s_meta_val),
            Paragraph("Total Area", s_meta_label),
            Paragraph(f"{total_area_sqm:,.0f} sq.m", s_meta_val),
        ],
        [
            Paragraph("Allocated Area", s_meta_label),
            Paragraph(f"{total_alloc_area:,.0f} sq.m", s_meta_val),
            Paragraph("Active Leases", s_meta_label),
            Paragraph(str(active_leases), s_meta_val),
            Paragraph("Surveys Pending", s_meta_label),
            Paragraph(str(surveys_pending), s_meta_val),
        ],
    ]
    qs_table = Table(
        qs_rows,
        colWidths=[
            avail_w * 0.14,
            avail_w * 0.18,
            avail_w * 0.14,
            avail_w * 0.14,
            avail_w * 0.14,
            avail_w * 0.18,
        ],
    )
    qs_table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#E0E0E0")),
                (
                    "LINEBELOW",
                    (0, 0),
                    (-1, 0),
                    0.5,
                    colors.HexColor("#E0E0E0"),
                ),
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#FAFAFA")),
            ]
        )
    )
    elements.append(qs_table)
    elements.append(Spacer(1, 20))

    # -- Disclaimer --
    elements.append(
        Paragraph(
            "<i>This report has been auto-generated by the DRISHTI Automated Land "
            "Monitoring System for CSIDC internal use. Data is based on the latest "
            "available records and satellite imagery. For official records, please "
            "refer to the original CSIDC documentation.</i>",
            s_small,
        )
    )

    # ===================================================================
    # BUILD PDF
    # ===================================================================
    doc.build(elements, onFirstPage=_page_template, onLaterPages=_page_template)

    # Cleanup temp chart images
    for temp_path in temp_files:
        try:
            Path(temp_path).unlink()
        except OSError:
            pass

    logger.info(f"Dashboard PDF report generated: {output_path}")
    return output_path
