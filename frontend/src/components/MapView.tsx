import React, { useRef, useEffect, useCallback } from "react";
import Map from "ol/Map";
import View from "ol/View";
import TileLayer from "ol/layer/Tile";
import XYZ from "ol/source/XYZ";
import ImageLayer from "ol/layer/Image";
import ImageWMS from "ol/source/ImageWMS";
import VectorLayer from "ol/layer/Vector";
import VectorSource from "ol/source/Vector";
import GeoJSON from "ol/format/GeoJSON";
import { Style, Fill, Stroke, Text as OlText } from "ol/style";
import { useGeographic } from "ol/proj";
import Feature from "ol/Feature";
import type { MapBrowserEvent } from "ol";
import type { Geometry } from "ol/geom";

import { useStore } from "../stores/useStore";
import { fetchAreaBoundary } from "../api/client";
import type { PlotData } from "../types";

// Register geographic (EPSG:4326) coordinate system globally
useGeographic();

// ---------------------------------------------------------------------------
// Deviation type → color mapping
// ---------------------------------------------------------------------------
const DEVIATION_COLORS: Record<string, string> = {
  ENCROACHMENT: "#ef4444",
  BOUNDARY_MISMATCH: "#f97316",
  VACANT: "#eab308",
  COMPLIANT: "#22c55e",
  UNAUTHORIZED_DEVELOPMENT: "#dc2626",
};

// ---------------------------------------------------------------------------
// Schematic category → style mapping
// ---------------------------------------------------------------------------
function schematicStyle(category: string, label: string): Style {
  const base: Record<string, { fill: string; stroke: string }> = {
    plot: { fill: "rgba(239,68,68,0.15)", stroke: "#ef4444" },
    road: { fill: "rgba(100,116,139,0.10)", stroke: "#64748b" },
    vegetation: { fill: "rgba(34,197,94,0.15)", stroke: "#22c55e" },
    open_land: { fill: "rgba(217,119,6,0.15)", stroke: "#d97706" },
    water: { fill: "rgba(59,130,246,0.20)", stroke: "#3b82f6" },
    building: { fill: "rgba(168,85,247,0.15)", stroke: "#a855f7" },
    infrastructure: { fill: "rgba(245,158,11,0.15)", stroke: "#f59e0b" },
    other: { fill: "rgba(156,163,175,0.15)", stroke: "#9ca3af" },
    // Legacy support
    parcel: { fill: "rgba(239,68,68,0.15)", stroke: "#ef4444" },
  };
  const cfg = base[category] ?? base.other;

  return new Style({
    fill: new Fill({ color: cfg.fill }),
    stroke: new Stroke({
      color: cfg.stroke,
      width: 2,
      lineDash: category === "plot" || category === "parcel" ? [8, 4] : undefined,
    }),
    text: new OlText({
      text: label,
      font: "12px sans-serif",
      fill: new Fill({ color: "#1f2937" }),
      stroke: new Stroke({ color: "#ffffff", width: 3 }),
      overflow: true,
    }),
  });
}

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------
interface MapViewProps {
  promptMode: boolean;
  onMapReady?: (map: Map) => void;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------
const MapView: React.FC<MapViewProps> = ({ promptMode, onMapReady }) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<Map | null>(null);

  // Layer refs so we can update them without recreating the map
  const baseTileRef = useRef<TileLayer<XYZ> | null>(null);
  const wmsLayerRef = useRef<ImageLayer<ImageWMS> | null>(null);
  const csidcPlotsLayerRef = useRef<ImageLayer<ImageWMS> | null>(null);
  const boundaryLayerRef = useRef<VectorLayer<VectorSource<Feature<Geometry>>> | null>(null);
  const plotLayerRef = useRef<VectorLayer<VectorSource<Feature<Geometry>>> | null>(null);
  const deviationLayerRef = useRef<VectorLayer<VectorSource<Feature<Geometry>>> | null>(null);

  // Store slices
  const viewMode = useStore((s) => s.viewMode);
  const wmsConfig = useStore((s) => s.wmsConfig);
  const activeProject = useStore((s) => s.activeProject);
  const selectedPlotId = useStore((s) => s.selectedPlotId);
  const selectPlot = useStore((s) => s.selectPlot);
  const selectedArea = useStore((s) => s.selectedArea);
  const setAreaBoundary = useStore((s) => s.setAreaBoundary);
  const showCsidcReference = useStore((s) => s.showCsidcReference);
  const comparison = useStore((s) => s.comparison);
  const runPromptDetect = useStore((s) => s.runPromptDetect);
  const loadWMSConfig = useStore((s) => s.loadWMSConfig);
  const setMapView = useStore((s) => s.setMapView);

