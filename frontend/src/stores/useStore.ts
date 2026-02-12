import { create } from "zustand";
import type {
  IndustrialArea,
  AreaBoundary,
  Project,
  ComparisonResult,
  WMSConfig,
  GeoJSONGeometry,
} from "../types";
import * as api from "../api/client";

type ViewMode = "satellite" | "schematic";
type SidebarTab = "areas" | "plots" | "compare" | "export";

interface AppState {
  // ---- Map ----
  viewMode: ViewMode;
  setViewMode: (mode: ViewMode) => void;
  wmsConfig: WMSConfig | null;
  loadWMSConfig: () => Promise<void>;
  mapExtent: [number, number, number, number] | null;
  mapZoom: number;
  setMapView: (extent: [number, number, number, number], zoom: number) => void;
  showCsidcReference: boolean;
  toggleCsidcReference: () => void;
  hideDetectedPlots: boolean;
  toggleHideDetectedPlots: () => void;

  // ---- Areas ----
  areas: IndustrialArea[];
  areasLoading: boolean;
  selectedArea: IndustrialArea | null;
  areaBoundary: AreaBoundary | null;
  loadAreas: (category?: string) => Promise<void>;
  selectArea: (area: IndustrialArea | null) => void;
  setAreaBoundary: (boundary: AreaBoundary | null) => void;

  // ---- Project ----
  projects: Project[];
  activeProject: Project | null;
  projectLoading: boolean;
  loadProjects: () => Promise<void>;
  loadProject: (id: number) => Promise<void>;
  setActiveProject: (project: Project | null) => void;

  // ---- Plots ----
  selectedPlotId: number | null;
  selectPlot: (id: number | null) => void;
  updatePlotLabel: (
    plotId: number,
    label: string
  ) => Promise<void>;
  updatePlotColor: (
    plotId: number,
    color: string
  ) => Promise<void>;
  removePlot: (plotId: number) => Promise<void>;

  // ---- Boundary Editing ----
  editingPlotId: number | null;
  editingGeometry: GeoJSONGeometry | null;
  startEditing: (plotId: number) => void;
  cancelEditing: () => void;
  saveEditing: () => Promise<void>;
  updateEditingGeometry: (geom: GeoJSONGeometry) => void;

  // ---- Detection ----
  detecting: boolean;
  detectionProgress: string;
  runAutoDetect: (
    bbox: [number, number, number, number],
    zoom: number
  ) => Promise<void>;
  runPromptDetect: (
    points?: { lon: number; lat: number; label: number }[],
    boxes?: [number, number, number, number][]
  ) => Promise<void>;

  // ---- Comparison ----
  comparison: ComparisonResult | null;
  comparing: boolean;
  runComparison: () => Promise<void>;
  loadComparison: () => Promise<void>;

  // ---- Export ----
  exporting: boolean;
  exportPDF: () => Promise<void>;
  exportGeoJSON: () => Promise<void>;

  // ---- UI ----
  sidebarTab: SidebarTab;
  setSidebarTab: (tab: SidebarTab) => void;
  sidebarOpen: boolean;
  toggleSidebar: () => void;
  toast: { message: string; type: "success" | "error" | "info" } | null;
  showToast: (
    message: string,
    type?: "success" | "error" | "info"
  ) => void;
  clearToast: () => void;
}

