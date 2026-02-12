/**
 * Mock data for CSIDC dashboards — realistic industrial area data
 * based on CSIDC Chhattisgarh industrial areas.
 *
 * Area names, districts, and categories are sourced from real CSIDC
 * GeoServer WFS layers. Revenue, payment, and karma figures are mocked
 * but internally consistent (totals = sum of parts).
 */

// ── Real CSIDC industrial areas ─────────────────────────────────────────────
export interface AreaRecord {
  name: string;
  district: string;
  category: string;
  plots: number;
  allocated: number;
  vacant: number;
  encroachments: number;
  area_sqm: number;
  occupancy: number; // %
  compliance: number; // %
  revenueCollected: number; // lakhs
  revenuePending: number; // lakhs
  establishedYear: number;
}

// Real CSIDC industrial area data (names from WFS layers)
const AREA_DATA: AreaRecord[] = [
  { name: "URLA", district: "Raipur", category: "Industrial", plots: 612, allocated: 524, vacant: 88, encroachments: 24, area_sqm: 3_200_000, occupancy: 86, compliance: 82, revenueCollected: 680, revenuePending: 145, establishedYear: 1989 },
  { name: "SILTARA", district: "Raipur", category: "Industrial", plots: 845, allocated: 698, vacant: 147, encroachments: 31, area_sqm: 5_600_000, occupancy: 83, compliance: 79, revenueCollected: 920, revenuePending: 210, establishedYear: 2001 },
  { name: "BHANPURI", district: "Raipur", category: "Old Industrial", plots: 234, allocated: 208, vacant: 26, encroachments: 12, area_sqm: 980_000, occupancy: 89, compliance: 84, revenueCollected: 310, revenuePending: 52, establishedYear: 1983 },
  { name: "BORAI", district: "Durg", category: "Industrial", plots: 378, allocated: 296, vacant: 82, encroachments: 18, area_sqm: 2_100_000, occupancy: 78, compliance: 76, revenueCollected: 420, revenuePending: 115, establishedYear: 1996 },
  { name: "RIKHI", district: "Raipur", category: "Old Industrial", plots: 189, allocated: 162, vacant: 27, encroachments: 8, area_sqm: 750_000, occupancy: 86, compliance: 81, revenueCollected: 195, revenuePending: 38, establishedYear: 1985 },
  { name: "METAL PARK", district: "Raipur", category: "Industrial", plots: 156, allocated: 118, vacant: 38, encroachments: 5, area_sqm: 1_200_000, occupancy: 76, compliance: 88, revenueCollected: 240, revenuePending: 42, establishedYear: 2012 },
  { name: "GATHULA", district: "Bilaspur", category: "Industrial", plots: 289, allocated: 198, vacant: 91, encroachments: 14, area_sqm: 1_800_000, occupancy: 69, compliance: 72, revenueCollected: 245, revenuePending: 78, establishedYear: 2003 },
  { name: "BIRGAON", district: "Raipur", category: "Old Industrial", plots: 167, allocated: 148, vacant: 19, encroachments: 9, area_sqm: 680_000, occupancy: 89, compliance: 83, revenueCollected: 178, revenuePending: 32, establishedYear: 1987 },
  { name: "SIRGITTI", district: "Bilaspur", category: "Industrial", plots: 245, allocated: 172, vacant: 73, encroachments: 11, area_sqm: 1_450_000, occupancy: 70, compliance: 74, revenueCollected: 198, revenuePending: 65, establishedYear: 2005 },
  { name: "BHILAI", district: "Durg", category: "Industrial", plots: 412, allocated: 342, vacant: 70, encroachments: 16, area_sqm: 2_800_000, occupancy: 83, compliance: 80, revenueCollected: 510, revenuePending: 98, establishedYear: 1991 },
  { name: "KORBA", district: "Korba", category: "Industrial", plots: 198, allocated: 134, vacant: 64, encroachments: 7, area_sqm: 1_350_000, occupancy: 68, compliance: 71, revenueCollected: 165, revenuePending: 58, establishedYear: 2002 },
  { name: "RAIGARH", district: "Raigarh", category: "Industrial", plots: 176, allocated: 128, vacant: 48, encroachments: 6, area_sqm: 1_100_000, occupancy: 73, compliance: 75, revenueCollected: 148, revenuePending: 45, establishedYear: 2004 },
  { name: "RAJNANDGAON", district: "Rajnandgaon", category: "Industrial", plots: 142, allocated: 94, vacant: 48, encroachments: 4, area_sqm: 850_000, occupancy: 66, compliance: 70, revenueCollected: 105, revenuePending: 42, establishedYear: 2006 },
  { name: "JAGDALPUR", district: "Jagdalpur", category: "Directorate", plots: 98, allocated: 58, vacant: 40, encroachments: 2, area_sqm: 620_000, occupancy: 59, compliance: 68, revenueCollected: 62, revenuePending: 28, establishedYear: 2008 },
  { name: "NAYA RAIPUR", district: "Raipur", category: "Industrial", plots: 124, allocated: 78, vacant: 46, encroachments: 1, area_sqm: 1_400_000, occupancy: 63, compliance: 92, revenueCollected: 185, revenuePending: 25, establishedYear: 2015 },
  { name: "DURG", district: "Durg", category: "Old Industrial", plots: 156, allocated: 132, vacant: 24, encroachments: 10, area_sqm: 720_000, occupancy: 85, compliance: 77, revenueCollected: 162, revenuePending: 48, establishedYear: 1988 },
];

