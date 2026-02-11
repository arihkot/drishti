"""CSIDC GeoServer API client for fetching boundary data."""

import logging
from typing import Any

import httpx

from backend.config import settings

logger = logging.getLogger(__name__)

# Timeout for external requests
TIMEOUT = httpx.Timeout(30.0, connect=10.0)


class CSIDCClient:
    """Client for CSIDC GeoServer API."""

    def __init__(self):
        self.api_url = settings.CSIDC_API_URL
        self.wms_url = settings.CSIDC_WMS_URL
        self.headers = {
            "Content-Type": "application/json",
            "Authorization": settings.CSIDC_AUTH_TOKEN,
        }

    async def fetch_layer_features(
        self, layer_name: str, filter_expr: str | None = None
    ) -> dict[str, Any]:
        """Fetch GeoJSON features from CSIDC API for a layer."""
        payload: dict[str, Any] = {"layerName": layer_name}
        if filter_expr:
            payload["filter"] = filter_expr

        url = f"{self.api_url}/block" if filter_expr else self.api_url

        async with httpx.AsyncClient(timeout=TIMEOUT, verify=False) as client:
            resp = await client.post(url, json=payload, headers=self.headers)
            resp.raise_for_status()
            data = resp.json()
            return data

    async def get_industrial_areas(self) -> list[dict[str, Any]]:
        """Fetch list of all industrial areas with boundaries."""
        data = await self.fetch_layer_features(settings.LAYER_INDUSTRIAL_BOUNDARY)
        areas = []
        features = self._extract_features(data)

        for feature in features:
            props = feature.get("properties", {})
            geom = feature.get("geometry", {})
            name = (
                props.get("industri_1")
                or props.get("name")
                or props.get("ia_name", "Unknown")
            )
            areas.append(
                {
                    "name": name,
                    "category": "industrial",
                    "properties": props,
                    "geometry": geom,
                }
            )
        return areas

    async def get_old_industrial_areas(self) -> list[dict[str, Any]]:
        """Fetch old industrial areas."""
        data = await self.fetch_layer_features(settings.LAYER_OLD_INDUSTRIAL_BOUNDARY)
        areas = []
        features = self._extract_features(data)

        for feature in features:
            props = feature.get("properties", {})
            geom = feature.get("geometry", {})
            name = props.get("industrial") or props.get("name", "Unknown")
            areas.append(
                {
                    "name": name,
                    "category": "old_industrial",
                    "properties": props,
                    "geometry": geom,
                }
            )
        return areas

    async def get_directorate_areas(self) -> list[dict[str, Any]]:
        """Fetch directorate industrial areas."""
        data = await self.fetch_layer_features(settings.LAYER_DIRECTORATE_BOUNDARY)
        areas = []
        features = self._extract_features(data)

        for feature in features:
            props = feature.get("properties", {})
            geom = feature.get("geometry", {})
            name = props.get("name") or props.get("directorate", "Unknown")
            areas.append(
                {
                    "name": name,
                    "category": "directorate",
                    "properties": props,
                    "geometry": geom,
                }
            )
        return areas

    async def get_individual_plots(self, area_name: str) -> list[dict[str, Any]]:
        """Fetch individual plot polygons for a specific industrial area.

        Tries filtering by ia_name first. If that returns no results,
        fetches all features and filters client-side.
        """
        plots = []

        # Try server-side filter first
        try:
            data = await self.fetch_layer_features(
                settings.LAYER_INDUSTRIAL_PLOTS,
                filter_expr=f"ia_name='{area_name}'",
            )
            features = self._extract_features(data)
            if features:
                plots = self._parse_plot_features(features, area_name)
                if plots:
                    return plots
        except Exception as e:
            logger.warning(f"Server-side plot filter failed: {e}")

        # Fallback: fetch all and filter client-side
        try:
            data = await self.fetch_layer_features(settings.LAYER_INDUSTRIAL_PLOTS)
            features = self._extract_features(data)
            for feature in features:
                props = feature.get("properties", {})
                feat_area_name = (
                    props.get("ia_name")
                    or props.get("industri_1")
                    or props.get("name", "")
                )
                if feat_area_name == area_name:
                    geom = feature.get("geometry", {})
                    plot_name = (
                        props.get("plot_no")
                        or props.get("plot_name")
                        or props.get("kh_no")
                        or f"Plot-{len(plots) + 1}"
                    )
                    plots.append(
                        {
                            "name": str(plot_name),
                            "area_name": area_name,
                            "properties": props,
                            "geometry": geom,
                        }
                    )
        except Exception as e:
            logger.warning(f"Failed to fetch all plot features: {e}")

        return plots

    def _extract_features(self, data: Any) -> list:
        """Extract features list from API response."""
        if isinstance(data, dict) and "features" in data:
            return data["features"]
        elif isinstance(data, list):
            return data
        return []

    def _parse_plot_features(
        self, features: list, area_name: str
    ) -> list[dict[str, Any]]:
        """Parse features into plot dicts."""
        plots = []
        for feature in features:
            props = feature.get("properties", {})
            geom = feature.get("geometry", {})
            plot_name = (
                props.get("plot_no")
                or props.get("plot_name")
                or props.get("kh_no")
                or f"Plot-{len(plots) + 1}"
            )
            plots.append(
                {
                    "name": str(plot_name),
                    "area_name": area_name,
                    "properties": props,
                    "geometry": geom,
                }
            )
        return plots

    async def get_districts(self) -> list[dict[str, Any]]:
        """Fetch district boundaries."""
        data = await self.fetch_layer_features(settings.LAYER_DISTRICTS)
        districts = []
        features = self._extract_features(data)

        for feature in features:
            props = feature.get("properties", {})
            geom = feature.get("geometry", {})
            districts.append(
                {
                    "name": props.get("dist_e", "Unknown"),
                    "code": props.get("dist_cod", ""),
                    "geometry": geom,
                }
            )
        return districts

    async def get_plot_info(
        self,
        bbox: list[float],
        width: int = 256,
        height: int = 256,
        x: int = 128,
        y: int = 128,
    ) -> dict[str, Any] | None:
        """Get feature info for a clicked point via WMS GetFeatureInfo."""
        params = {
            "service": "WMS",
            "version": "1.1.1",
            "request": "GetFeatureInfo",
            "LAYERS": f"{settings.CSIDC_WORKSPACE}:{settings.LAYER_INDUSTRIAL_PLOTS}",
            "QUERY_LAYERS": f"{settings.CSIDC_WORKSPACE}:{settings.LAYER_INDUSTRIAL_PLOTS}",
            "INFO_FORMAT": "application/json",
            "SRS": "EPSG:4326",
            "WIDTH": width,
            "HEIGHT": height,
            "X": x,
            "Y": y,
            "BBOX": ",".join(str(b) for b in bbox),
        }
        async with httpx.AsyncClient(timeout=TIMEOUT, verify=False) as client:
            resp = await client.get(self.wms_url, params=params)
            resp.raise_for_status()
            data = resp.json()
            if data.get("features"):
                return data["features"][0]
        return None

    def get_wms_tile_url(self, layer_name: str) -> str:
        """Get WMS tile URL pattern for a layer (for frontend use)."""
        return (
            f"{self.wms_url}?"
            f"service=WMS&version=1.1.1&request=GetMap"
            f"&LAYERS={settings.CSIDC_WORKSPACE}:{layer_name}"
            f"&SRS=EPSG:4326&FORMAT=image/png&TRANSPARENT=true"
            f"&WIDTH=256&HEIGHT=256&BBOX={{bbox}}"
        )


csidc_client = CSIDCClient()
