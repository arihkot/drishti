"""PDF report generator."""

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
from matplotlib.collections import PatchCollection
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
)
from shapely.geometry import shape

from backend.config import settings

logger = logging.getLogger(__name__)


def _render_schematic(
    plots: list[dict],
    basemap_features: list[dict] | None = None,
    deviations: list[dict] | None = None,
    title: str = "Land Parcel Schematic",
) -> bytes:
    """Render a CAD-style schematic of plots as PNG bytes."""
    fig, ax = plt.subplots(1, 1, figsize=(14, 10), dpi=150)
    ax.set_facecolor("white")
    fig.patch.set_facecolor("white")

    # Draw basemap boundaries if available
    if basemap_features:
        for feature in basemap_features:
            try:
                geom = shape(feature.get("geometry", feature))
                if hasattr(geom, "exterior"):
                    x, y = geom.exterior.xy
                    ax.plot(
                        x, y, color="#00CED1", linewidth=2.5, linestyle="-", zorder=2
                    )
                    ax.fill(x, y, alpha=0.05, color="#00CED1")
            except Exception:
                continue

    # Draw detected plots
    for i, plot in enumerate(plots):
        try:
            geom = shape(plot["geometry"])
            category = plot.get("category", "parcel")
            color = plot.get("color", "#FF0000")
            label = plot.get("label", f"Plot {i + 1}")

            if hasattr(geom, "exterior"):
                x, y = geom.exterior.xy
                ax.plot(x, y, color=color, linewidth=1.5, zorder=3)

                # Hatching for parcels
                if category == "parcel":
                    ax.fill(x, y, alpha=0.15, color=color, hatch="///", zorder=1)
                elif category == "road":
                    ax.fill(x, y, alpha=0.1, color=color, zorder=1)

                # Label at centroid
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
                        boxstyle="round,pad=0.2",
                        facecolor="white",
                        edgecolor=color,
                        alpha=0.9,
                    ),
                    zorder=5,
                )
        except Exception:
            continue

    # Draw deviations if available
    if deviations:
        for dev in deviations:
            if dev.get("deviation_geometry"):
                try:
                    geom = shape(dev["deviation_geometry"])
                    if hasattr(geom, "exterior"):
                        x, y = geom.exterior.xy
                        dev_type = dev.get("deviation_type", "")
                        if dev_type == "ENCROACHMENT":
                            ax.fill(x, y, alpha=0.4, color="#FF6600", zorder=4)
                            ax.plot(
                                x,
                                y,
                                color="#FF6600",
                                linewidth=2,
                                linestyle="--",
                                zorder=4,
                            )
                        elif dev_type == "VACANT":
                            ax.fill(x, y, alpha=0.3, color="#808080", zorder=4)
                except Exception:
                    continue

    ax.set_title(title, fontsize=14, fontweight="bold", pad=15)
    ax.set_xlabel("Longitude", fontsize=10)
    ax.set_ylabel("Latitude", fontsize=10)
    ax.set_aspect("equal")
    ax.grid(True, alpha=0.2, linestyle="--")

    # Legend
    legend_elements = [
        mpatches.Patch(
            facecolor="#FF000025",
            edgecolor="#FF0000",
            label="Detected Parcel",
            hatch="///",
        ),
        mpatches.Patch(
            facecolor="#00CED125", edgecolor="#00CED1", label="Basemap Boundary"
        ),
    ]
    if deviations:
        legend_elements.extend(
            [
                mpatches.Patch(
                    facecolor="#FF660066", edgecolor="#FF6600", label="Encroachment"
                ),
                mpatches.Patch(
                    facecolor="#80808050", edgecolor="#808080", label="Vacant"
                ),
            ]
        )
    ax.legend(handles=legend_elements, loc="upper right", fontsize=8)

    plt.tight_layout()

    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight", dpi=150)
    plt.close(fig)
    buf.seek(0)
    return buf.read()


