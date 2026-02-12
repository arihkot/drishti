"""CSIDC GeoServer API client for fetching boundary data."""

import logging
from typing import Any
from urllib.parse import urlencode

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

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def fetch_layer_features(
        self, layer_name: str, filter_expr: str | None = None
    ) -> dict[str, Any]:
        """Fetch GeoJSON features from CSIDC POST API for a layer."""
        payload: dict[str, Any] = {"layerName": layer_name}
        if filter_expr:
            payload["filter"] = filter_expr

        url = f"{self.api_url}/block" if filter_expr else self.api_url

        async with httpx.AsyncClient(timeout=TIMEOUT, verify=False) as client:
            resp = await client.post(url, json=payload, headers=self.headers)
            resp.raise_for_status()
            data = resp.json()
            return data

    async def _wfs_get_features(
        self,
        layer_name: str,
        cql_filter: str | None = None,
        bbox: list[float] | None = None,
        max_features: int | None = None,
    ) -> list[dict[str, Any]]:
        """Fetch GeoJSON features via WFS GetFeature.

        This is much more reliable than the custom POST API for filtered
        queries because it supports standard OGC CQL and BBOX filters.
        """
        params: dict[str, str] = {
            "service": "WFS",
            "version": "1.0.0",
            "request": "GetFeature",
            "typeName": f"{settings.CSIDC_WORKSPACE}:{layer_name}",
            "outputFormat": "application/json",
        }
        if cql_filter:
            params["CQL_FILTER"] = cql_filter
        if bbox:
            params["BBOX"] = ",".join(str(b) for b in bbox)
        if max_features:
            params["maxFeatures"] = str(max_features)

        async with httpx.AsyncClient(timeout=TIMEOUT, verify=False) as client:
            resp = await client.get(self.wms_url, params=params)
            resp.raise_for_status()
            data = resp.json()
            return self._extract_features(data)

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
        """Parse raw GeoJSON features into plot dicts."""
        plots = []
        for feature in features:
            props = feature.get("properties", {})
            geom = feature.get("geometry", {})
            if not geom or not geom.get("coordinates"):
                continue
            plot_name = (
                props.get("plotno_inf")
                or props.get("PLOT_NO")
                or props.get("plot_no")
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

    @staticmethod
    def _bbox_from_geometry(geometry: dict) -> list[float] | None:
        """Extract [minLon, minLat, maxLon, maxLat] from a GeoJSON geometry."""
        coords = geometry.get("coordinates", [])
        if not coords:
            return None

        all_points: list[list[float]] = []

        def _flatten(c: Any) -> None:
            if isinstance(c, (list, tuple)):
                if len(c) >= 2 and isinstance(c[0], (int, float)):
                    all_points.append([float(c[0]), float(c[1])])
                else:
                    for item in c:
                        _flatten(item)

        _flatten(coords)
        if not all_points:
            return None

        lons = [p[0] for p in all_points]
        lats = [p[1] for p in all_points]
        return [min(lons), min(lats), max(lons), max(lats)]

    # ------------------------------------------------------------------
    # Industrial areas (boundaries)
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # Individual plot fetching — multi-strategy
    # ------------------------------------------------------------------

    async def get_individual_plots(
        self,
        area_name: str,
        boundary_geometry: dict | None = None,
    ) -> list[dict[str, Any]]:
        """Fetch individual plot polygons for a specific industrial area.

        Uses a multi-strategy approach because boundary area names often
        do not match the plot layer's area name column:

        1. WFS exact name filter (``industrial = 'NAME'``)
        2. WFS case-insensitive partial name filter (ILIKE)
        3. WFS BBOX spatial filter using the area's boundary geometry
        4. Repeat strategies 1-3 on the legacy ``cg_industrial_area_with_plot_info`` layer

        ``boundary_geometry`` is the GeoJSON geometry of the area's outer
        boundary. If provided, it enables the BBOX-based spatial fallback.
        """
        # Strategy 1: WFS exact name filter on primary layer
        plots = await self._try_wfs_name_filter(
            settings.LAYER_INDUSTRIAL_PLOTS,
            area_name,
            name_property="industrial",
        )
        if plots:
            logger.info(
                f"[CSIDC] Strategy 1 (exact name WFS): {len(plots)} plots for {area_name}"
            )
            return plots

        # Strategy 2: WFS fuzzy name filter on primary layer
        plots = await self._try_wfs_fuzzy_filter(
            settings.LAYER_INDUSTRIAL_PLOTS,
            area_name,
            name_property="industrial",
        )
        if plots:
            logger.info(
                f"[CSIDC] Strategy 2 (fuzzy name WFS): {len(plots)} plots for {area_name}"
            )
            return plots

        # Strategy 3: WFS BBOX spatial filter on primary layer
        if boundary_geometry:
            plots = await self._try_wfs_bbox_filter(
                settings.LAYER_INDUSTRIAL_PLOTS,
                boundary_geometry,
                area_name,
            )
            if plots:
                logger.info(
                    f"[CSIDC] Strategy 3 (BBOX spatial WFS): {len(plots)} plots for {area_name}"
                )
                return plots

        # Strategy 4: WFS exact name on legacy layer
        plots = await self._try_wfs_name_filter(
            settings.LAYER_INDUSTRIAL_PLOTS_OLD,
            area_name,
            name_property="INDUSTRIAL",
        )
        if plots:
            logger.info(
                f"[CSIDC] Strategy 4 (exact name legacy WFS): {len(plots)} plots for {area_name}"
            )
            return plots

        # Strategy 5: WFS fuzzy name on legacy layer
        plots = await self._try_wfs_fuzzy_filter(
            settings.LAYER_INDUSTRIAL_PLOTS_OLD,
            area_name,
            name_property="INDUSTRIAL",
        )
        if plots:
            logger.info(
                f"[CSIDC] Strategy 5 (fuzzy name legacy WFS): {len(plots)} plots for {area_name}"
            )
            return plots

        # Strategy 6: WFS BBOX spatial filter on legacy layer
        if boundary_geometry:
            plots = await self._try_wfs_bbox_filter(
                settings.LAYER_INDUSTRIAL_PLOTS_OLD,
                boundary_geometry,
                area_name,
            )
            if plots:
                logger.info(
                    f"[CSIDC] Strategy 6 (BBOX spatial legacy WFS): {len(plots)} plots for {area_name}"
                )
                return plots

        logger.warning(
            f"[CSIDC] No plot data found for {area_name} across all strategies"
        )
        return []

    async def _try_wfs_name_filter(
        self, layer: str, area_name: str, name_property: str
    ) -> list[dict[str, Any]]:
        """Strategy: WFS with exact CQL name filter."""
        try:
            # Escape single quotes in name
            safe_name = area_name.replace("'", "''")
            cql = f"{name_property}='{safe_name}'"
            features = await self._wfs_get_features(layer, cql_filter=cql)
            if features:
                return self._parse_plot_features(features, area_name)
        except Exception as e:
            logger.debug(f"WFS exact name filter failed for {layer}: {e}")
        return []

    async def _try_wfs_fuzzy_filter(
        self, layer: str, area_name: str, name_property: str
    ) -> list[dict[str, Any]]:
        """Strategy: WFS with case-insensitive partial name match (ILIKE).

        Tries multiple patterns:
        - The full name as a substring: ``ILIKE '%NAME%'``
        - Each word (3+ chars) of the name: ``ILIKE '%WORD%'``
        """
        try:
            safe_name = area_name.replace("'", "''")

            # Try full name as substring (case-insensitive)
            cql = f"{name_property} ILIKE '%{safe_name}%'"
            features = await self._wfs_get_features(layer, cql_filter=cql)
            if features:
                return self._parse_plot_features(features, area_name)

            # Try with the name as a prefix (area might have extra suffixes in data)
            cql = f"{name_property} ILIKE '{safe_name}%'"
            features = await self._wfs_get_features(layer, cql_filter=cql)
            if features:
                return self._parse_plot_features(features, area_name)

            # Try matching significant words from the area name
            # e.g. "METAL PARK PHASE II SECTOR A" -> try "METAL PARK PHASE II"
            words = [w for w in area_name.split() if len(w) >= 3]
            if len(words) >= 2:
                # Try progressively shorter combinations of words
                for end in range(len(words), 1, -1):
                    partial = " ".join(words[:end])
                    safe_partial = partial.replace("'", "''")
                    cql = f"{name_property} ILIKE '%{safe_partial}%'"
                    features = await self._wfs_get_features(layer, cql_filter=cql)
                    if features:
                        return self._parse_plot_features(features, area_name)

        except Exception as e:
            logger.debug(f"WFS fuzzy filter failed for {layer}: {e}")
        return []

    async def _try_wfs_bbox_filter(
        self, layer: str, boundary_geometry: dict, area_name: str
    ) -> list[dict[str, Any]]:
        """Strategy: WFS with BBOX spatial filter from boundary geometry.

        Fetches all features intersecting the area's bounding box, then
        filters client-side using shapely to keep only features that
        actually intersect the boundary polygon (not just the bbox).
        """
        try:
            bbox = self._bbox_from_geometry(boundary_geometry)
            if not bbox:
                return []

            features = await self._wfs_get_features(layer, bbox=bbox)
            if not features:
                return []

            # Spatial intersection filter using shapely
            try:
                from shapely.geometry import shape as shapely_shape

                boundary_shape = shapely_shape(boundary_geometry)
                if not boundary_shape.is_valid:
                    boundary_shape = boundary_shape.buffer(0)

                filtered = []
                for f in features:
                    geom = f.get("geometry")
                    if not geom:
                        continue
                    try:
                        feat_shape = shapely_shape(geom)
                        if not feat_shape.is_valid:
                            feat_shape = feat_shape.buffer(0)
                        # Keep if at least 10% of the plot intersects the boundary
                        intersection = boundary_shape.intersection(feat_shape)
                        if (
                            feat_shape.area > 0
                            and intersection.area / feat_shape.area > 0.1
                        ):
                            filtered.append(f)
                    except Exception:
                        # If shapely fails for a feature, include it anyway
                        filtered.append(f)

                logger.info(
                    f"[CSIDC] BBOX returned {len(features)} features, "
                    f"spatial filter kept {len(filtered)} for {area_name}"
                )
                features = filtered
            except ImportError:
                logger.warning("shapely not available, using all BBOX features")

            return self._parse_plot_features(features, area_name)

        except Exception as e:
            logger.debug(f"WFS BBOX filter failed for {layer}: {e}")
        return []

    # ------------------------------------------------------------------
    # Other endpoints
    # ------------------------------------------------------------------

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
