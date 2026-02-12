import React, { useEffect, useMemo, useState } from "react";
import {
  Map,
  Layers,
  GitCompare,
  Download,
  Search,
  Trash2,
  Edit3,
  ChevronRight,
  Loader2,
  MapPin,
  Building2,
  Move,
  Save,
  X,
} from "lucide-react";
import { useStore } from "../stores/useStore";

const CATEGORY_COLORS: Record<string, string> = {
  plot: "#ef4444",
  road: "#64748b",
  boundary: "#f97316",
};

const SEVERITY_COLORS: Record<string, string> = {
  low: "bg-green-100 text-green-800",
  medium: "bg-yellow-100 text-yellow-800",
  high: "bg-orange-100 text-orange-800",
  critical: "bg-red-100 text-red-800",
};

const AREA_CATEGORIES = ["All", "Industrial", "Old Industrial", "Directorate"];

const TABS = [
  { key: "areas" as const, icon: Map, label: "Browse Industrial Areas" },
  { key: "plots" as const, icon: Layers, label: "Detected Plots" },
  { key: "compare" as const, icon: GitCompare, label: "Comparison" },
  { key: "export" as const, icon: Download, label: "Export" },
];

/* ------------------------------------------------------------------ */
/*  Areas Panel                                                       */
/* ------------------------------------------------------------------ */
const AreasPanel: React.FC<{ onViewArea?: (areaName: string) => void }> = ({ onViewArea }) => {
  const {
    areas,
    areasLoading,
    selectedArea,
    areaBoundary,
    loadAreas,
    selectArea,
    detecting,
    runAutoDetect,
    mapExtent,
    mapZoom,
  } = useStore();

  const [search, setSearch] = useState("");
  const [categoryFilter, setCategoryFilter] = useState("All");

  useEffect(() => {
    loadAreas();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const filtered = useMemo(() => {
    return areas.filter((a) => {
      const matchesSearch = a.name
        .toLowerCase()
        .includes(search.toLowerCase());
      const matchesCategory =
        categoryFilter === "All" ||
        a.category.toLowerCase() === categoryFilter.toLowerCase();
      return matchesSearch && matchesCategory;
    });
  }, [areas, search, categoryFilter]);

  return (
    <div className="flex flex-col h-full">
      {/* Search */}
      <div className="p-3 border-b border-gray-200">
        <div className="relative">
          <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-gray-400" />
          <input
            type="text"
            placeholder="Search areas..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full pl-9 pr-3 py-2 text-sm border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
          />
        </div>
      </div>

      {/* Category filters */}
      <div className="flex flex-wrap gap-1.5 p-3 border-b border-gray-200">
        {AREA_CATEGORIES.map((cat) => (
          <button
            key={cat}
            onClick={() => setCategoryFilter(cat)}
            className={`px-2.5 py-1 text-xs font-medium rounded-full transition-colors ${
              categoryFilter === cat
                ? "bg-blue-600 text-white"
                : "bg-gray-100 text-gray-600 hover:bg-gray-200"
            }`}
          >
            {cat}
          </button>
        ))}
      </div>

      {/* Area count */}
      <div className="px-3 py-2 text-xs text-gray-500 border-b border-gray-100">
        {filtered.length} area{filtered.length !== 1 ? "s" : ""} found
      </div>

      {/* Area list */}
      <div className="flex-1 overflow-y-auto custom-scrollbar">
        {areasLoading ? (
          <div className="flex items-center justify-center py-12">
            <Loader2 className="h-5 w-5 animate-spin text-blue-500" />
            <span className="ml-2 text-sm text-gray-500">
              Loading areas...
            </span>
          </div>
        ) : filtered.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-12 text-gray-400">
            <MapPin className="h-8 w-8 mb-2" />
            <p className="text-sm">No areas found</p>
          </div>
        ) : (
          filtered.map((area) => {
            const isSelected = selectedArea?.name === area.name;
            return (
              <button
                key={area.name}
                onClick={() => selectArea(area)}
                className={`w-full text-left px-3 py-2.5 flex items-center gap-2.5 border-b border-gray-100 transition-colors ${
                  isSelected
                    ? "bg-blue-50 border-l-2 border-l-blue-600"
                    : "hover:bg-gray-50"
                }`}
              >
                <Building2
                  className={`h-4 w-4 flex-shrink-0 ${
                    isSelected ? "text-blue-600" : "text-gray-400"
                  }`}
                />
                <div className="flex-1 min-w-0">
                  <p
                    className={`text-sm font-medium truncate ${
                      isSelected ? "text-blue-900" : "text-gray-800"
                    }`}
                  >
                    {area.name}
                  </p>
                  <p className="text-xs text-gray-400 mt-0.5">
                    {area.category}
                  </p>
                </div>
                <ChevronRight
                  className={`h-4 w-4 flex-shrink-0 ${
                    isSelected ? "text-blue-400" : "text-gray-300"
                  }`}
                />
              </button>
            );
          })
        )}
      </div>

      {/* Selected area action */}
      {selectedArea && (
        <div className="p-3 border-t border-gray-200 bg-gray-50">
          <p className="text-xs text-gray-500 mb-1">Selected</p>
          <p className="text-sm font-semibold text-gray-800 truncate mb-2">
            {selectedArea.name}
          </p>
          <button
            disabled={detecting}
            onClick={() => {
              if (!selectedArea) return;
              // Use area boundary bbox if available, fall back to map viewport
              let bbox: [number, number, number, number];
              if (areaBoundary?.geometry?.coordinates) {
                // Deep-flatten coordinates to get all [lon, lat] pairs
                // Works for Polygon (number[][][]) and MultiPolygon (number[][][][])
                const flattenCoords = (arr: unknown): number[][] => {
                  if (
                    Array.isArray(arr) &&
                    arr.length >= 2 &&
                    typeof arr[0] === "number"
                  ) {
                    return [arr as number[]];
                  }
                  if (Array.isArray(arr)) {
                    return arr.flatMap((item) => flattenCoords(item));
                  }
                  return [];
                };
                const allPairs = flattenCoords(areaBoundary.geometry.coordinates);
                if (allPairs.length > 0) {
                  const lons = allPairs.map((c) => c[0]);
                  const lats = allPairs.map((c) => c[1]);
                  bbox = [
                    Math.min(...lons),
                    Math.min(...lats),
                    Math.max(...lons),
                    Math.max(...lats),
                  ];
                } else {
                  bbox = mapExtent ?? [0, 0, 0, 0];
                }
              } else {
                bbox = mapExtent ?? [0, 0, 0, 0];
              }
              const zoom = mapZoom ?? 18;
              runAutoDetect(bbox, zoom);
            }}
            className="w-full flex items-center justify-center gap-2 px-3 py-2 text-sm font-medium text-white bg-blue-600 rounded-md hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {detecting ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" />
                Detecting...
              </>
            ) : (
              <>
                <Layers className="h-4 w-4" />
                Detect Boundaries
              </>
            )}
          </button>
          {onViewArea && (
            <button
              onClick={() => onViewArea(selectedArea.name)}
              className="w-full flex items-center justify-center gap-2 px-3 py-2 text-sm font-medium text-blue-700 bg-blue-50 rounded-md hover:bg-blue-100 border border-blue-200 transition-colors mt-2"
            >
              View Dashboard
            </button>
          )}
        </div>
      )}
    </div>
  );
};