export { AREA_DATA };

// ── Dashboard-level interfaces ──────────────────────────────────────────────

export interface DashboardStats {
  totalIndustrialAreas: number;
  totalPlots: number;
  totalAllocatedPlots: number;
  totalVacantPlots: number;
  totalEncroachments: number;
  totalArea_sqm: number;
  totalAllocatedArea_sqm: number;
  totalRevenueCollected: number; // in lakhs
  totalRevenuePending: number;
  complianceRate: number; // percentage
  activeLeases: number;
  expiredLeases: number;
  surveysCompleted: number;
  surveysPending: number;
  lastSurveyDate: string;
  monthlyRevenue: { month: string; collected: number; pending: number }[];
  complianceTrend: { month: string; rate: number }[];
  categoryDistribution: { category: string; count: number; area_sqm: number }[];
  recentActivities: {
    id: number;
    type: string;
    description: string;
    area: string;
    date: string;
    status: string;
  }[];
  topDefaulters: {
    plotId: string;
    allotteeName: string;
    area: string;
    dueAmount: number;
    monthsOverdue: number;
    karmaScore: number;
  }[];
  areaWise: AreaRecord[];
}

export interface AreaDashboardData {
  name: string;
  district: string;
  category: string;
  totalPlots: number;
  allocatedPlots: number;
  vacantPlots: number;
  encroachments: number;
  totalArea_sqm: number;
  allocatedArea_sqm: number;
  occupancyRate: number;
  complianceRate: number;
  revenueCollected: number;
  revenuePending: number;
  karmaScore: number;
  establishedYear: number;
  managingAuthority: string;
  amenities: string[];
  plotDetails: PlotDetail[];
  paymentHistory: { month: string; amount: number; status: string }[];
  encroachmentDetails: {
    plotId: string;
    type: string;
    area_sqm: number;
    severity: string;
    detectedDate: string;
  }[];
}

export interface PlotDetail {
  plotId: string;
  plotNumber: string;
  allotteeName: string;
  companyName: string;
  industryType: string;
  area_sqm: number;
  leaseStartDate: string;
  leaseEndDate: string;
  leaseStatus: "active" | "expired" | "terminated" | "pending";
  monthlyRent: number;
  totalDues: number;
  lastPaymentDate: string;
  paymentStatus: "current" | "overdue" | "defaulter";
  karmaScore: number;
  utilizationStatus: "operational" | "under_construction" | "vacant" | "partial";
  complianceStatus: "compliant" | "non_compliant" | "under_review";
  contactNumber: string;
  email: string;
}

// ── Karma score ─────────────────────────────────────────────────────────────

export function calculateKarmaScore(plot: {
  totalDues: number;
  monthlyRent: number;
  leaseStatus: string;
  paymentStatus: string;
  complianceStatus: string;
  utilizationStatus: string;
}): number {
  let score = 100;

  if (plot.paymentStatus === "defaulter") score -= 40;
  else if (plot.paymentStatus === "overdue") score -= 20;

  const monthsOverdue = plot.monthlyRent > 0 ? plot.totalDues / plot.monthlyRent : 0;
  if (monthsOverdue > 12) score -= 25;
  else if (monthsOverdue > 6) score -= 15;
  else if (monthsOverdue > 3) score -= 8;

  if (plot.leaseStatus === "terminated") score -= 15;
  else if (plot.leaseStatus === "expired") score -= 10;

  if (plot.complianceStatus === "non_compliant") score -= 10;
  else if (plot.complianceStatus === "under_review") score -= 5;

  if (plot.utilizationStatus === "vacant") score -= 10;
  else if (plot.utilizationStatus === "partial") score -= 5;

  return Math.max(0, Math.min(100, score));
}

