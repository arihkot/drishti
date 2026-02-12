import { Eye, EyeOff, Satellite, PanelLeft, MapPinned, LayoutDashboard, LogOut } from "lucide-react";
import { useStore } from "../stores/useStore";

interface HeaderProps {
  onDashboard?: () => void;
  onLogout?: () => void;
}

export default function Header({ onDashboard, onLogout }: HeaderProps) {
  const viewMode = useStore((s) => s.viewMode);
  const setViewMode = useStore((s) => s.setViewMode);
  const toggleSidebar = useStore((s) => s.toggleSidebar);
  const showCsidcReference = useStore((s) => s.showCsidcReference);
  const toggleCsidcReference = useStore((s) => s.toggleCsidcReference);
  const hideDetectedPlots = useStore((s) => s.hideDetectedPlots);
  const toggleHideDetectedPlots = useStore((s) => s.toggleHideDetectedPlots);
  const activeProject = useStore((s) => s.activeProject);
  const showToast = useStore((s) => s.showToast);

  const hasBbox = activeProject?.bbox && activeProject.bbox.length === 4;

  return (
    <header className="fixed top-0 left-0 right-0 z-50 h-14 bg-blue-800 flex items-center justify-between px-4 shadow-md">
      {/* Left: Branding */}
      <div className="flex items-center gap-2 min-w-0">
        <div className="flex flex-col leading-tight">
          <span className="text-white font-bold text-lg tracking-wide">
            DRISHTI
          </span>
          <span className="text-white/80 text-[10px]">
            Automated Land Monitoring System
          </span>
        </div>
      </div>

      {/* Center: Organisation name */}
      <div className="hidden md:block text-white font-medium text-sm tracking-wide text-center">
        CHHATTISGARH STATE INDUSTRIAL DEVELOPMENT CORPORATION
      </div>

      {/* Right: Controls */}
      <div className="flex items-center gap-2">
        {/* Dashboard button */}
        {onDashboard && (
          <button
            onClick={onDashboard}
            className="flex items-center gap-1 px-2.5 py-1 text-xs font-medium rounded-md border border-white/30 text-white/70 hover:bg-white/10 transition-colors"
            title="Return to Dashboard"
          >
            <LayoutDashboard size={14} />
            Dashboard
          </button>
        )}

        {/* View mode toggle */}
        <div className="flex rounded-md overflow-hidden border border-white/30">
          <button
            onClick={() => setViewMode("satellite")}
            className={`flex items-center gap-1 px-2.5 py-1 text-xs font-medium transition-colors ${
              viewMode === "satellite"
                ? "bg-white text-blue-900"
                : "text-white hover:bg-white/10"
            }`}
          >
            <Satellite size={14} />
            Satellite
          </button>
          <button
            onClick={() => setViewMode("schematic")}
            className={`flex items-center gap-1 px-2.5 py-1 text-xs font-medium transition-colors ${
              viewMode === "schematic"
                ? "bg-white text-blue-900"
                : "text-white hover:bg-white/10"
            }`}
          >
            <Eye size={14} />
            Schematic
          </button>
        </div>

        {/* CSIDC reference layer toggle */}
        <button
          onClick={() => {
            if (!hasBbox) {
              showToast("Run detection first to see CSIDC reference overlay", "info");
              return;
            }
            toggleCsidcReference();
          }}
          className={`flex items-center gap-1 px-2.5 py-1 text-xs font-medium rounded-md border transition-colors ${
            !hasBbox
              ? "text-white/30 border-white/15 cursor-not-allowed"
              : showCsidcReference
                ? "bg-white text-blue-900 border-white"
                : "text-white/70 border-white/30 hover:bg-white/10"
          }`}
          title={
            !hasBbox
              ? "Run detection first to enable CSIDC reference overlay"
              : showCsidcReference
                ? "Hide CSIDC reference plots"
                : "Show CSIDC reference plots overlay"
          }
        >
          <MapPinned size={14} />
          CSIDC Ref
        </button>

        {/* CSIDC Only mode toggle — hides detected plots */}
        <button
          onClick={() => {
            if (!hasBbox) {
              showToast("Run detection first to use CSIDC Only mode", "info");
              return;
            }
            toggleHideDetectedPlots();
          }}
          className={`flex items-center gap-1 px-2.5 py-1 text-xs font-medium rounded-md border transition-colors ${
            !hasBbox
              ? "text-white/30 border-white/15 cursor-not-allowed"
              : hideDetectedPlots
                ? "bg-white text-blue-900 border-white"
                : "text-white/70 border-white/30 hover:bg-white/10"
          }`}
          title={
            !hasBbox
              ? "Run detection first to enable CSIDC Only mode"
              : hideDetectedPlots
                ? "Show detected plot boundaries"
                : "Hide detected plots, show only CSIDC reference"
          }
        >
          <EyeOff size={14} />
          CSIDC Only
        </button>

        {/* Sidebar toggle */}
        <button
          onClick={toggleSidebar}
          className="p-1.5 rounded-md text-white hover:bg-white/10 transition-colors"
          aria-label="Toggle sidebar"
        >
          <PanelLeft size={20} />
        </button>

        {/* Logout */}
        {onLogout && (
          <button
            onClick={onLogout}
            className="p-1.5 rounded-md text-white/70 hover:bg-white/10 hover:text-white transition-colors"
            title="Sign out"
          >
            <LogOut size={16} />
          </button>
        )}
      </div>
    </header>
  );
}