/* ------------------------------------------------------------------ */
/*  Plots Panel                                                       */
/* ------------------------------------------------------------------ */
const PlotsPanel: React.FC = () => {
  const {
    activeProject,
    selectedPlotId,
    selectPlot,
    updatePlotLabel,
    removePlot,
    editingPlotId,
    startEditing,
    cancelEditing,
    saveEditing,
  } = useStore();

  const [editingId, setEditingId] = useState<number | null>(null);
  const [editValue, setEditValue] = useState("");

  const isEditingBoundary = editingPlotId !== null;

  if (!activeProject) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-gray-400 px-6">
        <Layers className="h-10 w-10 mb-3" />
        <p className="text-sm font-medium text-gray-500">No project active</p>
        <p className="text-xs text-center mt-1">
          Select an area and run detection first to see detected plots.
        </p>
      </div>
    );
  }

  const plots = activeProject.plots ?? [];

  const totalArea = plots.reduce((sum, p) => sum + (p.area_sqft ?? 0), 0);

  const startEdit = (plot: { id: number; label: string }) => {
    if (isEditingBoundary) return; // Block label editing during boundary edit
    setEditingId(plot.id);
    setEditValue(plot.label);
  };

  const commitEdit = async () => {
    if (editingId !== null && editValue.trim()) {
      await updatePlotLabel(editingId, editValue.trim());
    }
    setEditingId(null);
  };

  return (
    <div className="flex flex-col h-full">
      {/* Summary */}
      <div className="p-3 border-b border-gray-200 bg-gray-50">
        <div className="grid grid-cols-2 gap-3">
          <div>
            <p className="text-xs text-gray-500">Total Plots</p>
            <p className="text-lg font-bold text-gray-800">{plots.length}</p>
          </div>
          <div>
            <p className="text-xs text-gray-500">Total Area</p>
            <p className="text-lg font-bold text-gray-800">
              {totalArea.toLocaleString(undefined, {
                maximumFractionDigits: 0,
              })}{" "}
              <span className="text-xs font-normal text-gray-500">sqft</span>
            </p>
          </div>
        </div>
      </div>

      {/* Editing mode banner */}
      {isEditingBoundary && (
        <div className="p-3 bg-cyan-50 border-b border-cyan-200">
          <div className="flex items-center gap-2 mb-2">
            <Move className="h-4 w-4 text-cyan-600" />
            <p className="text-sm font-medium text-cyan-800">
              Editing Boundary
            </p>
          </div>
          <p className="text-xs text-cyan-600 mb-3">
            Drag vertices on the map to adjust the boundary. Press Esc to cancel, Cmd/Ctrl+S to save.
          </p>
          <div className="flex gap-2">
            <button
              onClick={saveEditing}
              className="flex-1 flex items-center justify-center gap-1.5 px-3 py-2 text-sm font-medium text-white bg-cyan-600 rounded-md hover:bg-cyan-700 transition-colors"
            >
              <Save className="h-3.5 w-3.5" />
              Save
            </button>
            <button
              onClick={cancelEditing}
              className="flex-1 flex items-center justify-center gap-1.5 px-3 py-2 text-sm font-medium text-gray-700 bg-gray-200 rounded-md hover:bg-gray-300 transition-colors"
            >
              <X className="h-3.5 w-3.5" />
              Cancel
            </button>
          </div>
        </div>
      )}

      {/* Plot list */}
      <div className="flex-1 overflow-y-auto custom-scrollbar">
        {plots.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-12 text-gray-400">
            <Layers className="h-8 w-8 mb-2" />
            <p className="text-sm">No plots detected yet</p>
          </div>
        ) : (
          plots.map((plot) => {
            const isSelected = selectedPlotId === plot.id;
            const isThisEditing = editingPlotId === plot.id;
            const color =
              CATEGORY_COLORS[plot.category] ?? plot.color ?? "#9E9E9E";

            return (
              <div
                key={plot.id}
                onClick={() => {
                  if (!isEditingBoundary) selectPlot(plot.id);
                }}
                className={`flex items-center gap-2.5 px-3 py-2.5 border-b border-gray-100 transition-colors ${
                  isEditingBoundary && !isThisEditing
                    ? "opacity-40 cursor-default"
                    : isEditingBoundary && isThisEditing
                    ? "bg-cyan-50 border-l-2 border-l-cyan-500 cursor-default"
                    : isSelected
                    ? "bg-blue-50 border-l-2 border-l-blue-600 cursor-pointer"
                    : "hover:bg-gray-50 cursor-pointer"
                }`}
              >
                {/* Color swatch */}
                <span
                  className="w-3 h-3 rounded-full flex-shrink-0 ring-1 ring-black/10"
                  style={{ backgroundColor: isThisEditing ? "#00c8ff" : color }}
                />

                {/* Label / edit */}
                <div className="flex-1 min-w-0">
                  {editingId === plot.id ? (
                    <input
                      autoFocus
                      value={editValue}
                      onChange={(e) => setEditValue(e.target.value)}
                      onBlur={commitEdit}
                      onKeyDown={(e) => {
                        if (e.key === "Enter") commitEdit();
                        if (e.key === "Escape") setEditingId(null);
                      }}
                      className="w-full text-sm px-1.5 py-0.5 border border-blue-400 rounded focus:outline-none focus:ring-1 focus:ring-blue-500"
                    />
                  ) : (
                    <p
                      className={`text-sm font-medium truncate ${
                        isThisEditing ? "text-cyan-800" : "text-gray-800"
                      }`}
                      onDoubleClick={() => startEdit(plot)}
                      title={isEditingBoundary ? undefined : "Double-click to edit"}
                    >
                      {plot.label}
                    </p>
                  )}
                  <div className="flex items-center gap-2 mt-0.5">
                    <span
                      className="text-[10px] font-medium px-1.5 py-0.5 rounded-full"
                      style={{
                        backgroundColor: `${color}20`,
                        color: color,
                      }}
                    >
                      {plot.category}
                    </span>
                    {plot.area_sqft != null && (
                      <span className="text-xs text-gray-400">
                        {plot.area_sqft.toLocaleString(undefined, {
                          maximumFractionDigits: 0,
                        })}{" "}
                        sqft
                      </span>
                    )}
                  </div>
                </div>

                {/* Actions */}
                {!isEditingBoundary && (
                  <div className="flex items-center gap-1 flex-shrink-0">
                    {isSelected && (
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          startEditing(plot.id);
                        }}
                        className="p-1 rounded hover:bg-cyan-100 text-gray-400 hover:text-cyan-600 transition-colors"
                        title="Edit boundary"
                      >
                        <Move className="h-3.5 w-3.5" />
                      </button>
                    )}
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        startEdit(plot);
                      }}
                      className="p-1 rounded hover:bg-gray-200 text-gray-400 hover:text-gray-600 transition-colors"
                      title="Edit label"
                    >
                      <Edit3 className="h-3.5 w-3.5" />
                    </button>
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        removePlot(plot.id);
                      }}
                      className="p-1 rounded hover:bg-red-100 text-gray-400 hover:text-red-600 transition-colors"
                      title="Delete plot"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  </div>
                )}
              </div>
            );
          })
        )}
      </div>
    </div>
  );
};