export function getKarmaLabel(score: number): {
  label: string;
  color: string;
  bg: string;
} {
  if (score >= 85) return { label: "Excellent", color: "text-emerald-700", bg: "bg-emerald-100" };
  if (score >= 70) return { label: "Good", color: "text-blue-700", bg: "bg-blue-100" };
  if (score >= 50) return { label: "Fair", color: "text-yellow-700", bg: "bg-yellow-100" };
  if (score >= 30) return { label: "Poor", color: "text-orange-700", bg: "bg-orange-100" };
  return { label: "Critical", color: "text-red-700", bg: "bg-red-100" };
}

// ── Dashboard stats (computed from AREA_DATA) ───────────────────────────────

export function getMockDashboardStats(): DashboardStats {
  const totalPlots = AREA_DATA.reduce((s, a) => s + a.plots, 0);
  const totalAllocated = AREA_DATA.reduce((s, a) => s + a.allocated, 0);
  const totalVacant = AREA_DATA.reduce((s, a) => s + a.vacant, 0);
  const totalEncroachments = AREA_DATA.reduce((s, a) => s + a.encroachments, 0);
  const totalArea = AREA_DATA.reduce((s, a) => s + a.area_sqm, 0);
  const totalRevCollected = AREA_DATA.reduce((s, a) => s + a.revenueCollected, 0);
  const totalRevPending = AREA_DATA.reduce((s, a) => s + a.revenuePending, 0);

  // Weighted average compliance
  const complianceRate = +(
    AREA_DATA.reduce((s, a) => s + a.compliance * a.plots, 0) / totalPlots
  ).toFixed(1);

  const activeLeases = Math.round(totalAllocated * 0.89);
  const expiredLeases = totalAllocated - activeLeases;

  // Allocate area proportionally
  const totalAllocatedArea = Math.round(
    AREA_DATA.reduce((s, a) => s + a.area_sqm * (a.allocated / a.plots), 0)
  );

  return {
    totalIndustrialAreas: AREA_DATA.length,
    totalPlots,
    totalAllocatedPlots: totalAllocated,
    totalVacantPlots: totalVacant,
    totalEncroachments,
    totalArea_sqm: totalArea,
    totalAllocatedArea_sqm: totalAllocatedArea,
    totalRevenueCollected: totalRevCollected,
    totalRevenuePending: totalRevPending,
    complianceRate,
    activeLeases,
    expiredLeases,
    surveysCompleted: 42,
    surveysPending: 47,
    lastSurveyDate: "2025-12-15",
    monthlyRevenue: [
      { month: "Jul 2025", collected: 380, pending: 95 },
      { month: "Aug 2025", collected: 410, pending: 88 },
      { month: "Sep 2025", collected: 395, pending: 102 },
      { month: "Oct 2025", collected: 425, pending: 78 },
      { month: "Nov 2025", collected: 440, pending: 85 },
      { month: "Dec 2025", collected: 415, pending: 92 },
      { month: "Jan 2026", collected: 460, pending: 72 },
      { month: "Feb 2026", collected: 435, pending: 80 },
    ],
    complianceTrend: [
      { month: "Jul 2025", rate: 72.1 },
      { month: "Aug 2025", rate: 73.5 },
      { month: "Sep 2025", rate: 74.2 },
      { month: "Oct 2025", rate: 75.8 },
      { month: "Nov 2025", rate: 76.9 },
      { month: "Dec 2025", rate: 77.5 },
      { month: "Jan 2026", rate: 78.1 },
      { month: "Feb 2026", rate: complianceRate },
    ],
    categoryDistribution: [
      { category: "Manufacturing", count: 1456, area_sqm: 12_400_000 },
      { category: "IT/ITES", count: 342, area_sqm: 2_800_000 },
      { category: "Food Processing", count: 278, area_sqm: 3_100_000 },
      { category: "Textile", count: 189, area_sqm: 1_950_000 },
      { category: "Pharma", count: 156, area_sqm: 1_600_000 },
      { category: "Metal & Steel", count: 423, area_sqm: 4_200_000 },
      { category: "Other", count: 403, area_sqm: 2_450_000 },
    ],
    recentActivities: [
      { id: 1, type: "detection", description: "Satellite boundary detection completed for URLA Industrial Area", area: "URLA", date: "2026-02-13", status: "completed" },
      { id: 2, type: "encroachment", description: "Encroachment detected on Plot B-42, SILTARA Growth Centre", area: "SILTARA", date: "2026-02-12", status: "flagged" },
      { id: 3, type: "payment", description: "Quarterly dues collected from RIKHI Industrial Area \u2014 23 allottees", area: "RIKHI", date: "2026-02-11", status: "completed" },
      { id: 4, type: "lease", description: "Lease renewal processed for M/s Shree Cement Ltd, BHANPURI", area: "BHANPURI", date: "2026-02-10", status: "approved" },
      { id: 5, type: "survey", description: "Ground survey initiated for METAL PARK boundary verification", area: "METAL PARK", date: "2026-02-09", status: "in_progress" },
      { id: 6, type: "compliance", description: "Non-compliance notice issued to 3 allottees in BORAI Industrial Area", area: "BORAI", date: "2026-02-08", status: "pending" },
    ],
    topDefaulters: [
      { plotId: "SIL-B-42", allotteeName: "M/s Gupta Iron Works", area: "SILTARA", dueAmount: 18.5, monthsOverdue: 14, karmaScore: 15 },
      { plotId: "URL-C-17", allotteeName: "M/s Rajshree Steels Pvt Ltd", area: "URLA", dueAmount: 12.8, monthsOverdue: 11, karmaScore: 22 },
      { plotId: "BOR-A-08", allotteeName: "M/s National Plastics", area: "BORAI", dueAmount: 9.4, monthsOverdue: 9, karmaScore: 30 },
      { plotId: "RIK-D-23", allotteeName: "M/s Chhattisgarh Agro Industries", area: "RIKHI", dueAmount: 7.2, monthsOverdue: 7, karmaScore: 38 },
      { plotId: "BHP-E-11", allotteeName: "M/s Sai Enterprises", area: "BHANPURI", dueAmount: 5.6, monthsOverdue: 6, karmaScore: 45 },
    ],
    areaWise: AREA_DATA,
  };
}