  // -------------------------------------------------------------------
  // 1. Initialize the map (once)
  // -------------------------------------------------------------------
  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;

    const baseTile = new TileLayer({
      source: new XYZ({
        url: "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        maxZoom: 19,
        attributions:
          "Tiles &copy; Esri &mdash; Source: Esri, Maxar, Earthstar Geographics",
      }),
    });

    const plotSource = new VectorSource<Feature<Geometry>>();
    const plotLayer = new VectorLayer({ source: plotSource });

    const boundarySource = new VectorSource<Feature<Geometry>>();
    const boundaryLayer = new VectorLayer({
      source: boundarySource,
      style: new Style({
        fill: new Fill({ color: "rgba(255, 165, 0, 0.08)" }),
        stroke: new Stroke({
          color: "#f97316",
          width: 3,
          lineDash: [10, 6],
        }),
      }),
    });

    const deviationSource = new VectorSource<Feature<Geometry>>();
    const deviationLayer = new VectorLayer({
      source: deviationSource,
      visible: false,
    });

    const map = new Map({
      target: containerRef.current,
      layers: [baseTile, boundaryLayer, plotLayer, deviationLayer],
      view: new View({
        center: [82, 20.8],
        zoom: 7,
      }),
      controls: undefined, // use default zoom + attribution
    });

    baseTileRef.current = baseTile;
    boundaryLayerRef.current = boundaryLayer;
    plotLayerRef.current = plotLayer;
    deviationLayerRef.current = deviationLayer;
    mapRef.current = map;

    // Load WMS config on mount
    loadWMSConfig();

    onMapReady?.(map);

    // Report view extent changes to the store
    const view = map.getView();
    const reportView = () => {
      const extent = view.calculateExtent(map.getSize());
      const zoom = view.getZoom() ?? 7;
      setMapView(extent as [number, number, number, number], Math.round(zoom));
    };
    view.on("change:resolution", reportView);
    view.on("change:center", reportView);

    return () => {
      map.setTarget(undefined);
      mapRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // -------------------------------------------------------------------
  // 2. Add / update WMS overlay when config arrives
  // -------------------------------------------------------------------
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !wmsConfig) return;

    // Remove old WMS layer if present
    if (wmsLayerRef.current) {
      map.removeLayer(wmsLayerRef.current);
    }

    const wmsLayer = new ImageLayer({
      source: new ImageWMS({
        url: wmsConfig.wms_url,
        params: {
          LAYERS: Object.values(wmsConfig.layers).join(","),
          FORMAT: "image/png",
          TRANSPARENT: true,
        },
        serverType: "geoserver",
      }),
      opacity: 0.6,
    });

