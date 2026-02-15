# Drishti (दृष्टि)

**Automated Monitoring and Compliance System for Industrial Land Allotments**

Drishti is an AI-powered geospatial compliance platform built for the **Chhattisgarh State Industrial Development Corporation (CSIDC)**. It uses Meta's **Segment Anything Model (SAM)** to automatically detect land plot boundaries from high-resolution satellite imagery, compares them against official CSIDC GeoServer reference data, identifies deviations such as encroachments, unauthorized developments, boundary mismatches, and vacant plots, and generates comprehensive PDF compliance reports — all through an interactive web-based map interface.

---

## Demo

<img width="1466" height="852" alt="Screenshot 2026-02-14 at 11 48 42 AM" src="https://github.com/user-attachments/assets/d69cf919-bcd1-4026-a0d4-cc1b93532ff1" />
<img width="1469" height="851" alt="Screenshot 2026-02-14 at 11 33 16 AM" src="https://github.com/user-attachments/assets/13f2bf11-a324-40fa-9a65-a915595e956d" />
<img width="1448" height="834" alt="Screenshot 2026-02-14 at 7 15 45 PM" src="https://github.com/user-attachments/assets/64c3bd0e-7e8e-40f0-b600-91868805c59e" />
<img width="1070" height="853" alt="Screenshot 2026-02-14 at 11 35 13 AM" src="https://github.com/user-attachments/assets/9e6f11fb-1f89-4436-b486-7cc2e19c5b98" />
<img width="1466" height="851" alt="Screenshot 2026-02-14 at 11 34 14 AM" src="https://github.com/user-attachments/assets/7eca9732-3c05-4c78-9dfa-50ac1cc0cce0" />
<img width="1463" height="885" alt="Screenshot 2026-02-14 at 11 32 15 AM" src="https://github.com/user-attachments/assets/0bef585f-6c2c-47a1-aa9e-957e278a7b8e" />
<img width="1080" height="833" alt="Screenshot 2026-02-14 at 11 35 44 AM" src="https://github.com/user-attachments/assets/d79aedf3-b767-41a4-8d06-a6b3d91c4227" />
<img width="1450" height="830" alt="Screenshot 2026-02-14 at 7 00 39 PM" src="https://github.com/user-attachments/assets/c8d89180-4987-4473-b24a-edb75f0ee75e" />
<img width="1413" height="495" alt="Screenshot 2026-02-14 at 7 04 35 PM" src="https://github.com/user-attachments/assets/0bdc61fe-1162-4ecf-a2e7-aba9df2e9ff6" />


---
## Table of Contents



