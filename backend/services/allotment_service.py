"""Allotment data service — fetches from CSIDC or generates believable mock data.

Tries to extract allotment dates and construction status from CSIDC
reference plot properties.  If no real data is available, generates
realistic mock records with plausible dates and statuses.
"""

import hashlib
import logging
import random
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import AllotmentRecord, CsidcReferencePlot

logger = logging.getLogger(__name__)

# Construction deadline: 2 years after allotment
CONSTRUCTION_DEADLINE_YEARS = 2

# ── Realistic mock data pools ──
# These produce small, believable data points — not obviously fake.

_FIRM_NAMES = [
    "Shri Balaji Enterprises",
    "Chhattisgarh Steel Works",
    "Raipur Auto Components",
    "Bhilai Engineering Pvt Ltd",
    "Mahamaya Industries",
    "Narmada Fabricators",
    "Durg Cement Products",
    "Korba Power Ancillaries",
    "Bilaspur Agro Processing",
    "Rajnandgaon Textiles",
    "CG Pharma Solutions",
    "Bastar Minerals Ltd",
    "Kanker Forest Products",
    "Surguja Rice Mills",
    "Janjgir Steel Tubes",
    "Raigarh Ferro Alloys",
    "Dhamtari Food Processing",
    "Kawardha Timbers",
    "Mungeli Oil Mills",
    "Balod Pipe Industries",
]

_CATEGORIES = [
    "industrial",
    "small_scale_industrial",
    "medium_industrial",
    "commercial",
    "warehouse",
]

_STATUSES_ACTIVE = [
    "allotted",
    "allotted - construction in progress",
    "allotted - operational",
    "allotted - under development",
]

_STATUSES_VACANT = [
    "vacant",
    "unallotted",
    "cancelled - returned",
]

_STATUSES_DELAYED = [
    "allotted - no construction",
    "allotted - construction not started",
    "allotted - show cause issued",
]


def _deterministic_seed(area_name: str, plot_name: str) -> int:
    """Generate a deterministic seed from area + plot name so mock data
    is consistent across runs for the same plot."""
    key = f"{area_name}:{plot_name}"
    return int(hashlib.md5(key.encode()).hexdigest()[:8], 16)


def _parse_csidc_allotment_date(properties: dict) -> datetime | None:
    """Try to extract an allotment date from CSIDC reference properties."""
    # Look for any date-like field in the properties
    date_keys = [
        "allotment_date",
        "allot_date",
        "date_of_allotment",
        "allotment_dt",
        "dt_allotment",
        "date_allot",
        "allot_dt",
        "ALLOTMENT_DATE",
        "DATE_ALLOT",
    ]
    for key in date_keys:
        val = properties.get(key)
        if val and isinstance(val, str) and len(val) >= 8:
            # Try common date formats
            for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d", "%d.%m.%Y"):
                try:
                    return datetime.strptime(val.strip(), fmt).replace(
                        tzinfo=timezone.utc
                    )
                except ValueError:
                    continue
    return None


def _has_construction_evidence(properties: dict) -> bool | None:
    """Check if CSIDC properties indicate construction has started."""
    status = (
        properties.get("status_inf", "")
        or properties.get("status_from_csidc", "")
        or properties.get("status", "")
        or properties.get("allot_status", "")
        or ""
    ).lower()

    if not status:
        return None

    construction_keywords = [
        "operational",
        "constructed",
        "construction in progress",
        "running",
        "production",
        "under development",
        "building",
        "functional",
    ]
    no_construction_keywords = [
        "no construction",
        "not started",
        "vacant",
        "show cause",
        "cancelled",
        "unallotted",
    ]

    for kw in no_construction_keywords:
        if kw in status:
            return False
    for kw in construction_keywords:
        if kw in status:
            return True

    # If allotted but no construction keyword, unknown
    if "allotted" in status or "allot" in status:
        return None

    return None


