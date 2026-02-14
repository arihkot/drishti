import React, { useState, useMemo, useEffect, useRef, useCallback } from "react";
import {
  ArrowLeft,
  ChevronDown,
  ChevronUp,
  ShieldCheck,
  Leaf,
  Clock,
  Loader2,
  Upload,
} from "lucide-react";
import {
  type AreaDashboardData,
  type PlotDetail,
  getMockAreaDashboard,
  getKarmaLabel,
} from "../data/mockData";
import { useStore } from "../stores/useStore";

// Helpers for formatting
const fmt = (n: number) => n.toLocaleString("en-IN");

interface AreaDashboardProps {
  areaName: string;
  onBack: () => void;
  onEnterMap: () => void;
}

/* ------------------------------------------------------------------ */
/*  Helpers                                                             */
/* ------------------------------------------------------------------ */

function formatLeasePeriod(start: string, end: string): string {
  const s = new Date(start);
  const e = new Date(end);
  const years = e.getFullYear() - s.getFullYear();
  return `${years}yr (${s.getFullYear()}\u2013${e.getFullYear()})`;
}

function leaseStatusClasses(status: PlotDetail["leaseStatus"]): string {
  switch (status) {
    case "active":
      return "bg-emerald-100 text-emerald-700";
    case "expired":
      return "bg-red-100 text-red-700";
    case "terminated":
      return "bg-gray-200 text-gray-700";
    case "pending":
      return "bg-yellow-100 text-yellow-700";
    default:
      return "bg-gray-100 text-gray-600";
  }
}

function paymentStatusClasses(status: PlotDetail["paymentStatus"]): string {
  switch (status) {
    case "current":
      return "bg-emerald-100 text-emerald-700";
    case "overdue":
      return "bg-yellow-100 text-yellow-700";
    case "defaulter":
      return "bg-red-100 text-red-700";
    default:
      return "bg-gray-100 text-gray-600";
  }
}

function utilizationStatusClasses(
  status: PlotDetail["utilizationStatus"]
): string {
  switch (status) {
    case "operational":
      return "bg-emerald-100 text-emerald-700";
    case "under_construction":
      return "bg-blue-100 text-blue-700";
    case "partial":
      return "bg-yellow-100 text-yellow-700";
    case "vacant":
      return "bg-red-100 text-red-700";
    default:
      return "bg-gray-100 text-gray-600";
  }
}

function complianceStatusClasses(
  status: PlotDetail["complianceStatus"]
): string {
  switch (status) {
    case "compliant":
      return "bg-emerald-100 text-emerald-700";
    case "under_review":
      return "bg-yellow-100 text-yellow-700";
    case "non_compliant":
      return "bg-red-100 text-red-700";
    default:
      return "bg-gray-100 text-gray-600";
  }
}

function severityClasses(severity: string): string {
  switch (severity) {
    case "low":
      return "bg-green-100 text-green-700";
    case "medium":
      return "bg-yellow-100 text-yellow-700";
    case "high":
      return "bg-orange-100 text-orange-700";
    case "critical":
      return "bg-red-100 text-red-700";
    default:
      return "bg-gray-100 text-gray-600";
  }
}

