// ---- GeoJSON types ----
export interface GeoJSONGeometry {
  type: string;
  coordinates: number[] | number[][] | number[][][] | number[][][][];
}

export interface GeoJSONFeature {
  type: "Feature";
  geometry: GeoJSONGeometry;
  properties: Record<string, unknown>;
}

export interface GeoJSONFeatureCollection {
  type: "FeatureCollection";
  features: GeoJSONFeature[];
  properties?: Record<string, unknown>;
}

// ---- API types ----
export interface IndustrialArea {
  name: string;
  category: string;
  has_geometry: boolean;
}

export interface AreaBoundary {
  name: string;
  category: string;
  geometry: GeoJSONGeometry;
  properties: Record<string, unknown>;
}

export interface WMSConfig {
  wms_url: string;
  workspace: string;
  layers: Record<string, string>;
  reference_plots_layer: string;
  satellite_url: string;
  map_center: [number, number];
  map_zoom: number;
}

export interface Project {
  id: number;
  name: string;
  area_name: string | null;
  area_category: string | null;
  description: string | null;
  bbox: number[] | null;
  center_lon: number | null;
  center_lat: number | null;
  zoom: number;
  created_at: string;
  updated_at: string;
  plots?: PlotData[];
}

export interface PlotData {
  id: number;
  label: string;
  category: string;
  geometry: GeoJSONGeometry;
  area_sqm: number | null;
  area_sqft: number | null;
  perimeter_m: number | null;
  color: string;
  confidence: number | null;
  is_active: boolean;
  properties: Record<string, unknown> | null;
  created_at: string;
  centroid?: { lon: number; lat: number };
}

export interface AutoDetectRequest {
  bbox: [number, number, number, number];
  zoom: number;
  project_id?: number;
  project_name?: string;
  area_name?: string;
  area_category?: string;
  min_area_sqm?: number;
}

export interface AutoDetectResponse {
  project_id: number;
  project_name: string;
  plots: PlotData[];
  total: number;
  image_size: [number, number];
  meta: {
    bbox: number[];
    zoom: number;
    tiles: string;
  };
}

export interface PromptDetectRequest {
  bbox: [number, number, number, number];
  zoom: number;
  project_id: number;
  points?: { lon: number; lat: number; label: number }[];
  boxes?: [number, number, number, number][];
}

export interface PromptDetectResponse {
  project_id: number;
  new_plots: PlotData[];
  total_new: number;
}

export interface Deviation {
  id: number;
  plot_id: number | null;
  deviation_type: string;
  severity: string;
  deviation_area_sqm: number | null;
  deviation_geometry: GeoJSONGeometry | null;
  details: Record<string, unknown> | null;
  description: string | null;
  created_at: string;
}

export interface ComparisonResult {
  summary: {
    total: number;
    total_detected: number;
    total_basemap: number;
    compliant: number;
    encroachment: number;
    boundary_mismatch: number;
    vacant: number;
    unauthorized: number;
    unmatched_detected: number;
    unmatched_basemap: number;
  };
  deviations: Deviation[];
}

export interface ModelStatus {
  loaded: boolean;
  model_type: string;
  device: string;
}

export type DeviationType =
  | "ENCROACHMENT"
  | "UNAUTHORIZED_DEVELOPMENT"
  | "VACANT"
  | "BOUNDARY_MISMATCH"
  | "COMPLIANT";

export type Severity = "low" | "medium" | "high" | "critical";

export type PlotCategory = "plot" | "road" | "vegetation" | "open_land" | "water" | "building" | "infrastructure" | "other";