// ── Area dashboard ──────────────────────────────────────────────────────────

export function getMockAreaDashboard(areaName: string): AreaDashboardData {
  // Try to find real area data; fall back to generated values
  const record = AREA_DATA.find(
    (a) => a.name.toLowerCase() === areaName.toLowerCase()
  );

  const plotCount = record?.plots ?? 20 + Math.floor(areaName.length * 7) % 60;
  const allocated = record?.allocated ?? Math.floor(plotCount * 0.78);
  const vacant = record?.vacant ?? plotCount - allocated;
  const encroachments = record?.encroachments ?? Math.floor(plotCount * 0.04);
  const totalAreaSqm = record?.area_sqm ?? plotCount * 2500;
  const occupancyRate = record?.occupancy ?? Math.round((allocated / plotCount) * 100);
  const complianceRate = record?.compliance ?? 72 + (areaName.length % 20);
  const revenueCollected = record?.revenueCollected ?? 45 + areaName.length * 3;
  const revenuePending = record?.revenuePending ?? 8 + (areaName.length % 7);
  const estYear = record?.establishedYear ?? 1995 + (areaName.length % 20);
  const district = record?.district ?? ["Raipur", "Durg", "Bilaspur", "Korba", "Raigarh"][areaName.length % 5];
  const category = record?.category ?? "Industrial";

  const plotDetails: PlotDetail[] = [];
  const industries = ["Manufacturing", "Food Processing", "IT/ITES", "Textile", "Steel", "Pharma", "Agro", "Engineering"];
  const names = [
    "M/s Shree Industries", "M/s Bharat Steel Pvt Ltd", "M/s CG Agro Foods",
    "M/s National Polymers", "M/s Rajshree Fabricators", "M/s Sai Engineering Works",
    "M/s Mahamaya Textiles", "M/s Chhattisgarh Cement Corp", "M/s Gupta Iron & Steel",
    "M/s Raipur Chemicals Ltd", "M/s Shakti Industries", "M/s Narmada Foods Pvt Ltd",
    "M/s Godavari Steel Works", "M/s CG Pharma Solutions", "M/s Durga Enterprises",
    "M/s Aryan IT Services", "M/s Mahanadi Polymers", "M/s Kalinga Metals",
    "M/s Samrat Agro Industries", "M/s Vishwakarma Fabrication",
  ];

  for (let i = 0; i < Math.min(plotCount, 20); i++) {
    const monthlyRent = 5000 + Math.floor(Math.random() * 25000);
    const isDefaulter = i < 3;
    const isOverdue = i >= 3 && i < 6;
    const totalDues = isDefaulter
      ? monthlyRent * (8 + Math.floor(Math.random() * 10))
      : isOverdue
        ? monthlyRent * (2 + Math.floor(Math.random() * 4))
        : 0;

    const leaseStatus: PlotDetail["leaseStatus"] = i < 1 ? "expired" : i < 2 ? "terminated" : "active";
    const paymentStatus: PlotDetail["paymentStatus"] = isDefaulter ? "defaulter" : isOverdue ? "overdue" : "current";
    const complianceStatus: PlotDetail["complianceStatus"] = i < 2 ? "non_compliant" : i < 4 ? "under_review" : "compliant";
    const utilizationStatus: PlotDetail["utilizationStatus"] = i < 1 ? "vacant" : i < 3 ? "partial" : "operational";

    const plot: PlotDetail = {
      plotId: `${areaName.slice(0, 3).toUpperCase()}-${String.fromCharCode(65 + Math.floor(i / 10))}-${String(i + 1).padStart(2, "0")}`,
      plotNumber: `${String.fromCharCode(65 + Math.floor(i / 10))}-${i + 1}`,
      allotteeName: names[i % names.length],
      companyName: names[i % names.length],
      industryType: industries[i % industries.length],
      area_sqm: 500 + Math.floor(Math.random() * 4500),
      leaseStartDate: `${2015 + (i % 8)}-${String(1 + (i % 12)).padStart(2, "0")}-01`,
      leaseEndDate: `${2035 + (i % 8)}-${String(1 + (i % 12)).padStart(2, "0")}-01`,
      leaseStatus,
      monthlyRent,
      totalDues,
      lastPaymentDate: isDefaulter ? "2024-06-15" : isOverdue ? "2025-10-01" : "2026-01-15",
      paymentStatus,
      karmaScore: 0,
      utilizationStatus,
      complianceStatus,
      contactNumber: `+91 ${7000000000 + Math.floor(Math.random() * 999999999)}`,
      email: `contact@${names[i % names.length].split(" ").pop()?.toLowerCase() ?? "company"}.co.in`,
    };
    plot.karmaScore = calculateKarmaScore(plot);
    plotDetails.push(plot);
  }

  // Karma score from plot details average
  const avgKarma =
    plotDetails.length > 0
      ? Math.round(plotDetails.reduce((s, p) => s + p.karmaScore, 0) / plotDetails.length)
      : 65;

  return {
    name: areaName,
    district,
    category,
    totalPlots: plotCount,
    allocatedPlots: allocated,
    vacantPlots: vacant,
    encroachments,
    totalArea_sqm: totalAreaSqm,
    allocatedArea_sqm: Math.round(totalAreaSqm * (allocated / plotCount)),
    occupancyRate,
    complianceRate,
    revenueCollected,
    revenuePending,
    karmaScore: avgKarma,
    establishedYear: estYear,
    managingAuthority: "CSIDC, Naya Raipur",
    amenities: ["Water Supply", "Electricity", "Drainage", "Internal Roads", "Street Lights", "Common ETP", "Boundary Wall"],
    plotDetails,
    paymentHistory: [
      { month: "Sep 2025", amount: +(revenueCollected * 0.14).toFixed(1), status: "collected" },
      { month: "Oct 2025", amount: +(revenueCollected * 0.16).toFixed(1), status: "collected" },
      { month: "Nov 2025", amount: +(revenueCollected * 0.13).toFixed(1), status: "collected" },
      { month: "Dec 2025", amount: +(revenueCollected * 0.17).toFixed(1), status: "collected" },
      { month: "Jan 2026", amount: +(revenueCollected * 0.15).toFixed(1), status: "collected" },
      { month: "Feb 2026", amount: +(revenueCollected * 0.09).toFixed(1), status: "partial" },
    ],
    encroachmentDetails:
      encroachments > 0
        ? [
            { plotId: `${areaName.slice(0, 3).toUpperCase()}-B-12`, type: "Boundary Extension", area_sqm: 45, severity: "medium", detectedDate: "2026-01-20" },
            { plotId: `${areaName.slice(0, 3).toUpperCase()}-C-05`, type: "Unauthorized Construction", area_sqm: 120, severity: "high", detectedDate: "2026-01-15" },
          ]
        : [],
  };
}

// ── PDF upload mock ─────────────────────────────────────────────────────────

export function getPdfProcessingUpdates(): Partial<DashboardStats> {
  const base = getMockDashboardStats();
  return {
    totalPlots: base.totalPlots + 44,
    totalAllocatedPlots: base.totalAllocatedPlots + 38,
    totalVacantPlots: base.totalVacantPlots + 6,
    totalEncroachments: base.totalEncroachments + 3,
    totalRevenueCollected: base.totalRevenueCollected + 70,
    totalRevenuePending: base.totalRevenuePending - 15,
    complianceRate: +(base.complianceRate + 0.7).toFixed(1),
    surveysCompleted: base.surveysCompleted + 1,
    surveysPending: base.surveysPending - 1,
    lastSurveyDate: "2026-02-13",
  };
}
