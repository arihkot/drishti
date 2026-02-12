import { Eye, Satellite, PanelLeft, MapPinned, Loader2 } from "lucide-react";
import { useStore } from "../stores/useStore";

export default function Header() {
  const viewMode = useStore((s) => s.viewMode);
  const setViewMode = useStore((s) => s.setViewMode);
  const toggleSidebar = useStore((s) => s.toggleSidebar);
  const showCsidcReference = useStore((s) => s.showCsidcReference);
  const toggleCsidcReference = useStore((s) => s.toggleCsidcReference);
  const csidcReferenceLoading = useStore((s) => s.csidcReferenceLoading);
  const selectedArea = useStore((s) => s.selectedArea);

  return (
    <header className="fixed top-0 left-0 right-0 z-50 h-14 bg-gradient-to-r from-orange-800 to-orange-600 flex items-center justify-between px-4 shadow-md">
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
        {/* View mode toggle */}
        <div className="flex rounded-md overflow-hidden border border-white/30">
          <button
            onClick={() => setViewMode("satellite")}
            className={`flex items-center gap-1 px-2.5 py-1 text-xs font-medium transition-colors ${
              viewMode === "satellite"
                ? "bg-white text-orange-800"
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
                ? "bg-white text-orange-800"
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
            if (!selectedArea) return;
            toggleCsidcReference();
          }}
          disabled={csidcReferenceLoading}
          className={`flex items-center gap-1 px-2.5 py-1 text-xs font-medium rounded-md border transition-colors ${
            !selectedArea
              ? "text-white/30 border-white/15 cursor-not-allowed"
              : csidcReferenceLoading
                ? "text-white/50 border-white/30 cursor-wait"
                : showCsidcReference
                  ? "bg-white text-orange-800 border-white"
                  : "text-white/70 border-white/30 hover:bg-white/10"
          }`}
          title={
            !selectedArea
              ? "Select an area first"
              : csidcReferenceLoading
                ? "Loading CSIDC reference plots..."
                : "Toggle CSIDC reference plots overlay"
          }
        >
          {csidcReferenceLoading ? (
            <Loader2 size={14} className="animate-spin" />
          ) : (
            <MapPinned size={14} />
          )}
          CSIDC Ref
        </button>

        {/* Sidebar toggle */}
        <button
          onClick={toggleSidebar}
          className="p-1.5 rounded-md text-white hover:bg-white/10 transition-colors"
          aria-label="Toggle sidebar"
        >
          <PanelLeft size={20} />
        </button>
      </div>
    </header>
  );
}
