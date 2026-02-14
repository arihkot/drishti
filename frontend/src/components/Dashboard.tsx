import React, { useState, useRef, useCallback, useEffect } from "react";
import {
  ChevronRight,
  ArrowUpRight,
  ArrowDownRight,
  ChevronDown,
  ChevronUp,
  LogOut,
  Upload,
  ShieldCheck,
  Leaf,
  Clock,
  AlertTriangle,
  Bell,
  X,
  MapPin,
  Download,
} from "lucide-react";
import {
  type DashboardStats,
  getPdfProcessingUpdates,
  getKarmaLabel,
} from "../data/mockData";
import { useStore } from "../stores/useStore";
import * as api from "../api/client";

// ─── Prop types ──────────────────────────────────────────────────────────────

interface DashboardProps {
  user: {
    name: string;
    role: string;
    department: string;
    designation: string;
    employee_id: string;
  };
  onEnterMap: () => void;
  onViewArea: (areaName: string) => void;
  onLogout: () => void;
  stats: DashboardStats;
  setStats: React.Dispatch<React.SetStateAction<DashboardStats>>;
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

const fmt = (n: number) => n.toLocaleString("en-IN");
const fmtDec = (n: number, d = 1) =>
  n.toLocaleString("en-IN", { minimumFractionDigits: d, maximumFractionDigits: d });
const hectares = (sqm: number) => (sqm / 10000).toFixed(0);

const STATUS_COLORS: Record<string, string> = {
  completed: "bg-emerald-100 text-emerald-700",
  flagged: "bg-red-100 text-red-700",
  in_progress: "bg-yellow-100 text-yellow-700",
  pending: "bg-gray-100 text-gray-600",
  approved: "bg-blue-100 text-blue-700",
  sent: "bg-blue-100 text-blue-700",
};

// ─── Section wrapper ─────────────────────────────────────────────────────────

const Section: React.FC<{
  title: string;
  children: React.ReactNode;
  className?: string;
}> = ({ title, children, className = "" }) => (
  <div className={`bg-white rounded-xl shadow-sm border border-gray-200 ${className}`}>
    <div className="px-5 py-3.5 border-b border-gray-100">
      <h2 className="text-sm font-semibold text-gray-800 tracking-wide uppercase">{title}</h2>
    </div>
    <div className="p-5">{children}</div>
  </div>
);

// ─── Dashboard Component ─────────────────────────────────────────────────────

const Dashboard: React.FC<DashboardProps> = ({
  user,
  onEnterMap,
  onViewArea,
  onLogout,
  stats,
  setStats,
}) => {
  // ── PDF upload state ────────────────────────────────────────────────────────
  const [pdfFile, setPdfFile] = useState<File | null>(null);
  const [pdfDragOver, setPdfDragOver] = useState(false);
  const [pdfUploading, setPdfUploading] = useState(false);
  const [pdfProgress, setPdfProgress] = useState(0);
  const [pdfDone, setPdfDone] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // ── Drone upload state ────────────────────────────────────────────────────
  const [droneFiles, setDroneFiles] = useState<File[]>([]);
  const [droneDragOver, setDroneDragOver] = useState(false);
  const [droneProcessing, setDroneProcessing] = useState(false);
  const [droneProgress, setDroneProgress] = useState(0);
  const [droneStage, setDroneStage] = useState("");
  const [droneDone, setDroneDone] = useState(false);
  const droneInputRef = useRef<HTMLInputElement>(null);

  // ── Area sort state ───────────────────────────────────────────────────────
  const [areaSortKey, setAreaSortKey] = useState<
    "name" | "plots" | "occupancy" | "revenueCollected"
  >("revenueCollected");
  const [areaSortDir, setAreaSortDir] = useState<"asc" | "desc">("desc");

  // ── Last login ──────────────────────────────────────────────────────────────
  const [lastLogin] = useState(() => {
    const d = new Date();
    d.setHours(d.getHours() - 2);
    return d;
  });

  // ── Compliance data from store ──────────────────────────────────────────────
  const compliance = useStore((s) => s.compliance);

  // ── Notifications ─────────────────────────────────────────────────────────
  const notifications = useStore((s) => s.notifications);
  const initNotifications = useStore((s) => s.initNotifications);
  const markNotificationRead = useStore((s) => s.markNotificationRead);
  const markAllNotificationsRead = useStore((s) => s.markAllNotificationsRead);
  const dismissNotification = useStore((s) => s.dismissNotification);
  const [notifOpen, setNotifOpen] = useState(false);
  const notifRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    initNotifications();
  }, [initNotifications]);

  // Close dropdown on outside click
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (notifRef.current && !notifRef.current.contains(e.target as Node)) {
        setNotifOpen(false);
      }
    };
    if (notifOpen) document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [notifOpen]);

  const unreadCount = notifications.filter((n) => !n.read).length;

  // ── Dashboard PDF export ───────────────────────────────────────────────────
  const [dashExporting, setDashExporting] = useState(false);
  const showToast = useStore((s) => s.showToast);

  const handleExportDashboardPDF = useCallback(async () => {
    setDashExporting(true);
    try {
      const blob = await api.exportDashboardPDF(
        stats as unknown as Record<string, unknown>,
        { name: user.name, role: user.role, department: user.department, designation: user.designation }
      );
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `drishti-dashboard-${new Date().toISOString().slice(0, 10)}.pdf`;
      a.click();
      URL.revokeObjectURL(url);
      showToast("Dashboard PDF exported", "success");
    } catch (e) {
      showToast(`Dashboard PDF export failed: ${e}`, "error");
    } finally {
      setDashExporting(false);
    }
  }, [stats, user, showToast]);

  // ── PDF upload logic ────────────────────────────────────────────────────────
  const handleFileSelect = useCallback((file: File) => {
    if (file.type === "application/pdf" || file.name.endsWith(".pdf")) {
      setPdfFile(file);
      setPdfDone(false);
    }
  }, []);

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setPdfDragOver(false);
      const file = e.dataTransfer.files?.[0];
      if (file) handleFileSelect(file);
    },
    [handleFileSelect],
  );

  const handleUpload = useCallback(() => {
    if (!pdfFile || pdfUploading) return;
    setPdfUploading(true);
    setPdfProgress(0);
    setPdfDone(false);

    const duration = 4000;
    const interval = 50;
    const steps = duration / interval;
    let step = 0;

    const timer = setInterval(() => {
      step++;
      const progress = Math.min(100, Math.round((step / steps) * 100));
      setPdfProgress(progress);

      if (step >= steps) {
        clearInterval(timer);
        const updates = getPdfProcessingUpdates();
        setStats((prev) => ({ ...prev, ...updates }));
        setPdfUploading(false);
        setPdfDone(true);
      }
    }, interval);
  }, [pdfFile, pdfUploading, setStats]);

  // ── Drone upload logic ────────────────────────────────────────────────────
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

    const duration = 60000; // 60 seconds
    const interval = 200;
    const steps = duration / interval;
    let step = 0;

    setDroneStage(stages[0].label);
    const timer = setInterval(() => {
      step++;
      const progress = Math.min(100, Math.round((step / steps) * 100));
      setDroneProgress(progress);

      // Update stage label
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

  // ── Sorted area data ────────────────────────────────────────────────────────
  const sortedAreas = [...stats.areaWise].sort((a, b) => {
    const aVal = a[areaSortKey];
    const bVal = b[areaSortKey];
    if (typeof aVal === "string" && typeof bVal === "string") {
      return areaSortDir === "asc"
        ? aVal.localeCompare(bVal)
        : bVal.localeCompare(aVal);
    }
    return areaSortDir === "asc"
      ? (aVal as number) - (bVal as number)
      : (bVal as number) - (aVal as number);
  });

  const toggleAreaSort = (key: typeof areaSortKey) => {
    if (areaSortKey === key) {
      setAreaSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setAreaSortKey(key);
      setAreaSortDir("desc");
    }
  };

  const SortIcon: React.FC<{ col: typeof areaSortKey }> = ({ col }) => {
    if (areaSortKey !== col) return <ChevronDown className="w-3 h-3 text-gray-300" />;
    return areaSortDir === "asc" ? (
      <ChevronUp className="w-3 h-3 text-blue-700" />
    ) : (
      <ChevronDown className="w-3 h-3 text-blue-700" />
    );
  };

  // ── Revenue chart helpers ───────────────────────────────────────────────────
  const maxRevenue = Math.max(
    ...stats.monthlyRevenue.map((m) => Math.max(m.collected, m.pending)),
  );

  // ── Compliance trend helpers ────────────────────────────────────────────────
  const complianceMin = Math.min(...stats.complianceTrend.map((c) => c.rate));
  const complianceMax = Math.max(...stats.complianceTrend.map((c) => c.rate));
  const complianceRange = complianceMax - complianceMin || 1;
  const complianceTrendDir =
    stats.complianceTrend.length >= 2
      ? stats.complianceTrend[stats.complianceTrend.length - 1].rate -
        stats.complianceTrend[stats.complianceTrend.length - 2].rate
      : 0;

  // ── Category chart helpers ──────────────────────────────────────────────────
  const maxCategoryCount = Math.max(...stats.categoryDistribution.map((c) => c.count));

  // ── KPI card definitions ───────────────────────────────────────────────────
  const kpis = [
    {
      label: "Total Industrial Areas",
      value: fmt(stats.totalIndustrialAreas),
      accent: "text-blue-700",
      delta: null,
    },
    {
      label: "Total Plots",
      value: fmt(stats.totalPlots),
      accent: "text-blue-700",
      delta: null,
    },
    {
      label: "Allocated Plots",
      value: fmt(stats.totalAllocatedPlots),
      accent: "text-emerald-600",
      delta: {
        value: `${((stats.totalAllocatedPlots / stats.totalPlots) * 100).toFixed(1)}%`,
        positive: true,
        label: "occupancy",
      },
    },
    {
      label: "Vacant Plots",
      value: fmt(stats.totalVacantPlots),
      accent: "text-amber-600",
      delta: {
        value: `${((stats.totalVacantPlots / stats.totalPlots) * 100).toFixed(1)}%`,
        positive: false,
        label: "of total",
      },
    },
    {
      label: "Encroachments",
      value: fmt(stats.totalEncroachments),
      accent: "text-red-600",
      delta: {
        value: `${((stats.totalEncroachments / stats.totalPlots) * 100).toFixed(1)}%`,
        positive: false,
        label: "of plots",
      },
    },
    {
      label: "Compliance Rate",
      value: `${fmtDec(stats.complianceRate)}%`,
      accent: stats.complianceRate > 75 ? "text-emerald-600" : "text-amber-600",
      delta: {
        value: complianceTrendDir >= 0 ? `+${fmtDec(complianceTrendDir)}` : fmtDec(complianceTrendDir),
        positive: complianceTrendDir >= 0,
        label: "vs last month",
      },
    },
    {
      label: "Active Leases",
      value: fmt(stats.activeLeases),
      accent: "text-blue-700",
      delta: {
        value: fmt(stats.expiredLeases),
        positive: false,
        label: "expired",
      },
    },
    {
      label: "Revenue Collected",
      value: `₹${fmt(stats.totalRevenueCollected)} L`,
      accent: "text-emerald-600",
      delta: {
        value: `₹${fmt(stats.totalRevenuePending)} L`,
        positive: false,
        label: "pending",
      },
    },
  ];

  // ═══════════════════════════════════════════════════════════════════════════
  // RENDER
  // ═══════════════════════════════════════════════════════════════════════════

  return (
    <div className="min-h-screen bg-gray-50 pb-12">
      {/* ── Welcome Bar ──────────────────────────────────────────────────────── */}
      <div className="bg-blue-800 shadow-sm">
        <div className="max-w-[1440px] mx-auto px-4 sm:px-6 lg:px-8 py-5">
          <div className="flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
            {/* Left: User info */}
            <div className="flex items-center gap-4">
              <div className="w-11 h-11 rounded-lg bg-white/15 flex items-center justify-center text-white font-semibold text-sm">
                {user.name
                  .split(" ")
                  .map((w) => w[0])
                  .join("")
                  .slice(0, 2)
                  .toUpperCase()}
              </div>
              <div>
                <h1 className="text-white font-semibold text-base leading-tight">
                  Welcome, {user.name}
                </h1>
                <div className="flex flex-wrap items-center gap-x-3 gap-y-0.5 text-blue-200 text-xs mt-0.5">
                  <span>{user.designation}</span>
                  <span className="hidden sm:inline text-blue-300">|</span>
                  <span>{user.department}</span>
                  <span className="hidden sm:inline text-blue-300">|</span>
                  <span className="capitalize">{user.role}</span>
                </div>
                <div className="text-blue-300 text-[11px] mt-1">
                  Last login:{" "}
                  {lastLogin.toLocaleDateString("en-IN", {
                    day: "2-digit",
                    month: "short",
                    year: "numeric",
                  })}{" "}
                  at{" "}
                  {lastLogin.toLocaleTimeString("en-IN", {
                    hour: "2-digit",
                    minute: "2-digit",
                  })}
                </div>
              </div>
            </div>

            {/* Right: Actions */}
            <div className="flex items-center gap-3">
              <div className="hidden md:block px-3 py-1.5 rounded-lg bg-white/10 text-blue-100 text-xs">
                {new Date().toLocaleDateString("en-IN", {
                  weekday: "long",
                  day: "2-digit",
                  month: "long",
                  year: "numeric",
                })}
              </div>

              {/* Notification bell */}
              <div className="relative" ref={notifRef}>
                <button
                  onClick={() => setNotifOpen((o) => !o)}
                  className="relative p-2.5 rounded-lg bg-white/10 hover:bg-white/20 text-white transition-colors"
                  title="Notifications"
                >
                  <Bell className="w-4 h-4" />
                  {unreadCount > 0 && (
                    <span className="absolute -top-1 -right-1 w-5 h-5 bg-red-500 text-white text-[10px] font-bold rounded-full flex items-center justify-center">
                      {unreadCount > 9 ? "9+" : unreadCount}
                    </span>
                  )}
                </button>

                {notifOpen && (
                  <div className="absolute right-0 top-12 w-96 bg-white rounded-xl shadow-2xl border border-gray-200 z-50 overflow-hidden">
                    {/* Header */}
                    <div className="flex items-center justify-between px-4 py-3 border-b border-gray-100 bg-gray-50">
                      <h3 className="text-sm font-semibold text-gray-800">
                        Notifications
                        {unreadCount > 0 && (
                          <span className="ml-2 text-xs font-medium text-red-600">
                            {unreadCount} new
                          </span>
                        )}
                      </h3>
                      {unreadCount > 0 && (
                        <button
                          onClick={markAllNotificationsRead}
                          className="text-xs text-blue-600 hover:text-blue-800 font-medium"
                        >
                          Mark all read
                        </button>
                      )}
                    </div>

                    {/* Notification list */}
                    <div className="max-h-96 overflow-y-auto divide-y divide-gray-50">
                      {notifications.length === 0 ? (
                        <div className="py-8 text-center text-gray-400 text-sm">
                          No notifications
                        </div>
                      ) : (
                        notifications.map((n) => {
                          const sevColors: Record<string, string> = {
                            critical: "bg-red-100 text-red-700",
                            high: "bg-orange-100 text-orange-700",
                            medium: "bg-yellow-100 text-yellow-700",
                            low: "bg-blue-100 text-blue-700",
                          };
                          const sevIcon: Record<string, React.ReactNode> = {
                            critical: <AlertTriangle className="w-4 h-4 text-red-500" />,
                            high: <AlertTriangle className="w-4 h-4 text-orange-500" />,
                            medium: <MapPin className="w-4 h-4 text-yellow-600" />,
                            low: <ShieldCheck className="w-4 h-4 text-blue-500" />,
                          };
                          const timeAgo = (() => {
                            const diffMs = Date.now() - new Date(n.timestamp).getTime();
                            const mins = Math.floor(diffMs / 60000);
                            if (mins < 60) return `${mins}m ago`;
                            const hrs = Math.floor(mins / 60);
                            if (hrs < 24) return `${hrs}h ago`;
                            return `${Math.floor(hrs / 24)}d ago`;
                          })();

                          return (
                            <div
                              key={n.id}
                              className={`px-4 py-3 hover:bg-gray-50 transition-colors cursor-pointer ${
                                !n.read ? "bg-blue-50/40" : ""
                              }`}
                              onClick={() => markNotificationRead(n.id)}
                            >
                              <div className="flex items-start gap-3">
                                <div className="flex-shrink-0 mt-0.5">
                                  {sevIcon[n.severity]}
                                </div>
                                <div className="flex-1 min-w-0">
                                  <div className="flex items-center gap-2 mb-0.5">
                                    <span className="text-xs font-semibold text-gray-800 truncate">
                                      {n.title}
                                    </span>
                                    {!n.read && (
                                      <span className="w-2 h-2 rounded-full bg-blue-500 flex-shrink-0" />
                                    )}
                                  </div>
                                  <p className="text-[11px] text-gray-500 leading-relaxed line-clamp-2">
                                    {n.message}
                                  </p>
                                  <div className="flex items-center gap-2 mt-1">
                                    <span className={`text-[10px] font-medium px-1.5 py-0.5 rounded-full ${sevColors[n.severity]}`}>
                                      {n.severity}
                                    </span>
                                    <span className="text-[10px] text-gray-400">
                                      {n.area}
                                    </span>
                                    <span className="text-[10px] text-gray-300">|</span>
                                    <span className="text-[10px] text-gray-400">
                                      {timeAgo}
                                    </span>
                                  </div>
                                </div>
                                <button
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    dismissNotification(n.id);
                                  }}
                                  className="flex-shrink-0 p-1 rounded hover:bg-gray-200 text-gray-300 hover:text-gray-500 transition-colors"
                                >
                                  <X className="w-3 h-3" />
                                </button>
                              </div>
                            </div>
                          );
                        })
                      )}
                    </div>
                  </div>
                )}
              </div>

              <button
                onClick={handleExportDashboardPDF}
                disabled={dashExporting}
                className="p-2.5 rounded-lg bg-white/10 hover:bg-white/20 text-white transition-colors disabled:opacity-50"
                title="Export dashboard as PDF"
              >
                {dashExporting ? (
                  <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                ) : (
                  <Download className="w-4 h-4" />
                )}
              </button>

              <button
                onClick={onEnterMap}
                className="px-5 py-2.5 bg-white text-blue-800 font-semibold text-sm rounded-lg hover:bg-blue-50 transition-colors active:scale-[0.98]"
              >
                Enter Map View
              </button>
              <button
                onClick={onLogout}
                className="p-2.5 rounded-lg bg-white/10 hover:bg-white/20 text-white transition-colors"
                title="Sign out"
              >
                <LogOut className="w-4 h-4" />
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* ── Main Content ─────────────────────────────────────────────────────── */}
      <div className="max-w-[1440px] mx-auto px-4 sm:px-6 lg:px-8 mt-6 space-y-6">
        {/* ── PDF Upload Section ──────────────────────────────────────────────── */}
        <Section title="Upload Survey / Land Record PDF">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Drop zone */}
            <div
              className={`relative border-2 border-dashed rounded-xl p-8 text-center transition-all cursor-pointer group ${
                pdfDragOver
                  ? "border-blue-500 bg-blue-50"
                  : pdfFile
                    ? "border-emerald-400 bg-emerald-50/50"
                    : "border-gray-300 bg-gray-50 hover:border-blue-400 hover:bg-blue-50/30"
              }`}
              onDragOver={(e) => {
                e.preventDefault();
                setPdfDragOver(true);
              }}
              onDragLeave={() => setPdfDragOver(false)}
              onDrop={handleDrop}
              onClick={() => fileInputRef.current?.click()}
            >
              <input
                ref={fileInputRef}
                type="file"
                accept=".pdf,application/pdf"
                className="hidden"
                onChange={(e) => {
                  const f = e.target.files?.[0];
                  if (f) handleFileSelect(f);
                }}
              />
              <div className="flex flex-col items-center gap-3">
                {pdfFile ? (
                  <div>
                    <p className="font-medium text-gray-800">{pdfFile.name}</p>
                    <p className="text-xs text-gray-500 mt-0.5">
                      {(pdfFile.size / 1024).toFixed(1)} KB — Click or drag to replace
                    </p>
                  </div>
                ) : (
                  <div>
                    <p className="font-medium text-gray-700">
                      Drag & drop PDF here, or{" "}
                      <span className="text-blue-700 underline">browse</span>
                    </p>
                    <p className="text-xs text-gray-400 mt-0.5">
                      Survey reports, land records, allotment orders (.pdf)
                    </p>
                  </div>
                )}
              </div>
            </div>

            {/* Upload action & status */}
            <div className="flex flex-col justify-center gap-4">
              <div className="space-y-3">
                <p className="text-sm text-gray-600 leading-relaxed">
                  Upload scanned survey documents or land record PDFs. The system
                  extracts plot data to update dashboard statistics.
                </p>
                <button
                  onClick={handleUpload}
                  disabled={!pdfFile || pdfUploading}
                  className={`flex items-center justify-center gap-2 w-full sm:w-auto px-6 py-3 rounded-lg font-semibold text-sm transition-colors ${
                    !pdfFile || pdfUploading
                      ? "bg-gray-200 text-gray-400 cursor-not-allowed"
                      : "bg-blue-800 text-white hover:bg-blue-700 active:scale-[0.98]"
                  }`}
                >
                  {pdfUploading ? (
                    <>
                      <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                      Processing...
                    </>
                  ) : (
                    <>
                      <Upload className="w-4 h-4" />
                      Upload & Process PDF
                    </>
                  )}
                </button>
              </div>

              {/* Progress bar */}
              {pdfUploading && (
                <div className="space-y-2">
                  <div className="flex items-center justify-between text-xs text-gray-600">
                    <span className="flex items-center gap-1.5">
                      <div className="w-3 h-3 border-2 border-blue-600 border-t-transparent rounded-full animate-spin" />
                      Processing: {pdfFile?.name}
                    </span>
                    <span className="font-mono font-semibold text-blue-800">
                      {pdfProgress}%
                    </span>
                  </div>
                  <div className="w-full h-2.5 bg-gray-200 rounded-full overflow-hidden">
                    <div
                      className="h-full bg-blue-600 rounded-full transition-all duration-100 ease-linear"
                      style={{ width: `${pdfProgress}%` }}
                    />
                  </div>
                  <div className="text-[11px] text-gray-400">
                    {pdfProgress < 25
                      ? "Parsing PDF structure..."
                      : pdfProgress < 50
                        ? "Extracting plot data..."
                        : pdfProgress < 75
                          ? "Matching records..."
                          : "Finalizing updates..."}
                  </div>
                </div>
              )}

              {/* Success state */}
              {pdfDone && !pdfUploading && (
                <div className="p-3 bg-emerald-50 border border-emerald-200 rounded-lg">
                  <p className="text-sm font-semibold text-emerald-800">
                    Processing Complete
                  </p>
                  <p className="text-xs text-emerald-600 mt-0.5">
                    Dashboard updated with data from{" "}
                    <span className="font-medium">{pdfFile?.name}</span>. Total plots:{" "}
                    {fmt(stats.totalPlots)}, compliance: {fmtDec(stats.complianceRate)}%.
                  </p>
                </div>
              )}
            </div>
          </div>
        </Section>

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
                  Upload drone survey imagery to update the basemap. The system
                  stitches, georeferences, and integrates images into the existing basemap layer.
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
                    and integrated into the basemap. The updated imagery is now available in Map View.
                  </p>
                </div>
              )}
            </div>
          </div>
        </Section>

        {/* ── KPI Cards ──────────────────────────────────────────────────────── */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {kpis.map((kpi) => (
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
                    {kpi.delta.positive ? (
                      <ArrowUpRight className="w-3 h-3" />
                    ) : (
                      <ArrowDownRight className="w-3 h-3" />
                    )}
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

        {/* ── Revenue Chart + Compliance Trend ────────────────────────────────── */}
        <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
          {/* Revenue chart — 2/3 */}
          <Section title="Monthly Revenue" className="xl:col-span-2">
            <div className="flex items-center gap-5 mb-4 text-xs text-gray-500">
              <span className="flex items-center gap-1.5">
                <span className="w-3 h-3 rounded-sm bg-blue-600 inline-block" />
                Collected (₹ Lakhs)
              </span>
              <span className="flex items-center gap-1.5">
                <span className="w-3 h-3 rounded-sm bg-orange-400 inline-block" />
                Pending (₹ Lakhs)
              </span>
            </div>
            <div className="flex items-end gap-2 h-56">
              {stats.monthlyRevenue.map((m) => (
                <div key={m.month} className="flex-1 flex flex-col items-center gap-1 h-full justify-end">
                  <span className="text-[10px] text-blue-800 font-semibold">
                    {m.collected}
                  </span>
                  <div className="flex gap-0.5 items-end w-full h-[calc(100%-40px)]">
                    <div className="flex-1 flex flex-col justify-end h-full">
                      <div
                        className="w-full bg-blue-600 rounded-t-sm transition-all duration-500"
                        style={{
                          height: `${(m.collected / maxRevenue) * 100}%`,
                        }}
                      />
                    </div>
                    <div className="flex-1 flex flex-col justify-end h-full">
                      <div
                        className="w-full bg-orange-400 rounded-t-sm transition-all duration-500"
                        style={{
                          height: `${(m.pending / maxRevenue) * 100}%`,
                        }}
                      />
                    </div>
                  </div>
                  <span className="text-[10px] text-orange-600 font-medium">
                    {m.pending}
                  </span>
                  <span className="text-[10px] text-gray-400 whitespace-nowrap">
                    {m.month.split(" ")[0].slice(0, 3)}
                  </span>
                </div>
              ))}
            </div>
          </Section>

          {/* Compliance trend — 1/3 */}
          <Section title="Compliance Trend">
            <div className="flex items-center gap-2 mb-4">
              <span className="text-3xl font-bold text-gray-900">
                {fmtDec(stats.complianceRate)}%
              </span>
              <span
                className={`text-sm font-semibold ${
                  complianceTrendDir >= 0 ? "text-emerald-600" : "text-red-600"
                }`}
              >
                {complianceTrendDir >= 0 ? "+" : ""}
                {fmtDec(complianceTrendDir)}%
              </span>
            </div>

            <div className="relative h-44">
              {[0, 25, 50, 75, 100].map((pct) => (
                <div
                  key={pct}
                  className="absolute left-0 right-0 border-t border-gray-100"
                  style={{ bottom: `${pct}%` }}
                >
                  <span className="absolute -top-2.5 -left-0 text-[9px] text-gray-300">
                    {(complianceMin + (complianceRange * pct) / 100).toFixed(0)}
                  </span>
                </div>
              ))}

              <div className="absolute inset-0 flex items-end">
                {stats.complianceTrend.map((point) => {
                  const pct =
                    ((point.rate - complianceMin) / complianceRange) * 100;
                  return (
                    <div
                      key={point.month}
                      className="flex-1 flex flex-col items-center justify-end h-full relative group"
                    >
                      <div
                        className="w-full bg-blue-100 rounded-t-sm"
                        style={{ height: `${pct}%` }}
                      />
                      <div
                        className="absolute w-2.5 h-2.5 rounded-full bg-blue-700 border-2 border-white shadow-sm"
                        style={{ bottom: `calc(${pct}% - 5px)` }}
                      />
                      <div className="absolute opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none bg-gray-800 text-white text-[10px] px-2 py-1 rounded -top-2 whitespace-nowrap z-10">
                        {point.rate}%
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>

            <div className="flex mt-2">
              {stats.complianceTrend.map((point) => (
                <div
                  key={point.month}
                  className="flex-1 text-center text-[10px] text-gray-400"
                >
                  {point.month.split(" ")[0].slice(0, 3)}
                </div>
              ))}
            </div>
           </Section>
        </div>

        {/* ── Satellite Compliance Analysis ─────────────────────────────────── */}
        {compliance && compliance.summary && (
          <Section title="Satellite Compliance Analysis">
            <div className="mb-3">
              <p className="text-xs text-gray-400">
                Real-time compliance status from satellite imagery analysis and allotment records
                {compliance.area_name ? ` for ${compliance.area_name}` : ""}.
              </p>
            </div>

            {/* Summary cards */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-5">
              <div className="rounded-lg px-4 py-3 bg-gray-50 border border-gray-200">
                <div className="flex items-center gap-2 mb-1">
                  <ShieldCheck className="h-4 w-4 text-gray-500" />
                  <span className="text-[10px] font-medium text-gray-500 uppercase tracking-wider">
                    Total Checked
                  </span>
                </div>
                <p className="text-2xl font-bold text-gray-900">
                  {compliance.summary.total_plots}
                </p>
              </div>
              <div className="rounded-lg px-4 py-3 bg-emerald-50 border border-emerald-200">
                <div className="flex items-center gap-2 mb-1">
                  <ShieldCheck className="h-4 w-4 text-emerald-600" />
                  <span className="text-[10px] font-medium text-emerald-600 uppercase tracking-wider">
                    Fully Compliant
                  </span>
                </div>
                <p className="text-2xl font-bold text-emerald-700">
                  {compliance.summary.overall.fully_compliant}
                </p>
              </div>
              <div className="rounded-lg px-4 py-3 bg-red-50 border border-red-200">
                <div className="flex items-center gap-2 mb-1">
                  <AlertTriangle className="h-4 w-4 text-red-600" />
                  <span className="text-[10px] font-medium text-red-600 uppercase tracking-wider">
                    Non-Compliant
                  </span>
                </div>
                <p className="text-2xl font-bold text-red-700">
                  {compliance.summary.overall.non_compliant}
                </p>
              </div>
              <div className="rounded-lg px-4 py-3 bg-gray-50 border border-gray-200">
                <div className="flex items-center gap-2 mb-1">
                  <ShieldCheck className="h-4 w-4 text-gray-400" />
                  <span className="text-[10px] font-medium text-gray-500 uppercase tracking-wider">
                    Unchecked
                  </span>
                </div>
                <p className="text-2xl font-bold text-gray-500">
                  {compliance.summary.overall.unchecked}
                </p>
              </div>
            </div>

            {/* Green Cover + Construction Timeline breakdown */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              {/* Green Cover */}
              <div className="rounded-lg border border-gray-200 p-4">
                <div className="flex items-center gap-2 mb-3">
                  <Leaf className="h-4 w-4 text-green-600" />
                  <span className="text-xs font-semibold text-gray-700">
                    Green Cover ({"\u2265"}{compliance.summary.green_cover.threshold_pct}%)
                  </span>
                </div>
                <div className="flex items-center gap-4 mb-2">
                  <div className="flex-1">
                    <div className="flex justify-between text-[10px] text-gray-500 mb-1">
                      <span>{compliance.summary.green_cover.compliant} compliant</span>
                      <span>{compliance.summary.green_cover.checked} checked</span>
                    </div>
                    <div className="h-2 bg-gray-100 rounded-full overflow-hidden">
                      <div
                        className="h-full bg-green-500 rounded-full transition-all"
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
                {compliance.summary.green_cover.non_compliant > 0 && (
                  <p className="text-[10px] text-red-500">
                    {compliance.summary.green_cover.non_compliant} plot(s) below threshold
                  </p>
                )}
              </div>

              {/* Construction Timeline */}
              <div className="rounded-lg border border-gray-200 p-4">
                <div className="flex items-center gap-2 mb-3">
                  <Clock className="h-4 w-4 text-blue-600" />
                  <span className="text-xs font-semibold text-gray-700">
                    Construction Timeline ({compliance.summary.construction_timeline.deadline_years}yr deadline)
                  </span>
                </div>
                <div className="flex items-center gap-4 mb-2">
                  <div className="flex-1">
                    <div className="flex justify-between text-[10px] text-gray-500 mb-1">
                      <span>{compliance.summary.construction_timeline.compliant} compliant</span>
                      <span>{compliance.summary.construction_timeline.checked} checked</span>
                    </div>
                    <div className="h-2 bg-gray-100 rounded-full overflow-hidden">
                      <div
                        className="h-full bg-blue-500 rounded-full transition-all"
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
                {compliance.summary.construction_timeline.non_compliant > 0 && (
                  <p className="text-[10px] text-red-500">
                    {compliance.summary.construction_timeline.non_compliant} plot(s) past deadline
                  </p>
                )}
              </div>
            </div>
          </Section>
        )}

        {/* ── Industrial Area Statistics + Category Distribution ────────────── */}
        <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
          {/* Area table — 2/3 */}
          <Section title="Industrial Area Statistics" className="xl:col-span-2">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-xs text-gray-500 uppercase tracking-wider">
                    <th
                      className="pb-3 pr-4 cursor-pointer select-none hover:text-gray-700 transition-colors"
                      onClick={() => toggleAreaSort("name")}
                    >
                      <span className="flex items-center gap-1">
                        Industrial Area
                        <SortIcon col="name" />
                      </span>
                    </th>
                    <th className="pb-3 pr-4 text-center">District</th>
                    <th
                      className="pb-3 pr-4 text-right cursor-pointer select-none hover:text-gray-700 transition-colors"
                      onClick={() => toggleAreaSort("plots")}
                    >
                      <span className="flex items-center justify-end gap-1">
                        Plots
                        <SortIcon col="plots" />
                      </span>
                    </th>
                    <th
                      className="pb-3 pr-4 cursor-pointer select-none hover:text-gray-700 transition-colors"
                      onClick={() => toggleAreaSort("occupancy")}
                    >
                      <span className="flex items-center gap-1">
                        Occupancy
                        <SortIcon col="occupancy" />
                      </span>
                    </th>
                    <th
                      className="pb-3 text-right cursor-pointer select-none hover:text-gray-700 transition-colors"
                      onClick={() => toggleAreaSort("revenueCollected")}
                    >
                      <span className="flex items-center justify-end gap-1">
                        Revenue (₹L)
                        <SortIcon col="revenueCollected" />
                      </span>
                    </th>
                    <th className="pb-3 w-8"></th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {sortedAreas.map((a) => {
                    const occColor =
                      a.occupancy >= 80
                        ? "bg-emerald-500"
                        : a.occupancy >= 65
                          ? "bg-blue-500"
                          : a.occupancy >= 50
                            ? "bg-amber-500"
                            : "bg-red-500";
                    return (
                      <tr
                        key={a.name}
                        className="hover:bg-blue-50/50 cursor-pointer transition-colors group"
                        onClick={() => onViewArea(a.name)}
                      >
                        <td className="py-3 pr-4">
                          <span className="font-medium text-gray-800 group-hover:text-blue-700 transition-colors">
                            {a.name}
                          </span>
                          <span className="text-[10px] text-gray-400 ml-2">
                            {a.category}
                          </span>
                        </td>
                        <td className="py-3 pr-4 text-center text-gray-600 text-xs">
                          {a.district}
                        </td>
                        <td className="py-3 pr-4 text-right text-gray-700 font-medium">
                          {fmt(a.plots)}
                        </td>
                        <td className="py-3 pr-4">
                          <div className="flex items-center gap-2">
                            <div className="flex-1 h-2 bg-gray-100 rounded-full overflow-hidden">
                              <div
                                className={`h-full ${occColor} rounded-full transition-all`}
                                style={{ width: `${a.occupancy}%` }}
                              />
                            </div>
                            <span className="text-xs font-semibold text-gray-600 w-9 text-right">
                              {a.occupancy}%
                            </span>
                          </div>
                        </td>
                        <td className="py-3 text-right font-semibold text-gray-800">
                          ₹{fmt(a.revenueCollected)}
                        </td>
                        <td className="py-3 pl-2">
                          <ChevronRight className="w-4 h-4 text-gray-300 group-hover:text-blue-600 transition-colors" />
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </Section>

          {/* Category distribution — 1/3 */}
          <Section title="Category Distribution">
            <div className="space-y-3.5">
              {stats.categoryDistribution.map((cat) => {
                const pct = (cat.count / maxCategoryCount) * 100;
                return (
                  <div key={cat.category}>
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-xs font-medium text-gray-700">
                        {cat.category}
                      </span>
                      <span className="text-xs text-gray-500">
                        {fmt(cat.count)} plots
                      </span>
                    </div>
                    <div className="h-3.5 bg-gray-100 rounded-full overflow-hidden">
                      <div
                        className="h-full bg-blue-600 rounded-full transition-all duration-700"
                        style={{ width: `${pct}%` }}
                      />
                    </div>
                    <div className="text-[10px] text-gray-400 mt-0.5">
                      {hectares(cat.area_sqm)} hectares
                    </div>
                  </div>
                );
              })}
            </div>
          </Section>
        </div>

        {/* ── Surveys + Top Defaulters ───────────────────────────────────────── */}
        <div className="grid grid-cols-1 xl:grid-cols-4 gap-6">
          {/* Surveys — 1/4 */}
          <Section title="Surveys Overview">
            <div className="space-y-5">
              <div className="flex items-center justify-between">
                <div className="text-center flex-1">
                  <p className="text-3xl font-bold text-emerald-600">
                    {stats.surveysCompleted}
                  </p>
                  <p className="text-[11px] text-gray-500 mt-1 font-medium">
                    Completed
                  </p>
                </div>
                <div className="w-px h-12 bg-gray-200" />
                <div className="text-center flex-1">
                  <p className="text-3xl font-bold text-amber-600">
                    {stats.surveysPending}
                  </p>
                  <p className="text-[11px] text-gray-500 mt-1 font-medium">
                    Pending
                  </p>
                </div>
              </div>

              {/* Progress ring */}
              <div className="flex flex-col items-center">
                <div className="relative w-28 h-28">
                  <svg
                    className="w-full h-full -rotate-90"
                    viewBox="0 0 100 100"
                  >
                    <circle
                      cx="50"
                      cy="50"
                      r="42"
                      fill="none"
                      stroke="#e5e7eb"
                      strokeWidth="8"
                    />
                    <circle
                      cx="50"
                      cy="50"
                      r="42"
                      fill="none"
                      stroke="#1e40af"
                      strokeWidth="8"
                      strokeLinecap="round"
                      strokeDasharray={`${
                        (stats.surveysCompleted /
                          (stats.surveysCompleted + stats.surveysPending)) *
                        264
                      } 264`}
                    />
                  </svg>
                  <div className="absolute inset-0 flex items-center justify-center">
                    <span className="text-lg font-bold text-gray-800">
                      {(
                        (stats.surveysCompleted /
                          (stats.surveysCompleted + stats.surveysPending)) *
                        100
                      ).toFixed(0)}
                      %
                    </span>
                  </div>
                </div>
              </div>

              <div className="text-xs text-gray-500 bg-gray-50 rounded-lg px-3 py-2 text-center">
                Last survey:{" "}
                <span className="font-medium text-gray-700">
                  {new Date(stats.lastSurveyDate).toLocaleDateString("en-IN", {
                    day: "2-digit",
                    month: "short",
                    year: "numeric",
                  })}
                </span>
              </div>
            </div>
          </Section>

          {/* Top Defaulters — 3/4 */}
          <Section title="Top Defaulters" className="xl:col-span-3">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-xs text-gray-500 uppercase tracking-wider">
                    <th className="pb-3 pr-4">Plot ID</th>
                    <th className="pb-3 pr-4">Allottee</th>
                    <th className="pb-3 pr-4">Area</th>
                    <th className="pb-3 pr-4 text-right">Due Amount (₹L)</th>
                    <th className="pb-3 pr-4 text-center">Months Overdue</th>
                    <th className="pb-3 text-center">Karma Score</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {stats.topDefaulters.map((d) => {
                    const karma = getKarmaLabel(d.karmaScore);
                    const isCritical = d.karmaScore < 30;
                    return (
                      <tr
                        key={d.plotId}
                        className={`transition-colors ${
                          isCritical
                            ? "bg-red-50/60 hover:bg-red-50"
                            : "hover:bg-gray-50"
                        }`}
                      >
                        <td className="py-3 pr-4">
                          <span className="font-mono font-semibold text-gray-800 text-xs bg-gray-100 px-2 py-1 rounded">
                            {d.plotId}
                          </span>
                        </td>
                        <td className="py-3 pr-4">
                          <span className="font-medium text-gray-700">
                            {d.allotteeName}
                          </span>
                        </td>
                        <td className="py-3 pr-4 text-gray-600">{d.area}</td>
                        <td className="py-3 pr-4 text-right">
                          <span className="font-semibold text-red-700">
                            ₹{fmtDec(d.dueAmount)}
                          </span>
                        </td>
                        <td className="py-3 pr-4 text-center">
                          <span
                            className={`inline-flex items-center justify-center w-8 h-8 rounded-full text-xs font-bold ${
                              d.monthsOverdue > 12
                                ? "bg-red-100 text-red-700"
                                : d.monthsOverdue > 6
                                  ? "bg-orange-100 text-orange-700"
                                  : "bg-yellow-100 text-yellow-700"
                            }`}
                          >
                            {d.monthsOverdue}
                          </span>
                        </td>
                        <td className="py-3 text-center">
                          <span
                            className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-semibold ${karma.bg} ${karma.color}`}
                          >
                            {d.karmaScore}
                            <span className="text-[10px] font-medium opacity-75">
                              {karma.label}
                            </span>
                          </span>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </Section>
        </div>

        {/* ── Recent Activities ──────────────────────────────────────────────── */}
        <Section title="Recent Activities">
          <div className="space-y-0">
            {stats.recentActivities.map((activity, i) => {
              const isLast = i === stats.recentActivities.length - 1;
              const statusClass =
                STATUS_COLORS[activity.status] || STATUS_COLORS.pending;

              return (
                <div key={activity.id} className="flex gap-4">
                  {/* Timeline dot */}
                  <div className="flex flex-col items-center">
                    <div className="w-2.5 h-2.5 rounded-full bg-blue-600 mt-1.5 flex-shrink-0" />
                    {!isLast && (
                      <div className="w-px flex-1 bg-gray-200 min-h-[24px]" />
                    )}
                  </div>

                  {/* Content */}
                  <div className="pb-5 flex-1">
                    <div className="flex flex-col sm:flex-row sm:items-center gap-1 sm:gap-3">
                      <p className="text-sm text-gray-800 leading-snug flex-1">
                        {activity.description}
                      </p>
                      <span
                        className={`text-[11px] font-semibold px-2 py-0.5 rounded-full capitalize flex-shrink-0 ${statusClass}`}
                      >
                        {activity.status.replace("_", " ")}
                      </span>
                    </div>
                    <div className="flex items-center gap-3 mt-1 text-[11px] text-gray-400">
                      <span>{activity.area}</span>
                      <span>
                        {new Date(activity.date).toLocaleDateString("en-IN", {
                          day: "2-digit",
                          month: "short",
                          year: "numeric",
                        })}
                      </span>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </Section>

        {/* ── Quick Stats Footer ─────────────────────────────────────────────── */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-5">
            <p className="text-xs text-gray-500 font-medium uppercase tracking-wider">
              Revenue Pending
            </p>
            <p className="text-xl font-bold text-gray-900 mt-1">
              ₹{fmt(stats.totalRevenuePending)} Lakhs
            </p>
            <p className="text-[11px] text-gray-400 mt-0.5">
              Across all industrial areas
            </p>
          </div>

          <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-5">
            <p className="text-xs text-gray-500 font-medium uppercase tracking-wider">
              Expired Leases
            </p>
            <p className="text-xl font-bold text-gray-900 mt-1">
              {fmt(stats.expiredLeases)}
            </p>
            <p className="text-[11px] text-gray-400 mt-0.5">
              Require renewal or action
            </p>
          </div>

          <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-5">
            <p className="text-xs text-gray-500 font-medium uppercase tracking-wider">
              Total Area
            </p>
            <p className="text-xl font-bold text-gray-900 mt-1">
              {fmt(Number(hectares(stats.totalArea_sqm)))} Hectares
            </p>
            <p className="text-[11px] text-gray-400 mt-0.5">
              {fmt(stats.totalArea_sqm)} sq. meters managed
            </p>
          </div>
        </div>

        {/* ── Footer branding ────────────────────────────────────────────────── */}
        <div className="text-center py-4 border-t border-gray-200">
          <p className="text-[11px] text-gray-400">
            DRISHTI — Automated Land Monitoring System | CSIDC
          </p>
          <p className="text-[10px] text-gray-300 mt-0.5">
            Data last refreshed:{" "}
            {new Date().toLocaleDateString("en-IN", {
              day: "2-digit",
              month: "short",
              year: "numeric",
              hour: "2-digit",
              minute: "2-digit",
            })}
          </p>
        </div>
      </div>
    </div>
  );
};

export default Dashboard;
