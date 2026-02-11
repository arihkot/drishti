import { Eye, Satellite, PanelLeft } from "lucide-react";
import { useStore } from "../stores/useStore";

export default function Header() {
  const viewMode = useStore((s) => s.viewMode);
  const setViewMode = useStore((s) => s.setViewMode);
  const toggleSidebar = useStore((s) => s.toggleSidebar);

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