export const useStore = create<AppState>((set, get) => ({
  // ---- Map ----
  viewMode: "satellite",
  setViewMode: (mode) => set({ viewMode: mode }),
  wmsConfig: null,
  mapExtent: null,
  mapZoom: 7,
  setMapView: (extent, zoom) => set({ mapExtent: extent, mapZoom: zoom }),
  showCsidcReference: false,
  toggleCsidcReference: () => {
    set((s) => ({ showCsidcReference: !s.showCsidcReference }));
  },
  hideDetectedPlots: false,
  toggleHideDetectedPlots: () => {
    set((s) => {
      const newHide = !s.hideDetectedPlots;
      // Auto-enable CSIDC reference when entering "CSIDC Only" mode
      if (newHide && !s.showCsidcReference) {
        return { hideDetectedPlots: newHide, showCsidcReference: true };
      }
      return { hideDetectedPlots: newHide };
    });
  },
  loadWMSConfig: async () => {
    try {
      const config = await api.fetchWMSConfig();
      set({ wmsConfig: config });
    } catch (e) {
      get().showToast(`Failed to load WMS config: ${e}`, "error");
    }
  },

  // ---- Areas ----
  areas: [],
  areasLoading: false,
  selectedArea: null,
  areaBoundary: null,
  loadAreas: async (category) => {
    set({ areasLoading: true });
    try {
      const data = await api.fetchAreas(category);
      set({ areas: data.areas, areasLoading: false });
    } catch (e) {
      set({ areasLoading: false });
      get().showToast(`Failed to load areas: ${e}`, "error");
    }
  },
  selectArea: (area) => set({ selectedArea: area, areaBoundary: null }),
  setAreaBoundary: (boundary) => set({ areaBoundary: boundary }),

  // ---- Project ----
  projects: [],
  activeProject: null,
  projectLoading: false,
  loadProjects: async () => {
    try {
      const data = await api.fetchProjects();
      set({ projects: data.projects });
    } catch (e) {
      get().showToast(`Failed to load projects: ${e}`, "error");
    }
  },
  loadProject: async (id) => {
    set({ projectLoading: true });
    try {
      const project = await api.fetchProject(id);
      set({ activeProject: project, projectLoading: false });
    } catch (e) {
      set({ projectLoading: false });
      get().showToast(`Failed to load project: ${e}`, "error");
    }
  },
  setActiveProject: (project) => set({ activeProject: project }),

  // ---- Plots ----
  selectedPlotId: null,
  selectPlot: (id) => set({ selectedPlotId: id }),
  updatePlotLabel: async (plotId, label) => {
    const project = get().activeProject;
    if (!project) return;
    try {
      await api.updatePlot(project.id, plotId, { label });
      // Refresh project
      await get().loadProject(project.id);
      get().showToast("Label updated", "success");
    } catch (e) {
      get().showToast(`Failed to update label: ${e}`, "error");
    }
  },
  updatePlotColor: async (plotId, color) => {
    const project = get().activeProject;
    if (!project) return;
    try {
      await api.updatePlot(project.id, plotId, { color });
      await get().loadProject(project.id);
    } catch (e) {
      get().showToast(`Failed to update color: ${e}`, "error");
    }
  },
  removePlot: async (plotId) => {
    const project = get().activeProject;
    if (!project) return;
    try {
      await api.deletePlot(project.id, plotId);
      await get().loadProject(project.id);
      set({ selectedPlotId: null });
      get().showToast("Plot removed", "success");
    } catch (e) {
      get().showToast(`Failed to remove plot: ${e}`, "error");
    }
  },

  // ---- Boundary Editing ----
  editingPlotId: null,
  editingGeometry: null,
  startEditing: (plotId) => {
    const project = get().activeProject;
    if (!project) return;
    const plot = project.plots?.find((p) => p.id === plotId);
    if (!plot) return;
    set({
      editingPlotId: plotId,
      editingGeometry: plot.geometry,
      selectedPlotId: plotId,
    });
  },
  cancelEditing: () => {
    const project = get().activeProject;
    set({ editingPlotId: null, editingGeometry: null });
    // Reload project to restore original geometry on the map
    if (project) {
      get().loadProject(project.id);
    }
  },
  saveEditing: async () => {
    const { editingPlotId, editingGeometry, activeProject, showToast } = get();
    if (!editingPlotId || !editingGeometry || !activeProject) return;
    try {
      await api.updatePlot(activeProject.id, editingPlotId, {
        geometry: editingGeometry,
      });
      set({ editingPlotId: null, editingGeometry: null });
      await get().loadProject(activeProject.id);
      showToast("Boundary updated", "success");
    } catch (e) {
      showToast(`Failed to save boundary: ${e}`, "error");
    }
  },
  updateEditingGeometry: (geom) => {
    set({ editingGeometry: geom });
  },

  // ---- Detection ----
  detecting: false,
  detectionProgress: "",
  runAutoDetect: async (bbox, zoom) => {
    const state = get();
    set({ detecting: true, detectionProgress: "Fetching satellite tiles..." });
    try {
      const area = state.selectedArea;
      const result = await api.autoDetect({
        bbox,
        zoom,
        project_id: state.activeProject?.id,
        project_name: state.activeProject
          ? undefined
          : `Detection - ${area?.name ?? "Custom"}`,
        area_name: area?.name,
        area_category: area?.category,
      });
      set({ detectionProgress: "Detection complete!" });
      await get().loadProject(result.project_id);
      get().showToast(
        `Detected ${result.total} boundaries`,
        "success"
      );
    } catch (e) {
      get().showToast(`Detection failed: ${e}`, "error");
    } finally {
      set({ detecting: false, detectionProgress: "" });
    }
  },
  runPromptDetect: async (points, boxes) => {
    const project = get().activeProject;
    if (!project || !project.bbox) return;
    set({ detecting: true, detectionProgress: "Running prompt detection..." });
    try {
      const result = await api.promptDetect({
        bbox: project.bbox as [number, number, number, number],
        zoom: project.zoom,
        project_id: project.id,
        points,
        boxes,
      });
      await get().loadProject(project.id);
      get().showToast(
        `Detected ${result.total_new} new boundaries`,
        "success"
      );
    } catch (e) {
      get().showToast(`Prompt detection failed: ${e}`, "error");
    } finally {
      set({ detecting: false, detectionProgress: "" });
    }
  },

  // ---- Comparison ----
  comparison: null,
  comparing: false,
  runComparison: async () => {
    const project = get().activeProject;
    if (!project) return;
    set({ comparing: true });
    try {
      const result = await api.runComparison(project.id);
      set({ comparison: result, comparing: false });
      get().showToast("Comparison complete", "success");
    } catch (e) {
      set({ comparing: false });
      get().showToast(`Comparison failed: ${e}`, "error");
    }
  },
  loadComparison: async () => {
    const project = get().activeProject;
    if (!project) return;
    try {
      const result = await api.getComparison(project.id);
      set({ comparison: result });
    } catch {
      // No comparison yet — that's fine
    }
  },

  // ---- Export ----
  exporting: false,
  exportPDF: async () => {
    const project = get().activeProject;
    if (!project) return;
    set({ exporting: true });
    try {
      const blob = await api.exportPDF(project.id);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `drishti-${project.name}.pdf`;
      a.click();
      URL.revokeObjectURL(url);
      get().showToast("PDF exported", "success");
    } catch (e) {
      get().showToast(`PDF export failed: ${e}`, "error");
    } finally {
      set({ exporting: false });
    }
  },
  exportGeoJSON: async () => {
    const project = get().activeProject;
    if (!project) return;
    set({ exporting: true });
    try {
      const geojson = await api.exportGeoJSON(project.id);
      const blob = new Blob([JSON.stringify(geojson, null, 2)], {
        type: "application/json",
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `drishti-${project.name}.geojson`;
      a.click();
      URL.revokeObjectURL(url);
      get().showToast("GeoJSON exported", "success");
    } catch (e) {
      get().showToast(`GeoJSON export failed: ${e}`, "error");
    } finally {
      set({ exporting: false });
    }
  },

  // ---- UI ----
  sidebarTab: "areas",
  setSidebarTab: (tab) => set({ sidebarTab: tab }),
  sidebarOpen: true,
  toggleSidebar: () => set((s) => ({ sidebarOpen: !s.sidebarOpen })),
  toast: null,
  showToast: (message, type = "info") => {
    set({ toast: { message, type } });
    setTimeout(() => {
      set({ toast: null });
    }, 4000);
  },
  clearToast: () => set({ toast: null }),
}));