    // Insert WMS above base tile but below boundary layer
    map.getLayers().insertAt(1, wmsLayer);
    wmsLayerRef.current = wmsLayer;
  }, [wmsConfig]);

  // -------------------------------------------------------------------
  // 2b. Add / update CSIDC reference plots WMS overlay
  // -------------------------------------------------------------------
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !wmsConfig) return;

    // Remove old CSIDC plots layer if present
    if (csidcPlotsLayerRef.current) {
      map.removeLayer(csidcPlotsLayerRef.current);
    }

    const csidcPlotsLayer = new ImageLayer({
      source: new ImageWMS({
        url: wmsConfig.wms_url,
        params: {
          LAYERS: wmsConfig.reference_plots_layer,
          FORMAT: "image/png",
          TRANSPARENT: true,
        },
        serverType: "geoserver",
      }),
      opacity: 0.5,
      visible: showCsidcReference && !!selectedArea,
    });

    // Insert above the general WMS layer but below boundary/vector layers
    // Layer order: baseTile(0), wms(1), csidcPlots(2), boundary(3), plots(4), deviations(5)
    map.getLayers().insertAt(2, csidcPlotsLayer);
    csidcPlotsLayerRef.current = csidcPlotsLayer;
  }, [wmsConfig]);

  // -------------------------------------------------------------------
  // 2c. Toggle CSIDC reference plots layer visibility
  // -------------------------------------------------------------------
  useEffect(() => {
    if (csidcPlotsLayerRef.current) {
      csidcPlotsLayerRef.current.setVisible(showCsidcReference && !!selectedArea);
    }
  }, [showCsidcReference, selectedArea]);

  // -------------------------------------------------------------------
  // 3. Render plots as vector features
  // -------------------------------------------------------------------
  useEffect(() => {
    const layer = plotLayerRef.current;
    if (!layer) return;

    const source = layer.getSource();
    if (!source) return;
    source.clear();

    const plots: PlotData[] = activeProject?.plots ?? [];
    if (plots.length === 0) return;

    const geojsonFormat = new GeoJSON();

    for (const plot of plots) {
      if (!plot.is_active || !plot.geometry) continue;

      const feature = geojsonFormat.readFeature(
        {
          type: "Feature",
          geometry: plot.geometry,
          properties: {
            id: plot.id,
            label: plot.label,
            category: plot.category,
            color: plot.color,
          },
        },
        { dataProjection: "EPSG:4326", featureProjection: "EPSG:4326" }
      ) as Feature<Geometry>;

      feature.setId(plot.id);
      source.addFeature(feature);
    }
  }, [activeProject?.plots]);

  // -------------------------------------------------------------------
  // 4. Style plots — reacts to selectedPlotId and viewMode changes
  // -------------------------------------------------------------------
  useEffect(() => {
    const layer = plotLayerRef.current;
    if (!layer) return;

    layer.setStyle((feature) => {
      const props = feature.getProperties();
      const id = feature.getId();
      const isSelected = id === selectedPlotId;
      const color: string = props.color ?? "#3b82f6";
      const label: string = props.label ?? "";
      const category: string = props.category ?? "other";

      if (viewMode === "schematic") {
        const style = schematicStyle(category, label);
        if (isSelected) {
          style.getStroke()?.setWidth(4);
        }
        return style;
      }

      // Satellite mode
      return new Style({
        fill: new Fill({ color: hexToRgba(color, 0.3) }),
        stroke: new Stroke({
          color,
          width: isSelected ? 4 : 2,
        }),
        text: label
          ? new OlText({
              text: label,
              font: "11px sans-serif",
              fill: new Fill({ color: "#ffffff" }),
              stroke: new Stroke({ color: "#000000", width: 2 }),
              overflow: true,
            })
          : undefined,
      });
    });
  }, [selectedPlotId, viewMode]);

  // -------------------------------------------------------------------
  // 5. Toggle basemap visibility for schematic mode
  // -------------------------------------------------------------------
  useEffect(() => {
    const baseTile = baseTileRef.current;
    if (!baseTile) return;
    baseTile.setVisible(viewMode !== "schematic");

    // Also toggle WMS layer
    if (wmsLayerRef.current) {
      wmsLayerRef.current.setVisible(viewMode !== "schematic");
    }

    // Also toggle CSIDC reference layer
    if (csidcPlotsLayerRef.current) {
      csidcPlotsLayerRef.current.setVisible(
        viewMode !== "schematic" && showCsidcReference && !!selectedArea
      );
    }

    // Update container background for schematic view
    if (containerRef.current) {
      containerRef.current.style.background =
        viewMode === "schematic" ? "#ffffff" : "#1a1a2e";
    }
  }, [viewMode, showCsidcReference, selectedArea]);

  // -------------------------------------------------------------------
  // 6. Render deviation overlay from comparison results
  // -------------------------------------------------------------------
  useEffect(() => {
    const layer = deviationLayerRef.current;
    if (!layer) return;

    const source = layer.getSource();
    if (!source) return;
    source.clear();

    if (!comparison || comparison.deviations.length === 0) {
      layer.setVisible(false);
      return;
    }

    const geojsonFormat = new GeoJSON();

    for (const dev of comparison.deviations) {
      if (!dev.deviation_geometry) continue;

      const feature = geojsonFormat.readFeature(
        {
          type: "Feature",
          geometry: dev.deviation_geometry,
          properties: {
            deviation_type: dev.deviation_type,
            severity: dev.severity,
          },
        },
        { dataProjection: "EPSG:4326", featureProjection: "EPSG:4326" }
      ) as Feature<Geometry>;

      feature.setId(`dev-${dev.id}`);
      source.addFeature(feature);
    }

    layer.setStyle((feature) => {
      const devType = feature.get("deviation_type") as string;
      const color = DEVIATION_COLORS[devType] ?? "#9ca3af";
      return new Style({
        fill: new Fill({ color: hexToRgba(color, 0.35) }),
        stroke: new Stroke({ color, width: 2.5 }),
      });
    });

    layer.setVisible(true);
  }, [comparison]);

  // -------------------------------------------------------------------
  // 7. Zoom to selected area boundary & render boundary outline
  // -------------------------------------------------------------------
  useEffect(() => {
    const boundaryLayer = boundaryLayerRef.current;

    // Clear boundary layer when area changes
    if (boundaryLayer) {
      const src = boundaryLayer.getSource();
      if (src) src.clear();
    }

    if (!selectedArea || !mapRef.current) {
      setAreaBoundary(null);
      return;
    }

    let cancelled = false;

    (async () => {
      try {
        const boundary = await fetchAreaBoundary(
          selectedArea.name,
          selectedArea.category
        );
        if (cancelled || !mapRef.current) return;

        // Store boundary in Zustand so Sidebar/detection can use it
        setAreaBoundary(boundary);

        const geojsonFormat = new GeoJSON();
        const feature = geojsonFormat.readFeature(
          {
            type: "Feature",
            geometry: boundary.geometry,
            properties: {},
          },
          { dataProjection: "EPSG:4326", featureProjection: "EPSG:4326" }
        ) as Feature<Geometry>;

        // Add boundary feature to the boundary layer
        if (boundaryLayer) {
          const src = boundaryLayer.getSource();
          if (src) {
            src.clear();
            src.addFeature(feature);
          }
        }

        const extent = feature.getGeometry()?.getExtent();
        if (extent) {
          mapRef.current.getView().fit(extent, {
            padding: [60, 60, 60, 60],
            duration: 800,
            maxZoom: 18,
          });
        }
      } catch {
        // Boundary fetch failed — no zoom action
        setAreaBoundary(null);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [selectedArea, setAreaBoundary]);

  // -------------------------------------------------------------------
  // 8. Click handler — plot selection & prompt-detect
  // -------------------------------------------------------------------
  const handleClick = useCallback(
    (evt: MapBrowserEvent<PointerEvent>) => {
      const map = mapRef.current;
      if (!map) return;

      // Prompt-detect mode: collect coordinate and fire detection
      if (promptMode) {
        const [lon, lat] = evt.coordinate;
        runPromptDetect([{ lon, lat, label: 1 }]);
        return;
      }

      // Normal mode: try to select a plot feature
      const plotLayer = plotLayerRef.current;
      if (!plotLayer) return;

      let hit = false;
      map.forEachFeatureAtPixel(
        evt.pixel,
        (feature) => {
          if (hit) return;
          const id = feature.getId();
          if (id != null) {
            selectPlot(id as number);
            hit = true;
          }
        },
        { layerFilter: (l) => l === plotLayer }
      );

      // Click on empty space deselects
      if (!hit) {
        selectPlot(null);
      }
    },
    [promptMode, selectPlot, runPromptDetect]
  );

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    map.on("singleclick", handleClick as any);
    return () => {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      map.un("singleclick", handleClick as any);
    };
  }, [handleClick]);

  // -------------------------------------------------------------------
  // 9. Cursor style for prompt mode
  // -------------------------------------------------------------------
  useEffect(() => {
    if (containerRef.current) {
      containerRef.current.style.cursor = promptMode ? "crosshair" : "";
    }
  }, [promptMode]);

  // -------------------------------------------------------------------
  // Render
  // -------------------------------------------------------------------
  return (
    <div
      ref={containerRef}
      className="w-full h-full"
      style={{ position: "relative" }}
    />
  );
};

// ---------------------------------------------------------------------------
// Utility: convert hex color to rgba string
// ---------------------------------------------------------------------------
function hexToRgba(hex: string, alpha: number): string {
  // Handle shorthand and named colors by falling back to a default
  const cleaned = hex.replace("#", "");
  let r = 0,
    g = 0,
    b = 0;

  if (cleaned.length === 3) {
    r = parseInt(cleaned[0] + cleaned[0], 16);
    g = parseInt(cleaned[1] + cleaned[1], 16);
    b = parseInt(cleaned[2] + cleaned[2], 16);
  } else if (cleaned.length === 6) {
    r = parseInt(cleaned.slice(0, 2), 16);
    g = parseInt(cleaned.slice(2, 4), 16);
    b = parseInt(cleaned.slice(4, 6), 16);
  } else {
    // Fallback for non-hex colors
    return `rgba(59,130,246,${alpha})`;
  }

  return `rgba(${r},${g},${b},${alpha})`;
}

export default MapView;