function prettyStatus(s: string): string {
  return s
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

/* ------------------------------------------------------------------ */
/*  Section wrapper (matches Dashboard)                                */
/* ------------------------------------------------------------------ */
const Section: React.FC<{
  title: string;
  badge?: string;
  children: React.ReactNode;
  className?: string;
}> = ({ title, badge, children, className = "" }) => (
  <div className={`bg-white rounded-xl shadow-sm border border-gray-200 ${className}`}>
    <div className="px-5 py-3.5 border-b border-gray-100 flex items-center gap-2">
      <h2 className="text-sm font-semibold text-gray-800 tracking-wide uppercase">{title}</h2>
      {badge && (
        <span className="text-xs font-normal text-gray-400 ml-1">({badge})</span>
      )}
    </div>
    <div className="p-5">{children}</div>
  </div>
);

/* ------------------------------------------------------------------ */
/*  Component                                                          */
/* ------------------------------------------------------------------ */
const AreaDashboard: React.FC<AreaDashboardProps> = ({
  areaName,
  onBack,
  onEnterMap,
}) => {
  const data: AreaDashboardData = useMemo(
    () => getMockAreaDashboard(areaName),
    [areaName]
  );

  // Real compliance data from the store
  const {
    compliance,
    complianceLoading,
    runComplianceCheck,
    loadCompliance,
    activeProject,
  } = useStore();

  useEffect(() => {
    if (activeProject && !compliance) {
      loadCompliance();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeProject?.id]);

  // ── Drone upload state ────────────────────────────────────────────────────
  const [droneFiles, setDroneFiles] = useState<File[]>([]);
  const [droneDragOver, setDroneDragOver] = useState(false);
  const [droneProcessing, setDroneProcessing] = useState(false);
  const [droneProgress, setDroneProgress] = useState(0);
  const [droneStage, setDroneStage] = useState("");
  const [droneDone, setDroneDone] = useState(false);
  const droneInputRef = useRef<HTMLInputElement>(null);

  const handleDroneFiles = useCallback((files: FileList | null) => {
    if (!files) return;
    const imageFiles = Array.from(files).filter((f) =>
      f.type.startsWith("image/") || /\.(tif|tiff|jpg|jpeg|png)$/i.test(f.name)
    );
    if (imageFiles.length > 0) {
      setDroneFiles(imageFiles);
      setDroneDone(false);
    }
  }, []);

  const handleDroneUpload = useCallback(() => {
    if (droneFiles.length === 0 || droneProcessing) return;
    setDroneProcessing(true);
    setDroneProgress(0);
    setDroneDone(false);

    const stages = [
      { pct: 10, label: "Uploading drone imagery..." },
      { pct: 25, label: "Stitching orthomosaic..." },
      { pct: 40, label: "Georeferencing tiles..." },
      { pct: 55, label: "Aligning with existing basemap..." },
      { pct: 70, label: "Running radiometric correction..." },
      { pct: 85, label: "Generating tile pyramid..." },
      { pct: 95, label: "Finalizing basemap update..." },
    ];

    const duration = 60000;
    const interval = 200;
    const steps = duration / interval;
    let step = 0;

    setDroneStage(stages[0].label);
    const timer = setInterval(() => {
      step++;
      const progress = Math.min(100, Math.round((step / steps) * 100));
      setDroneProgress(progress);

      for (let i = stages.length - 1; i >= 0; i--) {
        if (progress >= stages[i].pct) {
          setDroneStage(stages[i].label);
          break;
        }
      }

      if (step >= steps) {
        clearInterval(timer);
        setDroneProcessing(false);
        setDroneDone(true);
        setDroneStage("");
      }
    }, interval);
  }, [droneFiles, droneProcessing]);

  // Plot table state
  const [plotSearch, setPlotSearch] = useState("");
  const [sortByKarma, setSortByKarma] = useState<"asc" | "desc" | null>("desc");

  const filteredPlots = useMemo(() => {
    let plots = [...data.plotDetails];

    if (plotSearch.trim()) {
      const q = plotSearch.toLowerCase();
      plots = plots.filter(
        (p) =>
          p.plotId.toLowerCase().includes(q) ||
          p.plotNumber.toLowerCase().includes(q) ||
          p.companyName.toLowerCase().includes(q) ||
          p.industryType.toLowerCase().includes(q)
      );
    }

    if (sortByKarma) {
      plots.sort((a, b) =>
        sortByKarma === "asc"
          ? a.karmaScore - b.karmaScore
          : b.karmaScore - a.karmaScore
      );
    }

    return plots;
  }, [data.plotDetails, plotSearch, sortByKarma]);

  // Payment history
  const maxPayment = Math.max(...data.paymentHistory.map((p) => p.amount), 1);

  // Summary stats
  const totalAreaHectares = data.totalArea_sqm / 10_000;
  const avgPlotSize =
    data.plotDetails.length > 0
      ? data.plotDetails.reduce((s, p) => s + p.area_sqm, 0) /
        data.plotDetails.length
      : 0;
  const revenueCollectionRate =
    data.revenueCollected + data.revenuePending > 0
      ? (data.revenueCollected /
          (data.revenueCollected + data.revenuePending)) *
        100
      : 0;
  const defaulterCount = data.plotDetails.filter(
    (p) => p.paymentStatus === "defaulter"
  ).length;
  const avgKarma =
    data.plotDetails.length > 0
      ? data.plotDetails.reduce((s, p) => s + p.karmaScore, 0) /
        data.plotDetails.length
      : 0;

  return (
    <div className="min-h-screen bg-gray-50 pb-12">
      {/* ── Header Bar ──────────────────────────────────────────────────── */}
      <div className="bg-blue-800 shadow-sm">
        <div className="max-w-[1440px] mx-auto px-4 sm:px-6 lg:px-8 py-4">
          <div className="flex items-center justify-between gap-4">
            {/* Left: back + area identity */}
            <div className="flex items-center gap-3 min-w-0">
              <button
                onClick={onBack}
                className="p-2 rounded-lg bg-white/10 hover:bg-white/20 text-white transition-colors flex-shrink-0"
                aria-label="Go back"
              >
                <ArrowLeft className="h-4 w-4" />
              </button>
              <div className="min-w-0">
                <h1 className="text-base font-semibold text-white truncate">
                  {data.name}
                </h1>
                <div className="flex flex-wrap items-center gap-x-3 gap-y-0.5 mt-0.5 text-xs text-blue-200">
                  <span>{data.district}</span>
                  <span className="hidden sm:inline text-blue-300">|</span>
                  <span>{data.category}</span>
                  <span className="hidden sm:inline text-blue-300">|</span>
                  <span>Est. {data.establishedYear}</span>
                  <span className="hidden sm:inline text-blue-300">|</span>
                  <span>{data.managingAuthority}</span>
                </div>
              </div>
            </div>

            {/* Right: map button */}
            <button
              onClick={onEnterMap}
              className="flex items-center gap-2 px-5 py-2.5 bg-white text-blue-800 font-semibold text-sm rounded-lg hover:bg-blue-50 transition-colors flex-shrink-0 active:scale-[0.98]"
            >
              View on Map
            </button>
          </div>
        </div>
      </div>

      {/* ── Main Content ─────────────────────────────────────────────────── */}
      <div className="max-w-[1440px] mx-auto px-4 sm:px-6 lg:px-8 mt-6 space-y-6">

        {/* ── KPI Cards ──────────────────────────────────────────────────── */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {[
            {
              label: "Total Plots",
              value: fmt(data.totalPlots),
              accent: "text-blue-700",
              delta: null,
            },
            {
              label: "Allocated",
              value: fmt(data.allocatedPlots),
              accent: "text-emerald-600",
              delta: {
                value: `${((data.allocatedPlots / data.totalPlots) * 100).toFixed(1)}%`,
                positive: true,
                label: "allocated",
              },
            },
            {
              label: "Vacant",
              value: fmt(data.vacantPlots),
              accent: "text-amber-600",
              delta: {
                value: `${((data.vacantPlots / data.totalPlots) * 100).toFixed(1)}%`,
                positive: false,
                label: "of total",
              },
            },
            {
              label: "Encroachments",
              value: fmt(data.encroachments),
              accent: "text-red-600",
              delta: {
                value: `${((data.encroachments / data.totalPlots) * 100).toFixed(1)}%`,
                positive: false,
                label: "of plots",
              },
            },
            {
              label: "Occupancy Rate",
              value: `${data.occupancyRate}%`,
              accent: data.occupancyRate >= 75 ? "text-emerald-600" : "text-amber-600",
              delta: null,
            },
            {
              label: "Compliance Rate",
              value: `${data.complianceRate}%`,
              accent: data.complianceRate >= 75 ? "text-emerald-600" : "text-amber-600",
              delta: null,
            },
            {
              label: "Revenue Collected",
              value: `₹${fmt(data.revenueCollected)} L`,
              accent: "text-emerald-600",
              delta: {
                value: `₹${fmt(data.revenuePending)} L`,
                positive: false,
                label: "pending",
              },
            },
            {
              label: "Avg Karma Score",
              value: avgKarma.toLocaleString(undefined, { maximumFractionDigits: 1 }),
              accent: avgKarma >= 60 ? "text-emerald-600" : "text-amber-600",
              delta: null,
            },
          ].map((kpi) => (
            <div
              key={kpi.label}
              className="bg-white rounded-xl shadow-sm border border-gray-200 p-4 hover:shadow-md transition-shadow"
            >
              <div className="flex items-start justify-between">
                <p className="text-xs text-gray-500 font-medium">{kpi.label}</p>
                {kpi.delta && (
                  <div
                    className={`flex items-center gap-0.5 text-[11px] font-medium px-1.5 py-0.5 rounded-md ${
                      kpi.delta.positive
                        ? "text-emerald-700 bg-emerald-50"
                        : "text-red-600 bg-red-50"
                    }`}
                  >
                    {kpi.delta.value}{" "}
                    <span className="text-gray-400 font-normal ml-0.5">
                      {kpi.delta.label}
                    </span>
                  </div>
                )}
              </div>
              <p className={`text-2xl font-bold tracking-tight mt-2 ${kpi.accent}`}>
                {kpi.value}
              </p>
            </div>
          ))}
        </div>

        {/* ── Modify Basemap (Drone Survey) ───────────────────────────────── */}
        <Section title="Modify Basemap — Drone Survey">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Drop zone */}
            <div
              className={`relative border-2 border-dashed rounded-xl p-8 text-center transition-all cursor-pointer group ${
                droneDragOver
                  ? "border-blue-500 bg-blue-50"
                  : droneFiles.length > 0
                    ? "border-emerald-400 bg-emerald-50/50"
                    : "border-gray-300 bg-gray-50 hover:border-blue-400 hover:bg-blue-50/30"
              }`}
              onDragOver={(e) => {
                e.preventDefault();
                setDroneDragOver(true);
              }}
              onDragLeave={() => setDroneDragOver(false)}
              onDrop={(e) => {
                e.preventDefault();
                setDroneDragOver(false);
                handleDroneFiles(e.dataTransfer.files);
              }}
              onClick={() => droneInputRef.current?.click()}
            >
              <input
                ref={droneInputRef}
                type="file"
                accept="image/*,.tif,.tiff"
                multiple
                className="hidden"
                onChange={(e) => handleDroneFiles(e.target.files)}
              />
              <div className="flex flex-col items-center gap-3">
                {droneFiles.length > 0 ? (
                  <div>
                    <p className="font-medium text-gray-800">
                      {droneFiles.length} image{droneFiles.length > 1 ? "s" : ""} selected
                    </p>
                    <p className="text-xs text-gray-500 mt-0.5">
                      {droneFiles.map((f) => f.name).join(", ").slice(0, 80)}
                      {droneFiles.map((f) => f.name).join(", ").length > 80 ? "..." : ""}
                      {" "}— Click or drag to replace
                    </p>
                  </div>
                ) : (
                  <div>
                    <p className="font-medium text-gray-700">
                      Drag & drop drone images here, or{" "}
                      <span className="text-blue-700 underline">browse</span>
                    </p>
                    <p className="text-xs text-gray-400 mt-0.5">
                      GeoTIFF, JPEG, or PNG from drone surveys (.tif, .jpg, .png)
                    </p>
                  </div>
                )}
              </div>
            </div>

            {/* Upload action & status */}
            <div className="flex flex-col justify-center gap-4">
              <div className="space-y-3">
                <p className="text-sm text-gray-600 leading-relaxed">
                  Upload drone survey imagery for {areaName} to update the basemap.
                  The system stitches, georeferences, and integrates images into the existing basemap layer.
                </p>
                <button
                  onClick={handleDroneUpload}
                  disabled={droneFiles.length === 0 || droneProcessing}
                  className={`flex items-center justify-center gap-2 w-full sm:w-auto px-6 py-3 rounded-lg font-semibold text-sm transition-colors ${
                    droneFiles.length === 0 || droneProcessing
                      ? "bg-gray-200 text-gray-400 cursor-not-allowed"
                      : "bg-blue-800 text-white hover:bg-blue-700 active:scale-[0.98]"
                  }`}
                >
                  {droneProcessing ? (
                    <>
                      <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                      Processing...
                    </>
                  ) : (
                    <>
                      <Upload className="w-4 h-4" />
                      Upload & Process Imagery
                    </>
                  )}
                </button>
              </div>

              {/* Progress */}
              {droneProcessing && (
                <div className="space-y-2">
                  <div className="flex items-center justify-between text-xs text-gray-600">
                    <span className="flex items-center gap-1.5">
                      <div className="w-3 h-3 border-2 border-blue-600 border-t-transparent rounded-full animate-spin" />
                      {droneStage}
                    </span>
                    <span className="font-mono font-semibold text-blue-800">
                      {droneProgress}%
                    </span>
                  </div>
                  <div className="w-full h-2.5 bg-gray-200 rounded-full overflow-hidden">
                    <div
                      className="h-full bg-blue-600 rounded-full transition-all duration-200 ease-linear"
                      style={{ width: `${droneProgress}%` }}
                    />
                  </div>
                  <div className="text-[11px] text-gray-400">
                    Estimated time remaining: ~{Math.max(1, Math.ceil((100 - droneProgress) * 0.6))}s
                  </div>
                </div>
              )}

              {/* Success */}
              {droneDone && !droneProcessing && (
                <div className="p-3 bg-emerald-50 border border-emerald-200 rounded-lg">
                  <p className="text-sm font-semibold text-emerald-800">
                    Basemap Updated Successfully
                  </p>
                  <p className="text-xs text-emerald-600 mt-0.5">
                    {droneFiles.length} drone image{droneFiles.length > 1 ? "s" : ""} processed
                    and integrated into the basemap for {areaName}. The updated imagery is now available in Map View.
                  </p>
                </div>
              )}
            </div>
          </div>
        </Section>

        {/* ── Compliance Analysis ──────────────────────────────────────── */}
        <Section title="Compliance Analysis" badge={compliance ? `${compliance.total_plots} plots` : undefined}>
          {!compliance && !complianceLoading && (
            <div className="text-center py-6">
              <ShieldCheck className="h-8 w-8 text-gray-300 mx-auto mb-2" />
              <p className="text-sm text-gray-400 mb-3">
                No compliance data yet. Run a check to analyse green cover and construction timelines.
              </p>
              <button
                disabled={!activeProject || complianceLoading}
                onClick={runComplianceCheck}
                className="px-4 py-2 text-sm font-medium text-white bg-emerald-600 rounded-lg hover:bg-emerald-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                Run Compliance Check
              </button>
            </div>
          )}
          {complianceLoading && (
            <div className="flex items-center justify-center py-8">
              <Loader2 className="h-5 w-5 animate-spin text-emerald-500" />
              <span className="ml-2 text-sm text-gray-500">Running compliance checks...</span>
            </div>
          )}
          {compliance && compliance.summary && (
            <div className="space-y-4">
              {/* Summary grid */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                <div className="rounded-lg bg-green-50 border border-green-200 p-3">
                  <p className="text-xs text-green-600 font-medium">Fully Compliant</p>
                  <p className="text-2xl font-bold text-green-700">{compliance.summary.overall.fully_compliant}</p>
                </div>
                <div className="rounded-lg bg-red-50 border border-red-200 p-3">
                  <p className="text-xs text-red-600 font-medium">Non-Compliant</p>
                  <p className="text-2xl font-bold text-red-700">{compliance.summary.overall.non_compliant}</p>
                </div>
                <div className="rounded-lg bg-gray-50 border border-gray-200 p-3">
                  <p className="text-xs text-gray-500 font-medium">Unchecked</p>
                  <p className="text-2xl font-bold text-gray-700">{compliance.summary.overall.unchecked}</p>
                </div>
                <div className="rounded-lg bg-blue-50 border border-blue-200 p-3">
                  <p className="text-xs text-blue-600 font-medium">Total Checked</p>
                  <p className="text-2xl font-bold text-blue-700">{compliance.total_plots}</p>
                </div>
              </div>

              {/* Green cover + Construction timeline side by side */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                {/* Green cover */}
                <div className="rounded-lg border border-gray-200 p-4">
                  <div className="flex items-center gap-2 mb-3">
                    <Leaf className="h-4 w-4 text-green-600" />
                    <h3 className="text-sm font-semibold text-gray-700">Green Cover</h3>
                    <span className="text-xs text-gray-400 ml-auto">
                      min {compliance.summary.green_cover.threshold_pct}%
                    </span>
                  </div>
                  <div className="flex items-center gap-4 mb-2">
                    <div className="flex-1">
                      <div className="flex justify-between text-xs text-gray-500 mb-1">
                        <span>Compliant</span>
                        <span className="font-medium text-green-600">
                          {compliance.summary.green_cover.compliant}
                        </span>
                      </div>
                      <div className="w-full h-2 rounded-full bg-gray-200">
                        <div
                          className="h-2 rounded-full bg-green-500"
                          style={{
                            width: `${
                              compliance.summary.green_cover.checked > 0
                                ? (compliance.summary.green_cover.compliant /
                                    compliance.summary.green_cover.checked) *
                                  100
                                : 0
                            }%`,
                          }}
                        />
                      </div>
                    </div>
                  </div>
                  <div className="flex items-center gap-4">
                    <div className="flex-1">
                      <div className="flex justify-between text-xs text-gray-500 mb-1">
                        <span>Non-compliant</span>
                        <span className="font-medium text-red-600">
                          {compliance.summary.green_cover.non_compliant}
                        </span>
                      </div>
                      <div className="w-full h-2 rounded-full bg-gray-200">
                        <div
                          className="h-2 rounded-full bg-red-500"
                          style={{
                            width: `${
                              compliance.summary.green_cover.checked > 0
                                ? (compliance.summary.green_cover.non_compliant /
                                    compliance.summary.green_cover.checked) *
                                  100
                                : 0
                            }%`,
                          }}
                        />
                      </div>
                    </div>
                  </div>
                  <p className="text-[10px] text-gray-400 mt-2">
                    {compliance.summary.green_cover.checked} of {compliance.total_plots} plots checked
                  </p>
                </div>

                {/* Construction timeline */}
                <div className="rounded-lg border border-gray-200 p-4">
                  <div className="flex items-center gap-2 mb-3">
                    <Clock className="h-4 w-4 text-orange-600" />
                    <h3 className="text-sm font-semibold text-gray-700">Construction Timeline</h3>
                    <span className="text-xs text-gray-400 ml-auto">
                      {compliance.summary.construction_timeline.deadline_years}yr deadline
                    </span>
                  </div>
                  <div className="flex items-center gap-4 mb-2">
                    <div className="flex-1">
                      <div className="flex justify-between text-xs text-gray-500 mb-1">
                        <span>On time</span>
                        <span className="font-medium text-green-600">
                          {compliance.summary.construction_timeline.compliant}
                        </span>
                      </div>
                      <div className="w-full h-2 rounded-full bg-gray-200">
                        <div
                          className="h-2 rounded-full bg-green-500"
                          style={{
                            width: `${
                              compliance.summary.construction_timeline.checked > 0
                                ? (compliance.summary.construction_timeline.compliant /
                                    compliance.summary.construction_timeline.checked) *
                                  100
                                : 0
                            }%`,
                          }}
                        />
                      </div>
                    </div>
                  </div>
                  <div className="flex items-center gap-4">
                    <div className="flex-1">
                      <div className="flex justify-between text-xs text-gray-500 mb-1">
                        <span>Overdue</span>
                        <span className="font-medium text-orange-600">
                          {compliance.summary.construction_timeline.non_compliant}
                        </span>
                      </div>
                      <div className="w-full h-2 rounded-full bg-gray-200">
                        <div
                          className="h-2 rounded-full bg-orange-500"
                          style={{
                            width: `${
                              compliance.summary.construction_timeline.checked > 0
                                ? (compliance.summary.construction_timeline.non_compliant /
                                    compliance.summary.construction_timeline.checked) *
                                  100
                                : 0
                            }%`,
                          }}
                        />
                      </div>
                    </div>
                  </div>
                  <p className="text-[10px] text-gray-400 mt-2">
                    {compliance.summary.construction_timeline.checked} of {compliance.total_plots} plots checked
                  </p>
                </div>
              </div>


            </div>
          )}
        </Section>

        {/* ── Amenities ──────────────────────────────────────────────────── */}
        <Section title="Amenities">
          <div className="flex flex-wrap gap-2.5">
            {data.amenities.map((amenity) => (
              <span
                key={amenity}
                className="px-3 py-2 bg-gray-50 text-gray-700 rounded-lg text-sm font-medium border border-gray-200"
              >
                {amenity}
              </span>
            ))}
          </div>
        </Section>

        {/* ── Plot Details Table ──────────────────────────────────────────── */}
        <Section
          title="Plot Details"
          badge={`${data.plotDetails.length} plots`}
        >
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 mb-4">
            <div className="relative">
              <input
                type="text"
                placeholder="Search plots..."
                value={plotSearch}
                onChange={(e) => setPlotSearch(e.target.value)}
                className="px-3 py-2 text-sm border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent w-56"
              />
            </div>
            <button
              onClick={() =>
                setSortByKarma((prev) =>
                  prev === "desc" ? "asc" : prev === "asc" ? null : "desc"
                )
              }
              className={`flex items-center gap-1 px-3 py-2 text-xs font-medium rounded-lg border transition-colors ${
                sortByKarma
                  ? "bg-blue-50 text-blue-700 border-blue-200"
                  : "bg-gray-50 text-gray-600 border-gray-200 hover:bg-gray-100"
              }`}
            >
              Karma{" "}
              {sortByKarma === "desc" ? (
                <ChevronDown className="h-3 w-3" />
              ) : sortByKarma === "asc" ? (
                <ChevronUp className="h-3 w-3" />
              ) : null}
            </button>
          </div>

          <div className="overflow-x-auto -mx-5 px-5">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs text-gray-500 uppercase tracking-wider">
                  <th className="pb-3 pr-4">Plot ID</th>
                  <th className="pb-3 pr-4">Plot #</th>
                  <th className="pb-3 pr-4">Company</th>
                  <th className="pb-3 pr-4">Industry</th>
                  <th className="pb-3 pr-4 text-right">Area (sqm)</th>
                  <th className="pb-3 pr-4">Lease Period</th>
                  <th className="pb-3 pr-4">Status</th>
                  <th className="pb-3 pr-4 text-right">Monthly Rent</th>
                  <th className="pb-3 pr-4 text-right">Dues</th>
                  <th className="pb-3 pr-4">Payment</th>
                  <th className="pb-3 pr-4 text-center">Karma</th>
                  <th className="pb-3 pr-4">Utilization</th>
                  <th className="pb-3">Compliance</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {filteredPlots.length === 0 ? (
                  <tr>
                    <td
                      colSpan={13}
                      className="py-8 text-center text-gray-400"
                    >
                      No plots match your search.
                    </td>
                  </tr>
                ) : (
                  filteredPlots.map((plot) => {
                    const karma = getKarmaLabel(plot.karmaScore);
                    return (
                      <tr
                        key={plot.plotId}
                        className="hover:bg-gray-50 transition-colors"
                      >
                        <td className="py-3 pr-4 font-mono text-xs text-gray-700 whitespace-nowrap">
                          {plot.plotId}
                        </td>
                        <td className="py-3 pr-4 text-gray-700 whitespace-nowrap">
                          {plot.plotNumber}
                        </td>
                        <td className="py-3 pr-4 text-gray-800 font-medium whitespace-nowrap max-w-[200px] truncate">
                          {plot.companyName}
                        </td>
                        <td className="py-3 pr-4 text-gray-600 whitespace-nowrap">
                          {plot.industryType}
                        </td>
                        <td className="py-3 pr-4 text-gray-700 text-right whitespace-nowrap">
                          {plot.area_sqm.toLocaleString()}
                        </td>
                        <td className="py-3 pr-4 text-gray-600 text-xs whitespace-nowrap">
                          {formatLeasePeriod(
                            plot.leaseStartDate,
                            plot.leaseEndDate
                          )}
                        </td>
                        <td className="py-3 pr-4 whitespace-nowrap">
                          <span
                            className={`px-2 py-0.5 rounded-full text-xs font-medium ${leaseStatusClasses(plot.leaseStatus)}`}
                          >
                            {prettyStatus(plot.leaseStatus)}
                          </span>
                        </td>
                        <td className="py-3 pr-4 text-gray-700 text-right whitespace-nowrap">
                          {plot.monthlyRent.toLocaleString()}
                        </td>
                        <td className="py-3 pr-4 text-right whitespace-nowrap">
                          <span
                            className={
                              plot.totalDues > 0
                                ? "text-red-600 font-semibold"
                                : "text-gray-500"
                            }
                          >
                            {plot.totalDues > 0
                              ? plot.totalDues.toLocaleString()
                              : "\u2014"}
                          </span>
                        </td>
                        <td className="py-3 pr-4 whitespace-nowrap">
                          <span
                            className={`px-2 py-0.5 rounded-full text-xs font-medium ${paymentStatusClasses(plot.paymentStatus)}`}
                          >
                            {prettyStatus(plot.paymentStatus)}
                          </span>
                        </td>
                        <td className="py-3 pr-4 text-center whitespace-nowrap">
                          <span
                            className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold ${karma.bg} ${karma.color}`}
                          >
                            {plot.karmaScore}
                          </span>
                        </td>
                        <td className="py-3 pr-4 whitespace-nowrap">
                          <span
                            className={`px-2 py-0.5 rounded-full text-xs font-medium ${utilizationStatusClasses(plot.utilizationStatus)}`}
                          >
                            {prettyStatus(plot.utilizationStatus)}
                          </span>
                        </td>
                        <td className="py-3 whitespace-nowrap">
                          <span
                            className={`px-2 py-0.5 rounded-full text-xs font-medium ${complianceStatusClasses(plot.complianceStatus)}`}
                          >
                            {prettyStatus(plot.complianceStatus)}
                          </span>
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
        </Section>

        {/* ── Payment History ────────────────────────────────────────────── */}
        <Section title="Payment History">
          <div className="flex items-center gap-4 mb-4 text-xs text-gray-500">
            <span className="flex items-center gap-1.5">
              <span className="w-3 h-3 rounded-sm bg-blue-600 inline-block" />
              Collected (₹ Lakhs)
            </span>
            <span className="flex items-center gap-1.5">
              <span className="w-3 h-3 rounded-sm bg-amber-400 inline-block" />
              Partial (₹ Lakhs)
            </span>
          </div>
          <div className="flex items-end gap-3 h-48">
            {data.paymentHistory.map((entry) => {
              const heightPct = (entry.amount / maxPayment) * 100;
              const isPartial = entry.status === "partial";
              return (
                <div
                  key={entry.month}
                  className="flex-1 flex flex-col items-center gap-1 h-full justify-end"
                >
                  <span className="text-[10px] font-semibold text-gray-700">
                    {entry.amount.toLocaleString()} L
                  </span>
                  <div className="w-full flex-1 relative flex items-end">
                    <div
                      className={`w-full rounded-t-sm transition-all duration-500 ${
                        isPartial ? "bg-amber-400" : "bg-blue-600"
                      }`}
                      style={{ height: `${heightPct}%` }}
                    />
                  </div>
                  <span className="text-[10px] text-gray-400 text-center whitespace-nowrap">
                    {entry.month.split(" ")[0].slice(0, 3)}
                  </span>
                </div>
              );
            })}
          </div>
        </Section>

        {/* ── Encroachment Details ────────────────────────────────────────── */}
        <Section
          title="Encroachment Details"
          badge={`${data.encroachmentDetails.length} detected`}
        >
          {data.encroachmentDetails.length === 0 ? (
            <p className="text-center text-gray-400 text-sm py-4">
              No encroachments detected in this area.
            </p>
          ) : (
            <div className="overflow-x-auto -mx-5 px-5">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-xs text-gray-500 uppercase tracking-wider">
                    <th className="pb-3 pr-4">Plot ID</th>
                    <th className="pb-3 pr-4">Type</th>
                    <th className="pb-3 pr-4 text-right">Area (sqm)</th>
                    <th className="pb-3 pr-4">Severity</th>
                    <th className="pb-3">Detected Date</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {data.encroachmentDetails.map((enc, idx) => (
                    <tr
                      key={`${enc.plotId}-${idx}`}
                      className="hover:bg-gray-50 transition-colors"
                    >
                      <td className="py-3 pr-4 font-mono text-xs text-gray-700">
                        {enc.plotId}
                      </td>
                      <td className="py-3 pr-4 text-gray-700">
                        {enc.type}
                      </td>
                      <td className="py-3 pr-4 text-gray-700 text-right">
                        {enc.area_sqm.toLocaleString()}
                      </td>
                      <td className="py-3 pr-4">
                        <span
                          className={`px-2 py-0.5 rounded-full text-xs font-medium capitalize ${severityClasses(enc.severity)}`}
                        >
                          {enc.severity}
                        </span>
                      </td>
                      <td className="py-3 text-gray-600">
                        {new Date(enc.detectedDate).toLocaleDateString(
                          "en-IN",
                          {
                            day: "2-digit",
                            month: "short",
                            year: "numeric",
                          }
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Section>

        {/* ── Summary Stats Footer ───────────────────────────────────────── */}
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-4">
          <SummaryCard label="Total Area" value={`${totalAreaHectares.toLocaleString(undefined, { maximumFractionDigits: 1 })} ha`} />
          <SummaryCard label="Avg Plot Size" value={`${avgPlotSize.toLocaleString(undefined, { maximumFractionDigits: 0 })} sqm`} />
          <SummaryCard label="Collection Rate" value={`${revenueCollectionRate.toLocaleString(undefined, { maximumFractionDigits: 1 })}%`} />
          <SummaryCard label="Defaulters" value={defaulterCount.toLocaleString()} />
          <SummaryCard label="Avg Karma Score" value={avgKarma.toLocaleString(undefined, { maximumFractionDigits: 1 })} />
        </div>
      </div>
    </div>
  );
};

/* ------------------------------------------------------------------ */
/*  Sub-components                                                     */
/* ------------------------------------------------------------------ */

const SummaryCard: React.FC<{
  label: string;
  value: string;
}> = ({ label, value }) => (
  <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-4">
    <p className="text-xs text-gray-500">{label}</p>
    <p className="text-lg font-bold text-gray-900 mt-0.5">{value}</p>
  </div>
);

export default AreaDashboard;
