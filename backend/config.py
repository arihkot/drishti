"""Application configuration."""

import os
from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    APP_NAME: str = "Drishti"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = True

    # Paths
    BASE_DIR: Path = Path(__file__).resolve().parent
    DATA_DIR: Path = BASE_DIR / "data"
    DB_PATH: Path = DATA_DIR / "drishti.db"
    TILES_DIR: Path = DATA_DIR / "tiles"
    MODELS_DIR: Path = DATA_DIR / "models"
    EXPORTS_DIR: Path = DATA_DIR / "exports"

    # Database
    DATABASE_URL: str = ""

    # CSIDC GeoServer
    CSIDC_API_URL: str = "https://cggis.cgstate.gov.in/giscg"
    CSIDC_WMS_URL: str = "https://cggis.cgstate.gov.in/giscg/wmscgcog"
    CSIDC_AUTH_TOKEN: str = "d01de439-448c-4b48-ac5b-5700ab0274b8"
    CSIDC_WORKSPACE: str = "CGCOG_DATABASE"

    # CSIDC Layer Names
    LAYER_INDUSTRIAL_PLOTS: str = "csidc_industrial_area_with_plots"
    LAYER_INDUSTRIAL_BOUNDARY: str = "csidc_industrial_area_outer_boundary"
    LAYER_OLD_INDUSTRIAL: str = "csidc_old_IA"
    LAYER_OLD_INDUSTRIAL_BOUNDARY: str = "csidc_old_IA_outer_b"
    LAYER_DIRECTORATE: str = "directoindustrialarea"
    LAYER_DIRECTORATE_BOUNDARY: str = "directoindustrialareaouterboundary"
    LAYER_DISTRICTS: str = "cg_district_boundary"
    LAYER_LANDBANK_VILLAGES: str = "csidc_land_bank_villages"
    LAYER_LANDBANK_CADASTRALS: str = "csidc_landbank_cadastrals__new"
    LAYER_AMENITIES: str = "csidc_industrialareaentities"
    LAYER_RIVERS: str = "csidc_rivers"
    LAYER_SUBSTATIONS: str = "csidc_substations"

    # Satellite Tiles
    ESRI_SATELLITE_URL: str = (
        "https://server.arcgisonline.com/ArcGIS/rest/services/"
        "World_Imagery/MapServer/tile/{z}/{y}/{x}"
    )
    DEFAULT_TILE_ZOOM: int = 18

    # SAM Model
    SAM_MODEL_TYPE: str = "vit_b"  # SAM base (smallest original SAM)
    SAM_CHECKPOINT: str = ""  # Auto-downloaded
    SAM_DEVICE: str = "mps"  # Apple Silicon GPU; MPS fallback handles unsupported ops

    # Detection
    MIN_POLYGON_AREA_SQM: float = 10.0
    SIMPLIFY_TOLERANCE: float = 3.0  # ~3.3m in degrees; smooths pixel staircase
    ENCROACHMENT_TOLERANCE_M: float = 2.0

    # Map defaults
    MAP_CENTER_LON: float = 82.0
    MAP_CENTER_LAT: float = 20.8
    MAP_DEFAULT_ZOOM: int = 7

    # Server
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    def model_post_init(self, __context):
        """Ensure directories exist and set computed fields."""
        self.DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.TILES_DIR.mkdir(parents=True, exist_ok=True)
        self.MODELS_DIR.mkdir(parents=True, exist_ok=True)
        self.EXPORTS_DIR.mkdir(parents=True, exist_ok=True)

        if not self.DATABASE_URL:
            self.DATABASE_URL = f"sqlite+aiosqlite:///{self.DB_PATH}"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
