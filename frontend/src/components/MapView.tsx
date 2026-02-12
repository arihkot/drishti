import React, { useRef, useEffect, useCallback, useState } from "react";
import { createPortal } from "react-dom";
import Map from "ol/Map";
import View from "ol/View";
import Overlay from "ol/Overlay";
import TileLayer from "ol/layer/Tile";
import XYZ from "ol/source/XYZ";
import TileWMS from "ol/source/TileWMS";
import ImageLayer from "ol/layer/Image";
import ImageWMS from "ol/source/ImageWMS";
import VectorLayer from "ol/layer/Vector";
import VectorSource from "ol/source/Vector";
import GeoJSON from "ol/format/GeoJSON";
import { Style, Fill, Stroke, Text as OlText, Circle as CircleStyle } from "ol/style";
import { useGeographic } from "ol/proj";
import Feature from "ol/Feature";
import { Modify } from "ol/interaction";
import { Collection } from "ol";
import type { MapBrowserEvent } from "ol";
import type { Geometry } from "ol/geom";

import { useStore } from "../stores/useStore";
import { fetchAreaBoundary, fetchReferencePlotsGeoJSON } from "../api/client";
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
    boundary: { fill: "rgba(249,115,22,0.08)", stroke: "#f97316" },
    // Legacy support
    parcel: { fill: "rgba(239,68,68,0.15)", stroke: "#ef4444" },
  };
  const cfg = base[category] ?? base.plot;

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
  const csidcRefLayerRef = useRef<TileLayer<TileWMS> | null>(null);
  const csidcRefVectorLayerRef = useRef<VectorLayer<VectorSource<Feature<Geometry>>> | null>(null);
  const boundaryLayerRef = useRef<VectorLayer<VectorSource<Feature<Geometry>>> | null>(null);
  const plotLayerRef = useRef<VectorLayer<VectorSource<Feature<Geometry>>> | null>(null);
  const deviationLayerRef = useRef<VectorLayer<VectorSource<Feature<Geometry>>> | null>(null);

  // Modify interaction ref for boundary editing
  const modifyRef = useRef<Modify | null>(null);
  const editCollectionRef = useRef<Collection<Feature<Geometry>> | null>(null);

  // Hover popup refs
  const popupElRef = useRef<HTMLDivElement | null>(null);
  const overlayRef = useRef<Overlay | null>(null);
  const [hoverInfo, setHoverInfo] = useState<{
    label: string;
    category: string;
    color: string;
    source?: "detected" | "csidc_reference";
    allottee?: string;
    area_sqm?: number | null;
    area_sqft?: number | null;
    perimeter_m?: number | null;
    confidence?: number | null;
    status?: string;
    plot_type?: string;
    location?: string;
    district?: string;
  } | null>(null);

  // Store slices
  const viewMode = useStore((s) => s.viewMode);
  const wmsConfig = useStore((s) => s.wmsConfig);
  const activeProject = useStore((s) => s.activeProject);
  const selectedPlotId = useStore((s) => s.selectedPlotId);
  const selectPlot = useStore((s) => s.selectPlot);
  const selectedArea = useStore((s) => s.selectedArea);
  const setAreaBoundary = useStore((s) => s.setAreaBoundary);
  const showCsidcReference = useStore((s) => s.showCsidcReference);
  const hideDetectedPlots = useStore((s) => s.hideDetectedPlots);
  const csidcReferencePlots = useStore((s) => s.csidcReferencePlots);
  const loadCsidcReferencePlots = useStore((s) => s.loadCsidcReferencePlots);
  const comparison = useStore((s) => s.comparison);
  const runPromptDetect = useStore((s) => s.runPromptDetect);
  const loadWMSConfig = useStore((s) => s.loadWMSConfig);
  const setMapView = useStore((s) => s.setMapView);

  // Editing state
  const editingPlotId = useStore((s) => s.editingPlotId);
  const updateEditingGeometry = useStore((s) => s.updateEditingGeometry);
  const cancelEditing = useStore((s) => s.cancelEditing);
  const saveEditing = useStore((s) => s.saveEditing);

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

    const csidcRefSource = new TileWMS({
      url: "/api/areas/wms-proxy",
      params: {
        LAYERS: "CGCOG_DATABASE:csidc_industrial_area_with_plots",
        FORMAT: "image/png",
        TRANSPARENT: true,
        SRS: "EPSG:4326",
        VERSION: "1.1.1",
        SERVICE: "WMS",
        REQUEST: "GetMap",
      },
      serverType: "geoserver",
    });
    const csidcRefLayer = new TileLayer({
      source: csidcRefSource,
      visible: false,
      opacity: 0.55,
    });

    // CSIDC reference vector layer — for hover/tooltip interaction
    const csidcRefVectorSource = new VectorSource<Feature<Geometry>>();
    const csidcRefVectorLayer = new VectorLayer({
      source: csidcRefVectorSource,
      visible: false,
      style: new Style({
        fill: new Fill({ color: "rgba(34, 197, 94, 0.12)" }),
        stroke: new Stroke({
          color: "#16a34a",
          width: 1.5,
          lineDash: [6, 3],
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
      layers: [baseTile, csidcRefLayer, csidcRefVectorLayer, boundaryLayer, plotLayer, deviationLayer],
      view: new View({
        center: [82, 20.8],
        zoom: 7,
      }),
      controls: undefined, // use default zoom + attribution
    });

    baseTileRef.current = baseTile;
    csidcRefLayerRef.current = csidcRefLayer;
    csidcRefVectorLayerRef.current = csidcRefVectorLayer;
    boundaryLayerRef.current = boundaryLayer;
    plotLayerRef.current = plotLayer;
    deviationLayerRef.current = deviationLayer;
    mapRef.current = map;

    // Create hover popup overlay (DOM element created programmatically to avoid React ref timing issues)
    const popupEl = document.createElement("div");
    popupEl.style.position = "absolute";
    popupEl.style.zIndex = "10";
    popupElRef.current = popupEl;

    const popupOverlay = new Overlay({
      element: popupEl,
      positioning: "bottom-center",
      offset: [0, -12],
      stopEvent: false,
    });
    map.addOverlay(popupOverlay);
    overlayRef.current = popupOverlay;

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
  // 2b. Update CSIDC ref WMS layer extent when project bbox changes
  // -------------------------------------------------------------------
  useEffect(() => {
    const layer = csidcRefLayerRef.current;
    if (!layer) return;

    const bbox = activeProject?.bbox;
    if (bbox && bbox.length === 4) {
      // Clip the WMS layer to the detected project extent
      layer.setExtent(bbox as [number, number, number, number]);
    } else {
      // No project bbox — don't clip, but layer won't show (no detection run yet)
      layer.setExtent(undefined);
    }
  }, [activeProject?.bbox]);

  // -------------------------------------------------------------------
  // 2c. Toggle CSIDC reference layer visibility
  // -------------------------------------------------------------------
  useEffect(() => {
    if (csidcRefLayerRef.current) {
      // Only show when toggle is on AND there is a detected extent to clip to
      const hasBbox = activeProject?.bbox && activeProject.bbox.length === 4;
      csidcRefLayerRef.current.setVisible(showCsidcReference && !!hasBbox);
    }
  }, [showCsidcReference, activeProject?.bbox]);

  // -------------------------------------------------------------------
  // 2d. Auto-load CSIDC reference plots when ref/only modes are toggled
  // -------------------------------------------------------------------
  useEffect(() => {
    if ((showCsidcReference || hideDetectedPlots) && activeProject?.area_name) {
      loadCsidcReferencePlots(
        activeProject.area_name,
        activeProject.area_category ?? "industrial"
      );
    }
  }, [showCsidcReference, hideDetectedPlots, activeProject?.area_name, activeProject?.area_category, loadCsidcReferencePlots]);

  // -------------------------------------------------------------------
  // 2e. Populate CSIDC reference vector layer from cached data
  // -------------------------------------------------------------------
  useEffect(() => {
    const layer = csidcRefVectorLayerRef.current;
    if (!layer) return;

    const source = layer.getSource();
    if (!source) return;
    source.clear();

    if (!csidcReferencePlots || csidcReferencePlots.features.length === 0) {
      layer.setVisible(false);
      return;
    }

    const geojsonFormat = new GeoJSON();
    for (const feat of csidcReferencePlots.features) {
      if (!feat.geometry) continue;
      try {
        const feature = geojsonFormat.readFeature(feat, {
          dataProjection: "EPSG:4326",
          featureProjection: "EPSG:4326",
        }) as Feature<Geometry>;
        feature.setId(feat.id);
        source.addFeature(feature);
      } catch {
        // Skip invalid geometries
      }
    }

    // Visibility follows the same logic as the WMS layer
    const hasBbox = activeProject?.bbox && activeProject.bbox.length === 4;
    layer.setVisible((showCsidcReference || hideDetectedPlots) && !!hasBbox);
  }, [csidcReferencePlots, showCsidcReference, hideDetectedPlots, activeProject?.bbox]);

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
            area_sqm: plot.area_sqm,
            area_sqft: plot.area_sqft,
            perimeter_m: plot.perimeter_m,
            confidence: plot.confidence,
          },
        },
        { dataProjection: "EPSG:4326", featureProjection: "EPSG:4326" }
      ) as Feature<Geometry>;

      feature.setId(plot.id);
      source.addFeature(feature);
    }
  }, [activeProject?.plots]);

  // -------------------------------------------------------------------
  // 4. Style plots — reacts to selectedPlotId, viewMode, and editingPlotId
  // -------------------------------------------------------------------
  useEffect(() => {
    const layer = plotLayerRef.current;
    if (!layer) return;

    layer.setStyle((feature) => {
      const props = feature.getProperties();
      const id = feature.getId();
      const isSelected = id === selectedPlotId;
      const isEditing = id === editingPlotId;
      const inEditMode = editingPlotId !== null;
      const color: string = props.color ?? "#3b82f6";
      const label: string = props.label ?? "";
      const category: string = props.category ?? "plot";

      // Special style for the feature being edited
      if (isEditing) {
        return [
          new Style({
            fill: new Fill({ color: "rgba(0, 200, 255, 0.15)" }),
            stroke: new Stroke({
              color: "#00c8ff",
              width: 3,
              lineDash: [8, 4],
            }),
            text: label
              ? new OlText({
                  text: `${label} (editing)`,
                  font: "bold 12px sans-serif",
                  fill: new Fill({ color: "#00c8ff" }),
                  stroke: new Stroke({ color: "#000000", width: 3 }),
                  overflow: true,
                })
              : undefined,
          }),
          // Vertex circles
          new Style({
            image: new CircleStyle({
              radius: 5,
              fill: new Fill({ color: "#00c8ff" }),
              stroke: new Stroke({ color: "#ffffff", width: 2 }),
            }),
          }),
        ];
      }

      // Dim non-editing features when in edit mode
      const dimFactor = inEditMode ? 0.35 : 1;

      if (viewMode === "schematic") {
        const style = schematicStyle(category, label);
        if (isSelected && !inEditMode) {
          style.getStroke()?.setWidth(4);
        }
        if (inEditMode) {
          style.getStroke()?.setColor(`rgba(128,128,128,${dimFactor})`);
          style.getFill()?.setColor(`rgba(200,200,200,0.08)`);
        }
        return style;
      }

      // Satellite mode
      return new Style({
        fill: new Fill({
          color: inEditMode
            ? `rgba(128,128,128,0.1)`
            : hexToRgba(color, 0.3),
        }),
        stroke: new Stroke({
          color: inEditMode ? `rgba(128,128,128,${dimFactor})` : color,
          width: isSelected && !inEditMode ? 4 : 2,
        }),
        text: label
          ? new OlText({
              text: label,
              font: "11px sans-serif",
              fill: new Fill({
                color: inEditMode ? `rgba(255,255,255,${dimFactor})` : "#ffffff",
              }),
              stroke: new Stroke({
                color: inEditMode ? `rgba(0,0,0,${dimFactor})` : "#000000",
                width: 2,
              }),
              overflow: true,
            })
          : undefined,
      });
    });
  }, [selectedPlotId, viewMode, editingPlotId]);

  // -------------------------------------------------------------------
  // 4b. Toggle plot layer visibility (CSIDC Only mode)
  // -------------------------------------------------------------------
  useEffect(() => {
    if (plotLayerRef.current) {
      plotLayerRef.current.setVisible(!hideDetectedPlots);
    }
  }, [hideDetectedPlots]);

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
    if (csidcRefLayerRef.current) {
      const hasBbox = activeProject?.bbox && activeProject.bbox.length === 4;
      csidcRefLayerRef.current.setVisible(
        viewMode !== "schematic" && showCsidcReference && !!hasBbox
      );
    }

    // Also toggle CSIDC reference vector layer
    if (csidcRefVectorLayerRef.current) {
      const hasBbox = activeProject?.bbox && activeProject.bbox.length === 4;
      csidcRefVectorLayerRef.current.setVisible(
        viewMode !== "schematic" && (showCsidcReference || hideDetectedPlots) && !!hasBbox
      );
    }

    // Update container background for schematic view
    if (containerRef.current) {
      containerRef.current.style.background =
        viewMode === "schematic" ? "#ffffff" : "#1a1a2e";
    }
  }, [viewMode, showCsidcReference, hideDetectedPlots, activeProject?.bbox]);

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

      // Block clicks during boundary editing
      if (editingPlotId !== null) return;

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
    [promptMode, selectPlot, runPromptDetect, editingPlotId]
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
  // 8b. Hover popup — show plot info on pointermove
  // -------------------------------------------------------------------
  useEffect(() => {
    const map = mapRef.current;
    const overlay = overlayRef.current;
    if (!map || !overlay) return;

    const handlePointerMove = (e: MapBrowserEvent<PointerEvent>) => {
      if (promptMode || editingPlotId !== null) {
        overlay.setPosition(undefined);
        setHoverInfo(null);
        return;
      }

      const plotLayer = plotLayerRef.current;
      const csidcRefVectorLayer = csidcRefVectorLayerRef.current;
      let hit = false;

      // 1. First, try detected plot layer (unless hidden)
      if (plotLayer && !hideDetectedPlots) {
        map.forEachFeatureAtPixel(
          e.pixel,
          (feature) => {
            const props = (feature as Feature).getProperties();
            setHoverInfo({
              label: props.label || "Unknown",
              category: props.category || "plot",
              color: props.color || "#3b82f6",
              source: "detected",
              area_sqm: props.area_sqm ?? null,
              area_sqft: props.area_sqft ?? null,
              perimeter_m: props.perimeter_m ?? null,
              confidence: props.confidence ?? null,
            });
            overlay.setPosition(e.coordinate);
            hit = true;
            return true; // stop iterating
          },
          {
            layerFilter: (layer) => layer === plotLayer,
            hitTolerance: 2,
          }
        );
      }

      // 2. If no detected plot hit, try CSIDC reference vector layer
      if (!hit && csidcRefVectorLayer && csidcRefVectorLayer.getVisible()) {
        map.forEachFeatureAtPixel(
          e.pixel,
          (feature) => {
            const props = (feature as Feature).getProperties();
            setHoverInfo({
              label: props.name || "Unknown Plot",
              category: "CSIDC Reference",
              color: "#16a34a",
              source: "csidc_reference",
              allottee: props.allottee || undefined,
              area_sqm: props.area_sqm ?? null,
              status: props.status || undefined,
              plot_type: props.plot_type || undefined,
              location: props.location || undefined,
              district: props.district || undefined,
            });
            overlay.setPosition(e.coordinate);
            hit = true;
            return true;
          },
          {
            layerFilter: (layer) => layer === csidcRefVectorLayer,
            hitTolerance: 2,
          }
        );
      }

      if (!hit) {
        overlay.setPosition(undefined);
        setHoverInfo(null);
      }

      // Set cursor to pointer when hovering over a feature
      if (containerRef.current && !promptMode && editingPlotId === null) {
        containerRef.current.style.cursor = hit ? "pointer" : "";
      }
    };

    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    map.on("pointermove", handlePointerMove as any);
    return () => {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      map.un("pointermove", handlePointerMove as any);
      // Note: overlay persists across re-renders and is cleaned up when the map unmounts
    };
  }, [promptMode, editingPlotId, hideDetectedPlots, showCsidcReference]);

  // -------------------------------------------------------------------
  // 9. Cursor style for prompt mode and edit mode
  // -------------------------------------------------------------------
  useEffect(() => {
    if (containerRef.current) {
      if (editingPlotId !== null) {
        containerRef.current.style.cursor = "grab";
      } else if (promptMode) {
        containerRef.current.style.cursor = "crosshair";
      } else {
        containerRef.current.style.cursor = "";
      }
    }
  }, [promptMode, editingPlotId]);

  // -------------------------------------------------------------------
  // 10. Modify interaction for boundary editing
  // -------------------------------------------------------------------
  useEffect(() => {
    const map = mapRef.current;
    const plotLayer = plotLayerRef.current;
    if (!map || !plotLayer) return;

    // Clean up previous modify interaction
    if (modifyRef.current) {
      map.removeInteraction(modifyRef.current);
      modifyRef.current = null;
    }
    editCollectionRef.current = null;

    if (editingPlotId === null) return;

    // Find the feature with the editing plot ID
    const source = plotLayer.getSource();
    if (!source) return;
    const feature = source.getFeatureById(editingPlotId);
    if (!feature) return;

    // Create a collection with just this feature
    const collection = new Collection<Feature<Geometry>>([feature as Feature<Geometry>]);
    editCollectionRef.current = collection;

    // Create the Modify interaction
    const modify = new Modify({
      features: collection,
      style: new Style({
        image: new CircleStyle({
          radius: 6,
          fill: new Fill({ color: "#00c8ff" }),
          stroke: new Stroke({ color: "#ffffff", width: 2 }),
        }),
      }),
    });

    modify.on("modifyend", () => {
      const geojsonFormat = new GeoJSON();
      const geom = feature.getGeometry();
      if (geom) {
        const geojsonGeom = geojsonFormat.writeGeometryObject(geom) as {
          type: string;
          coordinates: number[] | number[][] | number[][][] | number[][][][];
        };
        updateEditingGeometry(geojsonGeom);
      }
    });

    map.addInteraction(modify);
    modifyRef.current = modify;

    return () => {
      if (modifyRef.current) {
        map.removeInteraction(modifyRef.current);
        modifyRef.current = null;
      }
      editCollectionRef.current = null;
    };
  }, [editingPlotId, updateEditingGeometry]);

  // -------------------------------------------------------------------
  // 11. Keyboard shortcuts for editing (Escape to cancel, Cmd/Ctrl+S to save)
  // -------------------------------------------------------------------
  useEffect(() => {
    if (editingPlotId === null) return;

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        cancelEditing();
      }
      if (e.key === "s" && (e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        saveEditing();
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [editingPlotId, cancelEditing, saveEditing]);

  // -------------------------------------------------------------------
  // Render
  // -------------------------------------------------------------------
  const popupContent = (
    <div
      className={`transition-opacity duration-150 ${hoverInfo ? "opacity-100" : "opacity-0 pointer-events-none"}`}
    >
      {hoverInfo && (
        <div className="bg-black/80 text-white rounded-lg shadow-xl px-3.5 py-2.5 text-xs whitespace-nowrap border border-white/15 max-w-xs">
          <div className="flex items-center gap-2 mb-1">
            <span
              className="w-3 h-3 rounded-sm flex-shrink-0 border border-white/20"
              style={{ backgroundColor: hoverInfo.color }}
            />
            <span className="font-semibold text-sm text-white">{hoverInfo.label}</span>
          </div>
          <div className="text-gray-200 capitalize">{hoverInfo.category}</div>

          {/* Details for detected plots */}
          {hoverInfo.source === "detected" && (
            <div className="mt-1.5 pt-1.5 border-t border-white/15 space-y-0.5">
              {hoverInfo.area_sqm != null && (
                <div>
                  <span className="text-gray-400">Area:</span>{" "}
                  <span className="text-white">
                    {hoverInfo.area_sqm.toLocaleString(undefined, {
                      maximumFractionDigits: 1,
                    })}{" "}
                    sqm
                    {hoverInfo.area_sqft != null && (
                      <span className="text-gray-300">
                        {" "}({hoverInfo.area_sqft.toLocaleString(undefined, { maximumFractionDigits: 0 })} sqft)
                      </span>
                    )}
                  </span>
                </div>
              )}
              {hoverInfo.perimeter_m != null && (
                <div>
                  <span className="text-gray-400">Perimeter:</span>{" "}
                  <span className="text-white">
                    {hoverInfo.perimeter_m.toLocaleString(undefined, {
                      maximumFractionDigits: 1,
                    })}{" "}
                    m
                  </span>
                </div>
              )}
              {hoverInfo.confidence != null && (
                <div>
                  <span className="text-gray-400">Confidence:</span>{" "}
                  <span className="text-white">
                    {(hoverInfo.confidence * 100).toFixed(1)}%
                  </span>
                </div>
              )}
            </div>
          )}

          {/* Details for CSIDC reference plots */}
          {hoverInfo.source === "csidc_reference" && (
            <div className="mt-1.5 pt-1.5 border-t border-white/15 space-y-0.5">
              {hoverInfo.plot_type && (
                <div>
                  <span className="text-gray-400">Type:</span>{" "}
                  <span className="text-white">{hoverInfo.plot_type}</span>
                </div>
              )}
              {hoverInfo.status && (
                <div>
                  <span className="text-gray-400">Status:</span>{" "}
                  <span className="text-white">{hoverInfo.status}</span>
                </div>
              )}
              {hoverInfo.allottee && (
                <div>
                  <span className="text-gray-400">Allottee:</span>{" "}
                  <span className="text-white">{hoverInfo.allottee}</span>
                </div>
              )}
              {hoverInfo.area_sqm != null && (
                <div>
                  <span className="text-gray-400">Area:</span>{" "}
                  <span className="text-white">
                    {hoverInfo.area_sqm.toLocaleString(undefined, {
                      maximumFractionDigits: 1,
                    })}{" "}
                    sqm
                  </span>
                </div>
              )}
              {hoverInfo.location && (
                <div>
                  <span className="text-gray-400">Location:</span>{" "}
                  <span className="text-white">{hoverInfo.location}</span>
                </div>
              )}
              {hoverInfo.district && (
                <div>
                  <span className="text-gray-400">District:</span>{" "}
                  <span className="text-white">{hoverInfo.district}</span>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );

  return (
    <>
      <div
        ref={containerRef}
        className="w-full h-full"
        style={{ position: "relative" }}
      />
      {/* Portal popup content into the OL overlay element */}
      {popupElRef.current && createPortal(popupContent, popupElRef.current)}
    </>
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