def _generate_mock_allotment(
    area_name: str,
    plot_name: str,
    plot_area_sqm: float | None = None,
) -> dict:
    """Generate a single believable mock allotment record.

    Uses deterministic seeding so the same plot always gets the same mock data.
    """
    seed = _deterministic_seed(area_name, plot_name)
    rng = random.Random(seed)

    # 70% plots are allotted, 20% vacant, 10% delayed
    roll = rng.random()
    if roll < 0.70:
        status = rng.choice(_STATUSES_ACTIVE)
        allottee = rng.choice(_FIRM_NAMES)
        construction_started = True
    elif roll < 0.90:
        status = rng.choice(_STATUSES_VACANT)
        allottee = ""
        construction_started = False
    else:
        status = rng.choice(_STATUSES_DELAYED)
        allottee = rng.choice(_FIRM_NAMES)
        construction_started = False

    # Allotment date: between 1 and 6 years ago
    # Biased toward 2-4 years ago (most realistic for CSIDC areas)
    if status not in _STATUSES_VACANT:
        years_ago = rng.gauss(3.0, 1.2)
        years_ago = max(0.5, min(years_ago, 8.0))
        allotment_date = datetime.now(timezone.utc) - timedelta(
            days=int(years_ago * 365)
        )
        construction_deadline = allotment_date + timedelta(
            days=CONSTRUCTION_DEADLINE_YEARS * 365
        )
    else:
        allotment_date = None
        construction_deadline = None

    # Small realistic area variation if we don't have the real value
    if plot_area_sqm is None:
        plot_area_sqm = round(rng.uniform(200, 5000), 1)

    category = rng.choice(_CATEGORIES)

    return {
        "area_name": area_name,
        "plot_name": plot_name,
        "allottee": allottee,
        "allotment_date": allotment_date,
        "construction_deadline": construction_deadline,
        "plot_area_sqm": plot_area_sqm,
        "category": category,
        "status": status,
        "construction_started": construction_started,
        "data_source": "mock",
    }


async def get_allotment_records(
    db: AsyncSession,
    area_name: str,
    force_refresh: bool = False,
) -> list[AllotmentRecord]:
    """Get allotment records for an area.

    1. Check local DB for existing records.
    2. If none, try to extract from CSIDC reference plot properties.
    3. If still insufficient, generate believable mock data.
    4. Persist all records in the DB.

    Args:
        db: Database session.
        area_name: Name of the industrial area.
        force_refresh: If True, regenerate even if records exist.

    Returns:
        List of AllotmentRecord objects.
    """
    # Step 1: Check for existing records
    if not force_refresh:
        existing = await db.execute(
            select(AllotmentRecord).where(AllotmentRecord.area_name == area_name)
        )
        records = existing.scalars().all()
        if records:
            logger.info(
                f"Found {len(records)} existing allotment records for {area_name}"
            )
            return list(records)

    # Step 2: Load CSIDC reference plots
    ref_result = await db.execute(
        select(CsidcReferencePlot).where(CsidcReferencePlot.area_name == area_name)
    )
    ref_plots = ref_result.scalars().all()

    if not ref_plots:
        logger.warning(f"No CSIDC reference plots found for {area_name}")
        return []

    records = []
    csidc_count = 0
    mock_count = 0

    for ref_plot in ref_plots:
        props = ref_plot.properties or {}
        plot_name = ref_plot.plot_name or props.get("plotno_inf", f"Plot-{ref_plot.id}")

        # Try to extract real allotment data from CSIDC properties
        allotment_date = _parse_csidc_allotment_date(props)
        construction_started = _has_construction_evidence(props)

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
            or props.get("allot_status")
            or ""
        )

        area_val = (
            props.get("total_area")
            or props.get("area_sqm")
            or props.get("AREA_SQM")
            or props.get("shape_area")
            or props.get("Shape_Area")
            or None
        )
        plot_area_sqm = float(area_val) if area_val else None

        # If we have a real allotment date from CSIDC, use real data
        if allotment_date is not None:
            data_source = "csidc"
            construction_deadline = allotment_date + timedelta(
                days=CONSTRUCTION_DEADLINE_YEARS * 365
            )
            csidc_count += 1
        elif allottee and status:
            # We have some CSIDC data but no date — generate a plausible date
            # keeping the real allottee and status
            data_source = "mock"
            mock_data = _generate_mock_allotment(area_name, plot_name, plot_area_sqm)
            allotment_date = mock_data["allotment_date"]
            construction_deadline = mock_data["construction_deadline"]
            if construction_started is None:
                construction_started = mock_data["construction_started"]
            mock_count += 1
        else:
            # Fully mock
            data_source = "mock"
            mock_data = _generate_mock_allotment(area_name, plot_name, plot_area_sqm)
            allottee = mock_data["allottee"]
            allotment_date = mock_data["allotment_date"]
            construction_deadline = mock_data["construction_deadline"]
            status = mock_data["status"]
            construction_started = mock_data["construction_started"]
            if plot_area_sqm is None:
                plot_area_sqm = mock_data["plot_area_sqm"]
            mock_count += 1

        category = props.get("category_i") or props.get("plot_type") or "industrial"

        record = AllotmentRecord(
            area_name=area_name,
            plot_name=plot_name,
            allottee=allottee,
            allotment_date=allotment_date,
            construction_deadline=construction_deadline,
            plot_area_sqm=plot_area_sqm,
            category=category,
            status=status,
            data_source=data_source,
            properties_json=None,  # don't duplicate the full props
        )
        db.add(record)
        records.append(record)

    if records:
        await db.flush()

    logger.info(
        f"Allotment records for {area_name}: {len(records)} total "
        f"({csidc_count} from CSIDC, {mock_count} mock)"
    )
    return records