- [Key Features](#key-features)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Configuration](#configuration)
- [Usage](#usage)
- [API Reference](#api-reference)
- [Database Schema](#database-schema)
- [Detection Pipeline](#detection-pipeline)
- [Report Generation](#report-generation)
- [License](#license)

---

## Key Features

### AI-Powered Boundary Detection
- **SAM Auto-Detection** — Automatically segments satellite imagery into individual land plot polygons using Meta's Segment Anything Model (SAM `vit_b`).
- **CSIDC-Guided Detection** — After initial auto-detection, uses official CSIDC reference plot centroids as point prompts to detect any plots missed by the automatic pass.
- **Prompted Detection** — Supports manual point-click and bounding-box prompts for targeted detection of specific regions.
- **Apple Silicon GPU Acceleration** — Natively uses MPS (Metal Performance Shaders) on Apple Silicon Macs with automatic float64-to-float32 patching for unsupported ops.

### Compliance & Deviation Analysis
- Compares AI-detected plot boundaries against official CSIDC GeoServer records.
- Classifies deviations into five categories: **Encroachment**, **Boundary Mismatch**, **Vacant**, **Unauthorized Development**, and **Compliant**.
- Assigns severity levels (low, medium, high, critical) based on deviation magnitude.
- Calculates geodetic-accurate area and perimeter differences using the WGS84 ellipsoid.

### Interactive Map Interface
- **Satellite View** — ESRI World Imagery basemap with detected polygon overlays.
- **Schematic View** — Clean white-background view with category-styled polygons for print-ready visuals.
- **CSIDC Reference Overlay** — Toggle official CSIDC WMS layers (plot boundaries, outer boundaries, amenities, rivers, substations, land bank data) directly on the map.
- **Boundary Editing** — Modify detected polygon vertices interactively on the map with keyboard shortcuts (Escape to cancel, Ctrl+S to save). Changes trigger automatic geodetic recalculation of area and perimeter.

### Dashboard & Analytics
- **Main Dashboard** — Aggregate statistics across all 16 CSIDC industrial areas with charts and area-level compliance summaries.
- **Area Dashboard** — Drill-down per-area view with individual plot details, compliance karma scores, and payment tracking.

### Report Generation
- **PDF Reports** — Professional CSIDC-branded multi-page reports including: cover page, category breakdown with pie charts, satellite overlay maps, CSIDC reference overlay maps, combined comparison views, schematic maps, individual plot detail grids, full plot inventory tables, and deviation summaries.
- **GeoJSON Export** — Export detected plots and their metadata as standard GeoJSON for use in GIS tools.

### Smart Caching
- Satellite tiles cached as NumPy arrays (`.npy`) to avoid re-downloading.
- WMS tiles from CSIDC GeoServer cached in SQLite by SHA-256 content hash.
- CSIDC area boundaries and reference plot geometries cached in the local database.

---

## Tech Stack

### Backend

| Component | Technology |
|---|---|
| Web Framework | FastAPI + Uvicorn (async) |
| Database | SQLite via SQLAlchemy (async) + aiosqlite |
| Configuration | Pydantic Settings (`.env` support) |
| AI / ML | PyTorch, segment-geospatial (SAM), samgeo |
| Geospatial | Shapely, GeoPandas, PyProj, Rasterio, Mercantile |
| Image Processing | Pillow, OpenCV (headless), scikit-image, NumPy, SciPy |
| PDF Generation | ReportLab, Matplotlib |
| HTTP Client | httpx (async) |
| Python Version | 3.12+ |
| Package Manager | uv |

### Frontend

| Component | Technology |
|---|---|
| UI Framework | React 19 + TypeScript 5.9 |
| Build Tool | Vite 7 |
| Map Library | OpenLayers (ol) |
| State Management | Zustand |
| Styling | Tailwind CSS 4 |
| Icons | Lucide React |

---

## Project Structure

```
drishti/
├── main.py                          # Entry point — runs uvicorn server
├── pyproject.toml                   # Python dependencies and project metadata
├── uv.lock                         # uv lockfile
├── .python-version                  # Python 3.12
│
├── backend/
│   ├── __init__.py
│   ├── main.py                      # FastAPI app setup (CORS, lifespan, routers)
│   ├── config.py                    # All configuration via Pydantic Settings
│   ├── database.py                  # Async SQLAlchemy engine + session factory
│   ├── models.py                    # 6 SQLAlchemy ORM models
│   │
│   ├── routers/
│   │   ├── auth.py                  # Demo authentication endpoints
│   │   ├── areas.py                 # CSIDC area listing, boundaries, WMS proxy
│   │   ├── projects.py              # Full CRUD for projects and plots
│   │   ├── detection.py             # SAM auto-detect and prompt-detect
│   │   ├── comparison.py            # Deviation analysis between detected vs reference
│   │   └── export.py                # PDF and GeoJSON export
│   │
│   ├── services/
│   │   ├── sam_detector.py          # SAM model loading and inference
│   │   ├── tile_fetcher.py          # ESRI satellite tile fetching and stitching
│   │   ├── vectorizer.py            # Raster mask to polygon pipeline
│   │   ├── comparator.py            # Geometry comparison and deviation classification
│   │   ├── csidc_client.py          # CSIDC GeoServer WFS/WMS API client
│   │   └── pdf_generator.py         # Multi-page ReportLab PDF report generator
│   │
│   └── data/
│       ├── drishti.db               # SQLite database
│       ├── tiles/                   # Cached satellite imagery (.npy)
│       ├── models/                  # SAM model checkpoints (auto-downloaded)
│       └── exports/                 # Generated PDF reports
│
├── frontend/
│   ├── package.json
│   ├── vite.config.ts               # Dev server with API proxy to :8000
│   ├── tsconfig.json
│   ├── index.html
│   ├── public/
│   │   └── sample_survey_report.pdf
│   │
│   └── src/
│       ├── main.tsx                  # React entry point
│       ├── App.tsx                   # Root component (auth, routing)
│       ├── index.css                 # Tailwind CSS imports
│       ├── api/client.ts             # Typed API client for all backend endpoints
│       ├── types/index.ts            # TypeScript type definitions
│       ├── stores/useStore.ts        # Zustand global state store
│       ├── data/mockData.ts          # Mock dashboard data (16 CSIDC areas)
│       │
│       └── components/
│           ├── LoginPage.tsx         # Auth page with demo credential quick-fill
│           ├── Header.tsx            # Top bar with view toggles and controls
│           ├── Sidebar.tsx           # Area browser, plot list, compare, export
│           ├── MapView.tsx           # OpenLayers map with all interactions
│           ├── Dashboard.tsx         # Main dashboard with charts and stats
│           ├── AreaDashboard.tsx      # Per-area dashboard with plot details
│           └── Toast.tsx             # Toast notification component
```

---

## Prerequisites

- **Python** 3.12 or higher
- **Node.js** 18+ and **npm**
- **[uv](https://docs.astral.sh/uv/)** — Python package manager
- **(Optional)** Apple Silicon Mac for MPS GPU acceleration. CPU fallback is supported but significantly slower for SAM inference.

---

## Installation

### 1. Clone the repository

```bash
git clone <repository-url>
cd drishti
```

### 2. Install backend dependencies

```bash
uv sync
```

This will create a virtual environment and install all Python dependencies defined in `pyproject.toml`, including PyTorch, FastAPI, SAM, and all geospatial libraries.

### 3. Install frontend dependencies

```bash
cd frontend
npm install
cd ..
```

### 4. SAM model checkpoint

The SAM model checkpoint (`sam_vit_b`) is **automatically downloaded** on first use and cached in `backend/data/models/`. No manual download is required.

---

## Configuration

Configuration is managed via `backend/config.py` using Pydantic Settings. All values have sensible defaults and can be overridden using a `.env` file in the project root.

| Variable | Default | Description |
|---|---|---|
| `DEBUG` | `true` | Enable debug mode |
| `DATABASE_URL` | `sqlite+aiosqlite:///backend/data/drishti.db` | Database connection string |
| `CSIDC_API_URL` | `https://cggis.cgstate.gov.in/giscg` | CSIDC GeoServer base URL |
| `CSIDC_WMS_URL` | `https://cggis.cgstate.gov.in/giscg/wmscgcog` | CSIDC WMS endpoint |
| `CSIDC_AUTH_TOKEN` | *(set in config)* | Auth token for CSIDC GeoServer API |
| `SAM_MODEL_TYPE` | `vit_b` | SAM model variant (`vit_b`, `vit_l`, `vit_h`) |
| `SAM_DEVICE` | `mps` | PyTorch device (`mps`, `cuda`, `cpu`) |
| `MIN_POLYGON_AREA_SQM` | `50.0` | Minimum polygon area threshold in sq. meters |
| `SIMPLIFY_TOLERANCE` | `3.0` | Douglas-Peucker simplification tolerance (~3m) |
| `ENCROACHMENT_TOLERANCE_M` | `2.0` | Tolerance for encroachment detection in meters |
| `DEFAULT_TILE_ZOOM` | `18` | Satellite tile zoom level for detection |
| `HOST` | `0.0.0.0` | Server bind address |
| `PORT` | `8000` | Server port |

### CSIDC GeoServer Layers

The system integrates with 14 layers from the CSIDC GeoServer:

- `csidc_industrial_area_with_plots` — Industrial area plot boundaries
- `csidc_industrial_area_outer_boundary` — Industrial area outer boundaries
- `csidc_old_IA` / `csidc_old_IA_outer_b` — Legacy industrial area data
- `directoindustrialarea` / `directoindustrialareaouterboundary` — Directorate industrial areas
- `cg_district_boundary` — District boundaries
- `csidc_land_bank_villages` / `csidc_landbank_cadastrals__new` — Land bank data
- `csidc_industrialareaentities` — Amenities within industrial areas
- `csidc_rivers` — River features
- `csidc_substations` — Electrical substations

---

## Usage

### Starting the application

**Terminal 1 — Backend:**

```bash
python main.py
```

The FastAPI server starts on `http://localhost:8000` with auto-reload enabled.

**Terminal 2 — Frontend (development):**

```bash
cd frontend
npm run dev
```

The Vite dev server starts on `http://localhost:5173` with API requests proxied to the backend.

### Building for production

```bash
cd frontend
npm run build
```

The built assets are output to `frontend/dist/`.

### Demo credentials

The application ships with hardcoded demo accounts:

| Username | Password | Role |
|---|---|---|
| `admin` | `csidc2024` | Administrator |
| `inspector` | `inspect123` | Inspector |

### Workflow

1. **Login** — Authenticate with demo credentials.
2. **Select an area** — Browse the list of CSIDC industrial areas in the sidebar.
3. **Load boundary** — The system fetches the area boundary from CSIDC GeoServer.
4. **Create a project** — A detection project is created for the selected area.
5. **Run auto-detection** — SAM analyzes satellite imagery and detects all plot boundaries within the area.
6. **Review results** — Detected plots appear as interactive polygons on the map with area, perimeter, and category labels.
7. **Edit boundaries** — Click any polygon to modify its vertices directly on the map.
8. **Run comparison** — Compare detected plots against CSIDC reference data to identify deviations.
9. **Export** — Generate a PDF compliance report or export results as GeoJSON.

---

## API Reference

All endpoints are prefixed with `/api`.

### Authentication

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/auth/login` | Login with username and password |
| `GET` | `/api/auth/me` | Get current user info |

### Areas

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/areas` | List all CSIDC industrial areas |
| `GET` | `/api/areas/{name}/boundary` | Get area boundary GeoJSON |
| `GET` | `/api/areas/{name}/reference-plots` | Get CSIDC reference plot geometries |
| `GET` | `/api/areas/wms-proxy` | Proxy WMS tile requests to CSIDC GeoServer |
| `GET` | `/api/areas/wms-config` | Get WMS layer configuration |
| `GET` | `/api/areas/districts` | List all districts |

### Projects

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/projects` | List all projects |
| `POST` | `/api/projects` | Create a new project |
| `GET` | `/api/projects/{id}` | Get project details with plots |
| `PUT` | `/api/projects/{id}` | Update project |
| `DELETE` | `/api/projects/{id}` | Delete project and all associated data |
| `PUT` | `/api/projects/{id}/plots/{plot_id}` | Update a plot (geometry, label, category) |
| `DELETE` | `/api/projects/{id}/plots/{plot_id}` | Delete a plot |

### Detection

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/detect/auto` | Run SAM auto-detection on project area |
| `POST` | `/api/detect/prompt` | Run prompted detection (point/box prompts) |
| `GET` | `/api/detect/model-status` | Check SAM model loading status |
| `POST` | `/api/detect/preload-model` | Pre-load SAM model into memory |
| `POST` | `/api/detect/reload-model` | Reload SAM model |

### Comparison

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/compare/{project_id}` | Run deviation analysis |
| `GET` | `/api/compare/{project_id}` | Get comparison results |

### Export

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/export/{project_id}/pdf` | Generate PDF compliance report |
| `POST` | `/api/export/{project_id}/geojson` | Export as GeoJSON |

### System

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/health` | Health check |

---

## Database Schema

The application uses SQLite with 6 tables:

### `projects`
Stores detection projects, each scoped to a CSIDC industrial area.

| Column | Type | Description |
|---|---|---|
| `id` | Integer (PK) | Auto-increment primary key |
| `name` | String | Project name |
| `area_name` | String | CSIDC industrial area name |
| `area_category` | String | `industrial`, `old_industrial`, or `directorate` |
| `description` | Text | Optional description |
| `bbox_json` | Text | Bounding box as JSON `[minLon, minLat, maxLon, maxLat]` |
| `center_lon` / `center_lat` | Float | Center coordinates |
| `zoom` | Integer | Map zoom level (default 18) |
| `created_at` / `updated_at` | DateTime | Timestamps |

### `plots`
Stores individual detected plot polygons, each belonging to a project.

| Column | Type | Description |
|---|---|---|
| `id` | Integer (PK) | Auto-increment primary key |
| `project_id` | Integer (FK) | Reference to parent project |
| `label` | String | Display label (e.g., "Plot 1", "Road 2") |
| `category` | String | `parcel`, `road`, `infrastructure`, `other` |
| `geometry_json` | Text | GeoJSON geometry |
| `area_sqm` / `area_sqft` | Float | Geodetic area |
| `perimeter_m` | Float | Geodetic perimeter |
| `color` | String | Hex color code |
| `confidence` | Float | SAM confidence score |

### `comparisons`
Stores deviation analysis results.

| Column | Type | Description |
|---|---|---|
| `id` | Integer (PK) | Auto-increment primary key |
| `project_id` | Integer (FK) | Reference to project |
| `plot_id` | Integer (FK) | Reference to detected plot |
| `deviation_type` | String | `ENCROACHMENT`, `BOUNDARY_MISMATCH`, `VACANT`, `UNAUTHORIZED_DEVELOPMENT`, `COMPLIANT` |
| `severity` | String | `low`, `medium`, `high`, `critical` |
| `deviation_area_sqm` | Float | Area of the deviation region |
| `deviation_geometry_json` | Text | GeoJSON of the deviation area |
| `description` | Text | Human-readable deviation description |

### `basemap_cache`
Caches CSIDC area boundary geometries fetched from GeoServer.

### `csidc_reference_plots`
Caches individual CSIDC reference plot geometries per area for offline comparison.

### `wms_tile_cache`
Caches WMS tile images from CSIDC GeoServer, keyed by SHA-256 hash of the request parameters.

---

## Detection Pipeline

The detection pipeline is a multi-phase process that combines AI segmentation with geospatial post-processing:

### Phase 1 — Data Preparation
1. **CSIDC preload** — Fetch the area's outer boundary and individual reference plots from CSIDC GeoServer (with multi-strategy fallback: exact name, fuzzy ILIKE, BBOX spatial filter, legacy layer lookup — 6 strategies total).
2. **Satellite tile fetch** — Download ESRI World Imagery tiles at zoom 18 covering the project bounding box, stitch them into a single composite image, and cache the result as a NumPy array.

### Phase 2 — SAM Auto-Detection
3. **SAM inference** — Run the Segment Anything Model on the satellite composite to produce a segmentation mask of all detected regions.
4. **CSIDC-guided detection** — For each CSIDC reference plot whose centroid was not covered by an auto-detected polygon, run a prompted SAM detection using the centroid as a point prompt. This catches plots that SAM's automatic mode may have missed.

### Phase 3 — Vectorization
5. **Mask-to-polygon conversion** — Convert the raster segmentation mask into vector polygons.
6. **Polygon smoothing** — Apply a multi-step pipeline:
   - Morphological buffer open (expand then contract to fill small holes)
   - Chaikin corner-cutting (smooth jagged pixel-staircase edges)
   - Douglas-Peucker simplification (reduce vertex count while preserving shape)
7. **Classification** — Classify each polygon as `plot`, `road`, or `boundary` based on satellite pixel color analysis and shape heuristics.

### Phase 4 — Post-Processing
8. **Merge overlapping** — Combine polygons that overlap above a threshold.
9. **Merge small nearby** — Absorb small polygons into adjacent larger ones.
10. **Noise filtering** — Remove polygons below the minimum area threshold (default 50 sqm).
11. **Remove contained** — Eliminate polygons that are entirely within another polygon.
12. **Clip to boundary** — Clip all polygons to the CSIDC area outer boundary.
13. **Renumber labels** — Assign sequential labels ("Plot 1", "Plot 2", "Road 1", etc.).

### Phase 5 — Geodetic Measurement
14. **Area & perimeter calculation** — Compute geodetically-accurate area (sqm and sqft) and perimeter (m) for each polygon using PyProj with the WGS84 ellipsoid.

---

## Report Generation

The PDF report generator produces comprehensive CSIDC-branded compliance documents using ReportLab and Matplotlib. Each report includes:

1. **Cover Page** — Project name, area name, generation date, CSIDC branding.
2. **Summary Statistics** — Total plots, total area, category breakdown.
3. **Category Breakdown** — Pie chart showing distribution of plots by category.
4. **Satellite Map** — Full-area satellite image with detected polygon overlays.
5. **CSIDC Reference Map** — Satellite image with official CSIDC reference plot overlays.
6. **Combined Comparison Map** — Satellite image with both detected and reference overlays for visual comparison.
7. **Schematic Map** — Clean vector map with category-colored polygons.
8. **Individual Plot Details** — Grid of per-plot detail cards with geometry thumbnails.
9. **Plot Inventory Table** — Tabular listing of all plots with area, perimeter, and category.
10. **Deviation Summary** — Details of all detected compliance deviations with severity and area.

---

## License

This project is proprietary software developed for CSIDC (Chhattisgarh State Industrial Development Corporation).