def generate_pdf_report(
    project_name: str,
    area_name: str,
    plots: list[dict],
    basemap_features: list[dict] | None = None,
    deviations: list[dict] | None = None,
    comparison_summary: dict | None = None,
) -> Path:
    """
    Generate a PDF report.

    Returns:
        Path to the generated PDF file.
    """
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"drishti_report_{timestamp}.pdf"
    output_path = settings.EXPORTS_DIR / filename

    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=landscape(A4),
        rightMargin=20 * mm,
        leftMargin=20 * mm,
        topMargin=20 * mm,
        bottomMargin=20 * mm,
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "CustomTitle",
        parent=styles["Title"],
        fontSize=24,
        textColor=colors.HexColor("#1a237e"),
        spaceAfter=20,
    )
    subtitle_style = ParagraphStyle(
        "CustomSubtitle",
        parent=styles["Heading2"],
        fontSize=16,
        textColor=colors.HexColor("#283593"),
        spaceAfter=10,
    )
    body_style = ParagraphStyle(
        "CustomBody",
        parent=styles["Normal"],
        fontSize=10,
        leading=14,
    )
    header_style = ParagraphStyle(
        "Header",
        parent=styles["Heading3"],
        fontSize=13,
        textColor=colors.HexColor("#1a237e"),
        spaceBefore=15,
        spaceAfter=8,
    )

    elements = []

    # === Cover Page ===
    elements.append(Spacer(1, 60))
    elements.append(
        Paragraph(
            "CHHATTISGARH STATE INDUSTRIAL DEVELOPMENT CORPORATION",
            ParagraphStyle(
                "OrgTitle",
                parent=styles["Title"],
                fontSize=18,
                textColor=colors.HexColor("#0d47a1"),
            ),
        )
    )
    elements.append(Spacer(1, 10))
    elements.append(
        Paragraph(
            "Drishti - Automated Land Monitoring Report",
            title_style,
        )
    )
    elements.append(Spacer(1, 20))
    elements.append(Paragraph(f"<b>Project:</b> {project_name}", body_style))
    elements.append(Paragraph(f"<b>Area:</b> {area_name or 'N/A'}", body_style))
    elements.append(
        Paragraph(
            f"<b>Generated:</b> {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
            body_style,
        )
    )
    elements.append(Paragraph(f"<b>Total Plots Detected:</b> {len(plots)}", body_style))
    elements.append(Spacer(1, 30))

    # Summary statistics
    if comparison_summary:
        elements.append(Paragraph("Compliance Summary", subtitle_style))
        summary_data = [
            ["Metric", "Count"],
            [
                "Total Detected Plots",
                str(comparison_summary.get("total_detected", len(plots))),
            ],
            ["Compliant", str(comparison_summary.get("compliant", 0))],
            ["Encroachments", str(comparison_summary.get("encroachment", 0))],
            [
                "Boundary Mismatches",
                str(comparison_summary.get("boundary_mismatch", 0)),
            ],
            ["Vacant Plots", str(comparison_summary.get("vacant", 0))],
            [
                "Unauthorized Development",
                str(comparison_summary.get("unauthorized", 0)),
            ],
        ]
        t = Table(summary_data, colWidths=[200, 100])
        t.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a237e")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 10),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                    (
                        "ROWBACKGROUNDS",
                        (0, 1),
                        (-1, -1),
                        [colors.whitesmoke, colors.white],
                    ),
                    ("ALIGN", (1, 0), (1, -1), "CENTER"),
                ]
            )
        )
        elements.append(t)

    elements.append(PageBreak())

    # === Schematic Map ===
    elements.append(Paragraph("Plot Schematic", subtitle_style))

    schematic_png = _render_schematic(
        plots,
        basemap_features,
        deviations,
        title=f"{project_name} - {area_name or 'Plot Map'}",
    )
    schematic_path = settings.EXPORTS_DIR / f"schematic_{timestamp}.png"
    with open(schematic_path, "wb") as f:
        f.write(schematic_png)

    img = RLImage(str(schematic_path), width=700, height=450)
    elements.append(img)
    elements.append(PageBreak())

    # === Plot Inventory ===
    elements.append(Paragraph("Plot Inventory", subtitle_style))

    plot_data = [
        [
            "#",
            "Label",
            "Category",
            "Area (sq.m)",
            "Area (sq.ft)",
            "Perimeter (m)",
            "Status",
        ]
    ]
    for i, plot in enumerate(plots, 1):
        status = "Active"
        if deviations:
            for dev in deviations:
                if dev.get("plot_label") == plot.get("label"):
                    status = dev.get("deviation_type", "Unknown")
                    break

        plot_data.append(
            [
                str(i),
                plot.get("label", f"Plot {i}"),
                plot.get("category", "parcel").capitalize(),
                str(round(plot.get("area_sqm", 0), 1)),
                str(round(plot.get("area_sqft", 0), 1)),
                str(round(plot.get("perimeter_m", 0), 1)),
                status,
            ]
        )

    t = Table(plot_data, colWidths=[30, 120, 80, 80, 80, 80, 120])
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a237e")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.whitesmoke, colors.white]),
                ("ALIGN", (0, 0), (0, -1), "CENTER"),
                ("ALIGN", (3, 0), (5, -1), "RIGHT"),
            ]
        )
    )
    elements.append(t)

    # === Deviation Details ===
    if deviations:
        elements.append(PageBreak())
        elements.append(Paragraph("Deviation Details", subtitle_style))

        for dev in deviations:
            if dev.get("deviation_type") == "COMPLIANT":
                continue

            elements.append(
                Paragraph(
                    f"<b>{dev.get('plot_label', 'Unknown')}</b> - {dev.get('deviation_type', 'Unknown')}",
                    header_style,
                )
            )
            elements.append(Paragraph(dev.get("description", ""), body_style))

            details = dev.get("details", {})
            if details:
                detail_data = [
                    ["Detected Area", f"{details.get('detected_area_sqm', 0)} sq.m"],
                    ["Basemap Area", f"{details.get('basemap_area_sqm', 0)} sq.m"],
                    [
                        "Encroachment Area",
                        f"{details.get('encroachment_area_sqm', 0)} sq.m",
                    ],
                    ["Vacant Area", f"{details.get('vacant_area_sqm', 0)} sq.m"],
                    ["Match %", f"{details.get('match_percentage', 0)}%"],
                ]
                t = Table(detail_data, colWidths=[150, 150])
                t.setStyle(
                    TableStyle(
                        [
                            ("FONTSIZE", (0, 0), (-1, -1), 9),
                            ("GRID", (0, 0), (-1, -1), 0.5, colors.lightgrey),
                            ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                        ]
                    )
                )
                elements.append(t)
                elements.append(Spacer(1, 10))

    # === Footer ===
    elements.append(Spacer(1, 30))
    elements.append(
        Paragraph(
            "This report was generated by Drishti - Automated Land Monitoring System for CSIDC. "
            "Data accuracy depends on satellite imagery resolution and SAM model predictions.",
            ParagraphStyle(
                "Footer", parent=styles["Normal"], fontSize=8, textColor=colors.grey
            ),
        )
    )

    doc.build(elements)

    # Cleanup temp schematic
    try:
        schematic_path.unlink()
    except OSError:
        pass

    logger.info(f"PDF report generated: {output_path}")
    return output_path
