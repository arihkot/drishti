"""SQLAlchemy database models."""

import json
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from backend.database import Base


def utcnow():
    return datetime.now(timezone.utc)


class Project(Base):
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    area_name = Column(String(255), nullable=True)
    area_category = Column(
        String(50), nullable=True
    )  # industrial, old_industrial, directorate
    description = Column(Text, nullable=True)
    bbox_json = Column(Text, nullable=True)  # JSON [minLon, minLat, maxLon, maxLat]
    center_lon = Column(Float, nullable=True)
    center_lat = Column(Float, nullable=True)
    zoom = Column(Integer, default=18)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    plots = relationship("Plot", back_populates="project", cascade="all, delete-orphan")
    comparisons = relationship(
        "Comparison", back_populates="project", cascade="all, delete-orphan"
    )

    @property
    def bbox(self):
        if self.bbox_json:
            return json.loads(self.bbox_json)
        return None

    @bbox.setter
    def bbox(self, value):
        self.bbox_json = json.dumps(value) if value else None


class Plot(Base):
    __tablename__ = "plots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    label = Column(String(255), nullable=False)  # "Plot 1", "Road 1", etc.
    category = Column(
        String(50), default="parcel"
    )  # parcel, road, infrastructure, other
    geometry_json = Column(Text, nullable=False)  # GeoJSON geometry
    area_sqm = Column(Float, nullable=True)
    area_sqft = Column(Float, nullable=True)
    perimeter_m = Column(Float, nullable=True)
    color = Column(String(7), default="#FF0000")  # hex color
    is_active = Column(Boolean, default=True)
    confidence = Column(Float, nullable=True)  # SAM confidence score
    properties_json = Column(Text, nullable=True)  # additional properties as JSON
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    project = relationship("Project", back_populates="plots")

    @property
    def geometry(self):
        if self.geometry_json:
            return json.loads(self.geometry_json)
        return None

    @geometry.setter
    def geometry(self, value):
        self.geometry_json = json.dumps(value) if value else None

    @property
    def properties(self):
        if self.properties_json:
            return json.loads(self.properties_json)
        return {}

    @properties.setter
    def properties(self, value):
        self.properties_json = json.dumps(value) if value else None


class BasemapCache(Base):
    __tablename__ = "basemap_cache"

    id = Column(Integer, primary_key=True, autoincrement=True)
    layer_name = Column(String(255), nullable=False)
    area_name = Column(String(255), nullable=True)
    geometry_json = Column(Text, nullable=False)
    properties_json = Column(Text, nullable=True)
    fetched_at = Column(DateTime, default=utcnow)

    @property
    def geometry(self):
        if self.geometry_json:
            return json.loads(self.geometry_json)
        return None

    @property
    def properties(self):
        if self.properties_json:
            return json.loads(self.properties_json)
        return {}


class Comparison(Base):
    __tablename__ = "comparisons"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    plot_id = Column(Integer, ForeignKey("plots.id"), nullable=True)
    basemap_feature_id = Column(Integer, ForeignKey("basemap_cache.id"), nullable=True)
    deviation_type = Column(String(50), nullable=False)
    # ENCROACHMENT, UNAUTHORIZED_DEVELOPMENT, VACANT, BOUNDARY_MISMATCH, COMPLIANT
    severity = Column(String(20), default="low")  # low, medium, high, critical
    deviation_area_sqm = Column(Float, nullable=True)
    deviation_geometry_json = Column(Text, nullable=True)  # GeoJSON of deviation area
    details_json = Column(Text, nullable=True)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utcnow)

    project = relationship("Project", back_populates="comparisons")

    @property
    def deviation_geometry(self):
        if self.deviation_geometry_json:
            return json.loads(self.deviation_geometry_json)
        return None

    @property
    def details(self):
        if self.details_json:
            return json.loads(self.details_json)
        return {}


class SatelliteCache(Base):
    __tablename__ = "satellite_cache"

    id = Column(Integer, primary_key=True, autoincrement=True)
    bbox_json = Column(Text, nullable=False)
    zoom = Column(Integer, nullable=False)
    image_path = Column(String(512), nullable=False)
    width = Column(Integer, nullable=True)
    height = Column(Integer, nullable=True)
    fetched_at = Column(DateTime, default=utcnow)


class CsidcReferencePlot(Base):
    """Cached individual plot features from CSIDC GeoServer per area."""

    __tablename__ = "csidc_reference_plots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    area_name = Column(String(255), nullable=False, index=True)
    plot_name = Column(String(255), nullable=True)
    geometry_json = Column(Text, nullable=False)
    properties_json = Column(Text, nullable=True)
    fetched_at = Column(DateTime, default=utcnow)

    @property
    def geometry(self):
        if self.geometry_json:
            return json.loads(self.geometry_json)
        return None

    @property
    def properties(self):
        if self.properties_json:
            return json.loads(self.properties_json)
        return {}
