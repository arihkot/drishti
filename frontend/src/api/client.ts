import type {
  IndustrialArea,
  WMSConfig,
  AreaBoundary,
  Project,
  AutoDetectRequest,
  AutoDetectResponse,
  PromptDetectRequest,
  PromptDetectResponse,
  ComparisonResult,
  ModelStatus,
  GeoJSONFeatureCollection,
  GeoJSONGeometry,
  CsidcReferencePlotsGeoJSON,
} from "../types";

const BASE = "";

async function request<T>(
  path: string,
  options?: RequestInit
): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...options?.headers },
    ...options,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`API ${res.status}: ${text}`);
  }
  return res.json() as Promise<T>;
}

// ---- Areas ----
export async function fetchAreas(
  category?: string
): Promise<{ areas: IndustrialArea[]; total: number }> {
  const q = category ? `?category=${category}` : "";
  return request(`/api/areas${q}`);
}

export async function fetchWMSConfig(): Promise<WMSConfig> {
  return request("/api/areas/wms-config");
}

export async function fetchAreaBoundary(
  areaName: string,
  category = "industrial"
): Promise<AreaBoundary> {
  return request(
    `/api/areas/${encodeURIComponent(areaName)}/boundary?category=${category}`
  );
}

export async function fetchDistricts(): Promise<{
  districts: { name: string; code: string; geometry: unknown }[];
  total: number;
}> {
  return request("/api/areas/districts");
}

export async function fetchReferencePlotsGeoJSON(
  areaName: string,
  category = "industrial"
): Promise<CsidcReferencePlotsGeoJSON> {
  return request(
    `/api/areas/${encodeURIComponent(areaName)}/reference-plots/geojson?category=${category}`
  );
}

// ---- Projects ----
export async function fetchProjects(): Promise<{ projects: Project[] }> {
  return request("/api/projects");
}

export async function fetchProject(id: number): Promise<Project> {
  return request(`/api/projects/${id}`);
}

export async function createProject(data: {
  name: string;
  area_name?: string;
  area_category?: string;
  description?: string;
  bbox?: number[];
  center_lon?: number;
  center_lat?: number;
  zoom?: number;
}): Promise<{ id: number; name: string }> {
  return request("/api/projects", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export async function deleteProject(id: number): Promise<void> {
  return request(`/api/projects/${id}`, { method: "DELETE" });
}

export async function updatePlot(
  projectId: number,
  plotId: number,
  data: { label?: string; category?: string; color?: string; geometry?: GeoJSONGeometry }
): Promise<{ id: number; label: string; category: string; color: string; area_sqm?: number; area_sqft?: number; perimeter_m?: number }> {
  return request(`/api/projects/${projectId}/plots/${plotId}`, {
    method: "PUT",
    body: JSON.stringify(data),
  });
}

export async function deletePlot(
  projectId: number,
  plotId: number
): Promise<void> {
  return request(`/api/projects/${projectId}/plots/${plotId}`, {
    method: "DELETE",
  });
}

// ---- Detection ----
export async function autoDetect(
  data: AutoDetectRequest
): Promise<AutoDetectResponse> {
  return request("/api/detect/auto", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export async function promptDetect(
  data: PromptDetectRequest
): Promise<PromptDetectResponse> {
  return request("/api/detect/prompt", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export async function getModelStatus(): Promise<ModelStatus> {
  return request("/api/detect/model-status");
}

export async function preloadModel(): Promise<{ status: string }> {
  return request("/api/detect/preload-model", { method: "POST" });
}

// ---- Comparison ----
export async function runComparison(
  projectId: number,
  toleranceM = 2.0
): Promise<ComparisonResult> {
  return request(`/api/compare/${projectId}`, {
    method: "POST",
    body: JSON.stringify({ tolerance_m: toleranceM }),
  });
}

export async function getComparison(
  projectId: number
): Promise<ComparisonResult> {
  return request(`/api/compare/${projectId}`);
}

// ---- Export ----
export async function exportPDF(
  projectId: number,
  options?: {
    include_satellite?: boolean;
    include_schematic?: boolean;
    include_deviations?: boolean;
  }
): Promise<Blob> {
  const res = await fetch(`${BASE}/api/export/${projectId}/pdf`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(options ?? {}),
  });
  if (!res.ok) throw new Error(`Export failed: ${res.status}`);
  return res.blob();
}

export async function exportGeoJSON(
  projectId: number
): Promise<GeoJSONFeatureCollection> {
  return request(`/api/export/${projectId}/geojson`, { method: "POST" });
}