/* ------------------------------------------------------------------ */
/*  Compare Panel                                                     */
/* ------------------------------------------------------------------ */
const DEVIATION_TYPE_COLORS: Record<string, string> = {
  ENCROACHMENT: "bg-red-100 text-red-700",
  UNAUTHORIZED_DEVELOPMENT: "bg-orange-100 text-orange-700",
  BOUNDARY_MISMATCH: "bg-yellow-100 text-yellow-700",
  VACANT: "bg-purple-100 text-purple-700",
  COMPLIANT: "bg-green-100 text-green-700",
};

const ComparePanel: React.FC = () => {
  const { activeProject, comparison, comparing, runComparison } = useStore();

  const hasPlots =
    activeProject && activeProject.plots && activeProject.plots.length > 0;
  const canRun = !!activeProject && !!hasPlots && !comparing;

  return (
    <div className="flex flex-col h-full">
      {/* Run button */}
      <div className="p-3 border-b border-gray-200">
        <button
          disabled={!canRun}
          onClick={runComparison}
          className="w-full flex items-center justify-center gap-2 px-3 py-2.5 text-sm font-medium text-white bg-indigo-600 rounded-md hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          {comparing ? (
            <>
              <Loader2 className="h-4 w-4 animate-spin" />
              Comparing...
            </>
          ) : (
            <>
              <GitCompare className="h-4 w-4" />
              Run Comparison
            </>
          )}
        </button>
        {!activeProject && (
          <p className="text-xs text-gray-400 mt-2 text-center">
            No active project. Run detection first.
          </p>
        )}
        {activeProject && !hasPlots && (
          <p className="text-xs text-gray-400 mt-2 text-center">
            No plots detected yet. Run detection first.
          </p>
        )}
      </div>

      {/* Results */}
      {comparison && (
        <div className="flex-1 overflow-y-auto custom-scrollbar">
          {/* Summary cards */}
          <div className="grid grid-cols-2 gap-2 p-3 border-b border-gray-200">
            <SummaryCard label="Total Detected" value={comparison.summary.total_detected} color="bg-gray-100 text-gray-800" />
            <SummaryCard label="Total Basemap" value={comparison.summary.total_basemap} color="bg-gray-100 text-gray-800" />
            <SummaryCard label="Compliant" value={comparison.summary.compliant} color="bg-green-100 text-green-800" />
            <SummaryCard label="Encroachment" value={comparison.summary.encroachment} color="bg-red-100 text-red-800" />
            <SummaryCard label="Boundary Mismatch" value={comparison.summary.boundary_mismatch} color="bg-yellow-100 text-yellow-800" />
            <SummaryCard label="Vacant" value={comparison.summary.vacant} color="bg-purple-100 text-purple-800" />
            <SummaryCard label="Unauthorized" value={comparison.summary.unauthorized} color="bg-orange-100 text-orange-800" />
            <SummaryCard label="Unmatched" value={comparison.summary.unmatched_detected} color="bg-slate-100 text-slate-800" />
          </div>

          {/* Deviations list */}
          <div className="p-3">
            <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">
              Deviations ({comparison.deviations.length})
            </p>
            {comparison.deviations.length === 0 ? (
              <p className="text-sm text-gray-400 text-center py-4">
                No deviations found.
              </p>
            ) : (
              <div className="space-y-2">
                {comparison.deviations.map((dev) => (
                  <div
                    key={dev.id}
                    className="rounded-lg border border-gray-200 p-2.5"
                  >
                    <div className="flex items-center gap-2 mb-1">
                      <span
                        className={`text-[10px] font-semibold px-1.5 py-0.5 rounded-full ${
                          DEVIATION_TYPE_COLORS[dev.deviation_type] ??
                          "bg-gray-100 text-gray-700"
                        }`}
                      >
                        {dev.deviation_type.replace(/_/g, " ")}
                      </span>
                      <span
                        className={`text-[10px] font-medium px-1.5 py-0.5 rounded-full ${
                          SEVERITY_COLORS[dev.severity] ??
                          "bg-gray-100 text-gray-700"
                        }`}
                      >
                        {dev.severity}
                      </span>
                    </div>
                    {dev.deviation_area_sqm != null && (
                      <p className="text-xs text-gray-500">
                        Area:{" "}
                        {dev.deviation_area_sqm.toLocaleString(undefined, {
                          maximumFractionDigits: 1,
                        })}{" "}
                        sqm
                      </p>
                    )}
                    {dev.description && (
                      <p className="text-xs text-gray-600 mt-1">
                        {dev.description}
                      </p>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {/* Empty state when no comparison yet */}
      {!comparison && !comparing && (
        <div className="flex flex-col items-center justify-center flex-1 text-gray-400 px-6">
          <GitCompare className="h-10 w-10 mb-3" />
          <p className="text-xs text-center">
            Run a comparison to see how detected plots align with official
            records.
          </p>
        </div>
      )}
    </div>
  );
};

const SummaryCard: React.FC<{
  label: string;
  value: number;
  color: string;
}> = ({ label, value, color }) => (
  <div className={`rounded-lg px-3 py-2 ${color}`}>
    <p className="text-[10px] font-medium opacity-70">{label}</p>
    <p className="text-lg font-bold">{value}</p>
  </div>
);

/* ------------------------------------------------------------------ */
/*  Export Panel                                                      */
/* ------------------------------------------------------------------ */
const ExportPanel: React.FC = () => {
  const { activeProject, exporting, exportPDF, exportGeoJSON } = useStore();

  return (
    <div className="flex flex-col h-full">
      {/* Project info */}
      {activeProject && (
        <div className="p-3 border-b border-gray-200 bg-gray-50">
          <p className="text-xs text-gray-500">Active Project</p>
          <p className="text-sm font-semibold text-gray-800 truncate">
            {activeProject.name}
          </p>
          {activeProject.area_name && (
            <p className="text-xs text-gray-400 mt-0.5">
              {activeProject.area_name}
            </p>
          )}
          <p className="text-xs text-gray-400 mt-0.5">
            {activeProject.plots?.length ?? 0} plots &middot; Created{" "}
            {new Date(activeProject.created_at).toLocaleDateString()}
          </p>
        </div>
      )}

      {/* Buttons */}
      <div className="p-3 space-y-2">
        <button
          disabled={!activeProject || exporting}
          onClick={exportPDF}
          className="w-full flex items-center justify-center gap-2 px-3 py-2.5 text-sm font-medium text-white bg-rose-600 rounded-md hover:bg-rose-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          {exporting ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Download className="h-4 w-4" />
          )}
          Export PDF
        </button>

        <button
          disabled={!activeProject || exporting}
          onClick={exportGeoJSON}
          className="w-full flex items-center justify-center gap-2 px-3 py-2.5 text-sm font-medium text-white bg-emerald-600 rounded-md hover:bg-emerald-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          {exporting ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Download className="h-4 w-4" />
          )}
          Export GeoJSON
        </button>
      </div>

      {!activeProject && (
        <div className="flex flex-col items-center justify-center flex-1 text-gray-400 px-6">
          <Download className="h-10 w-10 mb-3" />
          <p className="text-xs text-center">
            No active project. Run detection first to enable exports.
          </p>
        </div>
      )}
    </div>
  );
};

/* ------------------------------------------------------------------ */
/*  Sidebar                                                           */
/* ------------------------------------------------------------------ */
interface SidebarProps {
  onViewArea?: (areaName: string) => void;
}

const Sidebar: React.FC<SidebarProps> = ({ onViewArea }) => {
  const { sidebarTab, setSidebarTab } = useStore();

  return (
    <div className="w-80 h-full flex flex-col bg-white shadow-lg border-r border-gray-200">
      {/* Tab bar */}
      <div className="flex border-b border-gray-200">
        {TABS.map((tab) => {
          const Icon = tab.icon;
          const isActive = sidebarTab === tab.key;
          return (
            <button
              key={tab.key}
              onClick={() => setSidebarTab(tab.key)}
              className={`flex-1 flex flex-col items-center gap-1 py-2.5 text-[10px] font-medium transition-colors ${
                isActive
                  ? "text-blue-600 border-b-2 border-blue-600 bg-blue-50/50"
                  : "text-gray-500 hover:text-gray-700 hover:bg-gray-50"
              }`}
              title={tab.label}
            >
              <Icon className="h-4 w-4" />
              {tab.label.split(" ")[0]}
            </button>
          );
        })}
      </div>

      {/* Panel content */}
      <div className="flex-1 overflow-y-auto custom-scrollbar">
        {sidebarTab === "areas" && <AreasPanel onViewArea={onViewArea} />}
        {sidebarTab === "plots" && <PlotsPanel />}
        {sidebarTab === "compare" && <ComparePanel />}
        {sidebarTab === "export" && <ExportPanel />}
      </div>
    </div>
  );
};

export default Sidebar;
